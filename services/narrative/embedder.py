"""Embedding engine wrapping BGE-M3 1024-dimensional dense vectors."""

from __future__ import annotations

import asyncio
import hashlib
import math
import threading
from typing import Any

from services.shared.config import get_settings
from services.shared.errors import RetrievalError
from services.shared.logging import get_logger

log = get_logger(__name__)

EMBEDDING_DIM = 1024
FAKE_MODEL_ID = "fake-hash-v1"

# Loaded models are shared across Embedder instances: bge-m3 is ~2 GB and takes seconds to load.
_MODEL_CACHE: dict[tuple[str, str, bool, int], Any] = {}
_MODEL_LOCK = threading.Lock()


class EmbeddingUnavailableError(RetrievalError):
    """Raised when the configured embedding model cannot be loaded or run."""


def _deterministic_hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Normalized bag-of-words hash vector. Only used when EMI_EMBEDDING_MODE=fake."""
    vec = [0.0] * dim
    words = text.lower().split()
    if not words:
        vec[0] = 1.0
        return vec

    for w in words:
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [round(x / norm, 6) for x in vec]
    else:
        vec[0] = 1.0
    return vec


def resolve_device(device: str) -> str:
    """Maps 'auto' to 'cuda' when a CUDA device is visible, else 'cpu'."""
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class Embedder:
    """BGE-M3 dense text embedder. Never substitutes fake vectors unless mode='fake'."""

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        *,
        mode: str | None = None,
        max_seq_length: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self.mode = mode or settings.embedding_mode
        self.device = resolve_device(device or settings.embedding_device)
        self.max_seq_length = max_seq_length or settings.embedding_max_seq_length
        self.batch_size = batch_size or settings.embedding_batch_size
        self.fp16 = settings.embedding_fp16 and self.device.startswith("cuda")

    @property
    def is_fake(self) -> bool:
        return self.mode == "fake"

    @property
    def model_id(self) -> str:
        """Identifier stored next to every vector (document_pages.embedding_model)."""
        return FAKE_MODEL_ID if self.is_fake else self.model_name

    def _get_model(self) -> Any:
        if self.is_fake:
            return None
        key = (self.model_name, self.device, self.fp16, self.max_seq_length)
        with _MODEL_LOCK:
            cached = _MODEL_CACHE.get(key)
            if cached is not None:
                return cached
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(self.model_name, device=self.device)
                model.max_seq_length = self.max_seq_length
                if self.fp16:
                    model.half()
            except Exception as exc:
                raise EmbeddingUnavailableError(
                    f"Cannot load embedding model '{self.model_name}' on device "
                    f"'{self.device}': {exc}. Install the 'ml' dependency group, check "
                    "EMI_EMBEDDING_DEVICE, or set EMI_EMBEDDING_MODE=fake for tests."
                ) from exc
            log.info(
                "Loaded embedding model",
                model=self.model_name,
                device=self.device,
                fp16=self.fp16,
                max_seq_length=self.max_seq_length,
            )
            _MODEL_CACHE[key] = model
            return model

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Blocking variant of embed(); returns L2-normalised 1024-dim vectors."""
        if not texts:
            return []
        if self.is_fake:
            return [_deterministic_hash_embedding(t, EMBEDDING_DIM) for t in texts]

        model = self._get_model()
        try:
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise EmbeddingUnavailableError(
                f"Embedding encode failed with model '{self.model_name}' on '{self.device}': {exc}"
            ) from exc

        out = [[float(x) for x in v] for v in vectors]
        if out and len(out[0]) != EMBEDDING_DIM:
            raise EmbeddingUnavailableError(
                f"Model '{self.model_name}' returned dim {len(out[0])}, expected {EMBEDDING_DIM}"
            )
        return out

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generates 1024-dimensional dense embeddings for input texts (off the event loop)."""
        if not texts:
            return []
        if self.is_fake:
            return self.embed_sync(texts)
        return await asyncio.to_thread(self.embed_sync, texts)
