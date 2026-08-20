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


def embed_query(text: str) -> np.ndarray:
    """Embed a single query. Returns an L2-normalised float32 vector."""
    vector = _model().encode(
        QUERY_PREFIX + text,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vector.astype(np.float32)
