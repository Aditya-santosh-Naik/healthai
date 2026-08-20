"""Retrieval. Pipeline step 8.

Retrieval is filtered by the surviving candidate condition codes and is NEVER
run on raw user text (spec section 11). If nothing clears the score threshold,
the caller falls back to templates rather than letting the LLM improvise.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from rag.index import Chunk, load

TOP_K = 5
SCORE_THRESHOLD = 0.30


@dataclass
class RetrievedPassage:
    chunk_id: str
    text: str
    heading: str
    condition: str
    category: str
    source_name: str
    source_url: str
    score: float


@lru_cache(maxsize=1)
def _index() -> tuple[list[Chunk], np.ndarray] | None:
    return load()


def available() -> bool:
    return _index() is not None


def retrieve(
    condition_codes: list[str],
    categories: list[str] | None = None,
    top_k: int = TOP_K,
) -> list[RetrievedPassage]:
    """Top passages for the given candidates.

    The query is built from the structured assessment, not from user text.
    """
    loaded = _index()
    if loaded is None or not condition_codes:
        return []

    chunks, matrix = loaded

    # Restrict to the candidates on the table, plus general safety material.
    allowed = set(condition_codes) | {"general"}
    mask = np.array([c.condition in allowed for c in chunks], dtype=bool)
    if categories:
        wanted = set(categories)
        mask &= np.array([c.category in wanted for c in chunks], dtype=bool)
    if not mask.any():
        return []

    from core import knowledge
    from rag.embedder import embed_query

    names = [
        knowledge.conditions()[c].display_name
        for c in condition_codes
        if c in knowledge.conditions()
    ]
    query = (
        f"{', '.join(names)}: symptoms, warning signs, self care, "
        "when to seek medical care, and medication safety"
    )

    vector = embed_query(query)
    scores = matrix @ vector  # both sides are L2-normalised, so this is cosine
    scores = np.where(mask, scores, -1.0)

    order = np.argsort(-scores)[:top_k]
    results: list[RetrievedPassage] = []
    for i in order:
        score = float(scores[i])
        if score < SCORE_THRESHOLD:
            continue
        chunk = chunks[i]
        results.append(
            RetrievedPassage(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                heading=chunk.heading,
                condition=chunk.condition,
                category=chunk.category,
                source_name=chunk.source_name,
                source_url=chunk.source_url,
                score=score,
            )
        )
    return results


def unique_sources(passages: list[RetrievedPassage]) -> list[dict[str, str]]:
    """Deduplicated source list for the result page."""
    seen: set[str] = set()
    sources: list[dict[str, str]] = []
    for p in passages:
        key = p.source_url or p.source_name
        if key in seen:
            continue
        seen.add(key)
        sources.append({"name": p.source_name, "url": p.source_url})
    return sources
