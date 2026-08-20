"""Build and load the vector index.

A NumPy matrix pickled to disk, not a vector database. At ~150 chunks, cosine
similarity over a small matrix is a few lines and runs in microseconds; a
vector DB here would be cargo-culting (spec section 3).

Build it with:
    .venv/Scripts/python.exe -m rag.index
"""
import pickle
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import DATA_DIR

KNOWLEDGE_DIR = DATA_DIR / "knowledge"
INDEX_PATH = DATA_DIR / "index.pkl"

# Chunks are split on markdown H2 headings and never mid-list.
_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    heading: str
    condition: str
    category: str
    source_name: str
    source_url: str


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, raw[match.end() :]


def chunk_file(path: Path) -> list[Chunk]:
    """Split one markdown file into chunks, one per H2 section."""
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(raw)

    headings = list(_HEADING.finditer(body))
    if not headings:
        text = body.strip()
        if not text:
            return []
        return [
            Chunk(
                chunk_id=path.stem,
                text=text,
                heading=meta.get("condition", path.stem),
                condition=meta.get("condition", "general"),
                category=meta.get("category", "description"),
                source_name=meta.get("source_name", "Unknown"),
                source_url=meta.get("source_url", ""),
            )
        ]

    chunks: list[Chunk] = []
    for i, match in enumerate(headings):
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        section = body[start:end].strip()
        if not section:
            continue
        heading = match.group(1).strip()
        chunks.append(
            Chunk(
                chunk_id=f"{path.stem}#{i}",
                text=f"{heading}\n\n{section}",
                heading=heading,
                condition=meta.get("condition", "general"),
                category=meta.get("category", "description"),
                source_name=meta.get("source_name", "Unknown"),
                source_url=meta.get("source_url", ""),
            )
        )
    return chunks


def collect_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        chunks.extend(chunk_file(path))
    return chunks


def build(verbose: bool = True) -> int:
    """Embed the corpus and pickle the matrix plus metadata."""
    from rag.embedder import embed_passages

    chunks = collect_chunks()
    if not chunks:
        raise RuntimeError(f"No markdown found in {KNOWLEDGE_DIR}")

    if verbose:
        print(f"Embedding {len(chunks)} chunks from {KNOWLEDGE_DIR}...")

    matrix = embed_passages([c.text for c in chunks])

    # Plain dicts, not dataclass instances: pickling the class ties the file
    # to the module path it was built from, which breaks when the builder runs
    # as __main__.
    with INDEX_PATH.open("wb") as fh:
        pickle.dump(
            {"chunks": [vars(c) for c in chunks], "matrix": matrix},
            fh,
        )

    if verbose:
        conditions = sorted({c.condition for c in chunks})
        print(f"Wrote {INDEX_PATH}")
        print(f"  chunks     : {len(chunks)}")
        print(f"  dimensions : {matrix.shape[1]}")
        print(f"  conditions : {len(conditions)}")
    return len(chunks)


def load() -> tuple[list[Chunk], np.ndarray] | None:
    """Load the index, or None if it has not been built."""
    if not INDEX_PATH.exists():
        return None
    with INDEX_PATH.open("rb") as fh:
        payload = pickle.load(fh)
    return [Chunk(**row) for row in payload["chunks"]], payload["matrix"]


if __name__ == "__main__":
    build()
