"""Unit tests for the page/narrative embedder: fake vectors only in fake mode, loud failures."""

from __future__ import annotations

import builtins
import math
from typing import Any

import pytest

from services.narrative import embedder as emb_mod
from services.narrative.embedder import (
    EMBEDDING_DIM,
    FAKE_MODEL_ID,
    Embedder,
    EmbeddingUnavailableError,
    resolve_device,
)


def test_fake_mode_is_deterministic_and_normalised() -> None:
    e = Embedder(mode="fake")
    assert e.is_fake and e.model_id == FAKE_MODEL_ID
    v1, v2 = e.embed_sync(["Jumlah aset konsolidasian", "Jumlah aset konsolidasian"])
    assert len(v1) == EMBEDDING_DIM and v1 == v2
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-4)
    assert e.embed_sync([]) == []


@pytest.mark.asyncio
async def test_fake_mode_async_embed() -> None:
    out = await Embedder(mode="fake").embed(["a b", "c"])
    assert len(out) == 2 and all(len(v) == EMBEDDING_DIM for v in out)


def test_real_mode_reports_real_model_id() -> None:
    e = Embedder(model_name="BAAI/bge-m3", device="cpu", mode="real")
    assert not e.is_fake and e.model_id == "BAAI/bge-m3"
    assert e.fp16 is False  # fp16 only on CUDA


def test_real_mode_load_failure_raises_instead_of_faking(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def _no_st(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("sentence_transformers"):
            raise ImportError("sentence_transformers not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_st)
    monkeypatch.setattr(emb_mod, "_MODEL_CACHE", {})
    e = Embedder(model_name="not-a-real/model", device="cpu", mode="real")
    with pytest.raises(EmbeddingUnavailableError, match="Cannot load embedding model"):
        e.embed_sync(["Laporan posisi keuangan"])


def test_real_mode_encode_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Broken:
        def encode(self, *_a: Any, **_k: Any) -> Any:
            raise RuntimeError("CUDA out of memory")

    e = Embedder(model_name="broken/model", device="cpu", mode="real")
    monkeypatch.setattr(e, "_get_model", _Broken)
    with pytest.raises(EmbeddingUnavailableError, match="encode failed"):
        e.embed_sync(["x"])


def test_real_mode_wrong_dimension_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    class _Small:
        def encode(self, texts: list[str], **_k: Any) -> Any:
            return np.ones((len(texts), 384), dtype=np.float32)

    e = Embedder(model_name="small/model", device="cpu", mode="real")
    monkeypatch.setattr(e, "_get_model", _Small)
    with pytest.raises(EmbeddingUnavailableError, match="dim 384"):
        e.embed_sync(["x"])


def test_resolve_device() -> None:
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("cuda:1") == "cuda:1"
    assert resolve_device("auto") in {"cpu", "cuda"}
