"""Phase I — sentence embeddings + cosine similarity.

Uses Sentence-BERT (Reimers & Gurevych, 2019) as specified in Section 4.3 of the
SIG proposal. Default model is MiniLM-L6-v2 for latency; swap via constructor.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

from sv.config import DEFAULT_SBERT_MODEL

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors.

    Implements equation (2) of the SIG proposal: dot product of normalized vectors.
    Returns a Python float in [-1, 1].
    """
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


class Embedder:
    """Lazy-loading wrapper around a SentenceTransformer model.

    The underlying model is loaded on first call to ``encode`` so that
    constructing an Embedder is cheap (useful for tests and config dry-runs).
    """

    def __init__(self, model_name: str = DEFAULT_SBERT_MODEL, cache_size: int = 1024) -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._encode_cached = lru_cache(maxsize=cache_size)(self._encode_uncached)

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode_uncached(self, text: str) -> np.ndarray:
        model = self._load()
        vec = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
        return vec.astype(np.float32)

    def encode(self, text: str) -> np.ndarray:
        """Embed a single string; result is cached by exact text match."""
        return self._encode_cached(text)

    def cache_info(self):
        return self._encode_cached.cache_info()
