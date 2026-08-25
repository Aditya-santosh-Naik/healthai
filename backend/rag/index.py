"""Build and load the vector index.

A NumPy matrix on disk, not a vector database. At ~150 chunks, cosine
similarity over a small matrix is a few lines and runs in microseconds; a
vector DB here would be cargo-culting (spec section 3).

Stored with numpy.savez plus JSON metadata rather than pickle. pickle.load
executes arbitrary code in the file it reads, so a pickled index is a remote
code execution primitive if the file is ever replaced. npz + JSON carries data
only and cannot execute anything.

Build it with:
    .venv/Scripts/python.exe -m rag.index
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from config import DATA_DIR

KNOWLEDGE_DIR = DATA_DIR / "knowledge"
INDEX_PATH = DATA_DIR / "index.npz"

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
    """Split YAML front matter from the body.

    yaml.safe_load rather than a hand-rolled key: value loop -- it already
    handles quoting, colons inside values, and type coercion correctly.
    """
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    meta = yaml.safe_load(match.group(1)) or {}
    return {str(k): str(v) for k, v in meta.items()}, raw[match.end() :]


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

    # Metadata as a JSON string inside the npz: data only, no executable
    # payload, and no dependence on the module path the builder ran from.
    np.savez_compressed(
        INDEX_PATH,
        matrix=matrix,
        chunks=json.dumps([vars(c) for c in chunks]),
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
    with np.load(INDEX_PATH, allow_pickle=False) as payload:
        chunks = [Chunk(**row) for row in json.loads(str(payload["chunks"]))]
        return chunks, payload["matrix"]


if __name__ == "__main__":
    build()
