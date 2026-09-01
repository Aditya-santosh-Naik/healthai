"""Sentence embeddings via bge-small, on CPU.

The model is ~130 MB and is loaded lazily so importing this module stays cheap.
It is downloaded once from HuggingFace on first use, the same one-time setup
step as `ollama pull`; after that everything runs offline.
"""
from functools import lru_cache

import numpy as np

from config import settings

# bge asks for this prefix on queries (not on stored passages) for retrieval.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model, device="cpu")


def embed_passages(texts: list[str]) -> np.ndarray:
    """Embed corpus passages. Returns an L2-normalised float32 matrix."""
    vectors = _model().encode(
        texts,
        batch_size=16,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.astype(np.float32)


@lru_cache(maxsize=512)
def _embed_query_cached(text: str) -> np.ndarray:
    vector = _model().encode(
        QUERY_PREFIX + text,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    vector = vector.astype(np.float32)
    # Frozen so a caller cannot mutate the cached array in place and corrupt
    # every later hit. Callers only ever read it or feed it to a matmul.
    vector.flags.writeable = False
    return vector


def embed_query(text: str) -> np.ndarray:
    """Embed a single query. Returns an L2-normalised float32 vector.

    Memoised, which is worth doing here and would be wrong almost anywhere
    else in this system.

    Profiling a consultation put 88% of all non-LLM time in retrieval, and 86%
    of THAT in this one call -- 35.9 ms of a 41.6 ms step, against 0.016 ms for
    the mask rebuild and 0.006 ms for the similarity matmul. It is the only
    part of the deterministic pipeline where caching changes anything.

    Safe because of what the query is: retrieval is filtered by candidate
    condition CODES and never runs on user text (spec section 11), so the
    string is condition display names plus a fixed suffix. At most three of
    fourteen conditions, so the key space is bounded at roughly 2,400
    permutations and in practice a handful recur constantly. No user text
    reaches the key, so the cache cannot leak between patients and cannot be
    poisoned by input.
    """
    return _embed_query_cached(text)


def reset_cache() -> None:
    """Drop memoised embeddings. For tests that swap the model or corpus."""
    _embed_query_cached.cache_clear()
