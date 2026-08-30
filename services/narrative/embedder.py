"""Embedding engine wrapping BGE-M3 1024-dimensional dense vectors."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger(__name__)

EMBEDDING_DIM = 1024


def _deterministic_hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generates a normalized deterministic dense embedding vector for testing/offline use."""
    vec = [0.0] * dim
    words = text.lower().split()
    if not words:
        vec[0] = 1.0
        return vec

    for w in words:
        # Hash word into bucket
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [round(x / norm, 6) for x in vec]
    else:
        vec[0] = 1.0
    return vec


class Embedder:
    """BGE-M3 dense text embedder."""

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str | None = None) -> None:
        self.model_name = model_name
        self.device = device or get_settings().embedding_device
        self._model: Any = None
        self._initialized = False

    def _get_model(self) -> Any:
        if self._initialized:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self.device)
            log.info(
                "Loaded SentenceTransformer embedding model",
                model=self.model_name,
                device=self.device,
            )
        except Exception as e:
            log.warning(
                "SentenceTransformer load skipped, using deterministic vector generator",
                error=str(e),
            )
            self._model = None

        self._initialized = True
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generates 1024-dimensional dense embeddings for input texts."""
        if not texts:
            return []

        model = self._get_model()
        if model is not None:
            try:
                embeddings = model.encode(
                    texts,
                    normalize_embeddings=True,
                    batch_size=32,
                    show_progress_bar=False,
                )
                return [e.tolist() for e in embeddings]
            except Exception as e:
                log.warning(
                    "Embedding encode failed, falling back to deterministic vectors", error=str(e)
                )

        return [_deterministic_hash_embedding(t, EMBEDDING_DIM) for t in texts]
