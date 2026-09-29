"""Unit tests for embed_pages_task and the backfill ordering (in-memory DB, fake embedder)."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.backfill_page_embeddings import (
    LQ45_TICKERS,
    order_documents,
    priority_rank,
    select_by_priority,
)
from services.ingest.tasks import embed_pages as ep
from services.narrative.embedder import FAKE_MODEL_ID, Embedder, EmbeddingUnavailableError
from tests.unit._fake_async_db import FakeConn, FakeEngine

PAGES = [
    {"id": 11, "page_index": 1, "page_text": "Laporan posisi keuangan", "text_md5": "m1"},
    {"id": 12, "page_index": 2, "page_text": "Catatan atas laporan keuangan", "text_md5": "m2"},
    {"id": 13, "page_index": 3, "page_text": "", "text_md5": "m3"},
]


def _handler(pages: list[dict[str, Any]], changed_ids: frozenset[int] = frozenset()) -> Any:
    state = {"stale": len(pages)}

    def handle(sql: str, p: dict[str, Any]) -> Any:  # noqa: PLR0911 - one branch per query
        if sql.startswith("SELECT id, doc_hash FROM documents"):
            return [{"id": "d1", "doc_hash": "h1"}]
        if sql.startswith("SELECT id, page_index, page_text, md5(page_text)"):
            return pages
        if "FROM pg_extension" in sql:
            return []
        if sql.startswith("UPDATE document_pages"):
            if p["pid"] in changed_ids:
                return 0  # text changed since it was read: the md5 guard matches no row
            state["stale"] -= 1
            return 1
        if sql.startswith("SELECT count(*) FROM document_pages WHERE doc_id = :id AND ("):
            return [{"count": state["stale"]}]
        if sql.startswith("SELECT count(*) FROM document_pages WHERE doc_id = :id"):
            return [{"count": len(pages)}]
        return None

    return handle


@pytest.mark.asyncio
async def test_embed_pages_writes_model_and_guards_on_text_hash() -> None:
    conn = FakeConn(_handler(PAGES))
    out = await ep.embed_pages_task(
        {"db_pool": FakeEngine(conn), "embedder": Embedder(mode="fake"), "settings": object()},
        "d1",
        batch_size=2,
    )
    assert out["status"] == "ok" and out["embedded_count"] == 3 and out["model"] == FAKE_MODEL_ID
    stale_select = conn.sql_matching("SELECT id, page_index, page_text")[0]
    assert "embedding IS NULL OR embedding_model IS DISTINCT FROM :model" in stale_select[0]
    updates = conn.sql_matching("UPDATE document_pages")
    assert len(updates) == 3
    assert "md5(page_text) = :text_md5" in updates[0][0]
    assert all(p["model"] == FAKE_MODEL_ID and len(p["emb"]) == 1024 for _s, p in updates)
    assert [p["text_md5"] for _s, p in updates] == ["m1", "m2", "m3"]
    assert [p["status"] for _s, p in conn.sql_matching("INSERT INTO worker_runs")] == ["running", "ok"]
    assert ep.WORKER_VERSION == "2.0"


@pytest.mark.asyncio
async def test_embed_pages_does_not_clobber_reindexed_page() -> None:
    conn = FakeConn(_handler(PAGES, changed_ids=frozenset({12})))
    out = await ep.embed_pages_task(
        {"db_pool": FakeEngine(conn), "embedder": Embedder(mode="fake"), "settings": object()}, "d1"
    )
    assert out["embedded_count"] == 2 and out["skipped_changed"] == 1
    assert out["status"] == "partial" and out["remaining"] == 1
    last_run = conn.sql_matching("INSERT INTO worker_runs")[-1][1]
    assert last_run["status"] == "failed" and "still stale" in last_run["error"]


@pytest.mark.asyncio
async def test_embed_pages_embedder_failure_is_loud() -> None:
    class Broken:
        model_id = "BAAI/bge-m3"
        device = "cuda"

        async def embed(self, _texts: list[str]) -> list[list[float]]:
            raise EmbeddingUnavailableError("CUDA out of memory")

    conn = FakeConn(_handler(PAGES))
    with pytest.raises(EmbeddingUnavailableError):
        await ep.embed_pages_task(
            {"db_pool": FakeEngine(conn), "embedder": Broken(), "settings": object()}, "d1"
        )
    assert not conn.sql_matching("UPDATE document_pages")
    runs = conn.sql_matching("INSERT INTO worker_runs")
    assert [p["status"] for _s, p in runs] == ["running", "failed"]
    assert conn.rollbacks == 1


@pytest.mark.asyncio
async def test_embed_pages_nothing_stale_is_already_ok() -> None:
    conn = FakeConn(_handler([]))
    out = await ep.embed_pages_task(
        {"db_pool": FakeEngine(conn), "embedder": Embedder(mode="fake"), "settings": object()}, "d1"
    )
    assert out["status"] == "not_indexed"  # 0 pages at all: nothing to mark ok


def test_backfill_priority_order() -> None:
    assert priority_rank("BMRI") == 0 and priority_rank("lsip") == 0
    assert "BBCA" in LQ45_TICKERS and priority_rank("BBCA") == 1
    assert priority_rank("JKON") == 2
    docs = [
        {"ticker": "JKON", "fiscal_period": "2021Q3"},
        {"ticker": "BBCA", "fiscal_period": "2025Q4"},
        {"ticker": "LSIP", "fiscal_period": "2025Q3"},
        {"ticker": "LSIP", "fiscal_period": "2025Q4"},
        {"ticker": "BMRI", "fiscal_period": "2026Q2"},
    ]
    ordered = [(d["ticker"], d["fiscal_period"]) for d in order_documents(docs)]
    assert ordered == [
        ("BMRI", "2026Q2"),
        ("LSIP", "2025Q4"),
        ("LSIP", "2025Q3"),
        ("BBCA", "2025Q4"),
        ("JKON", "2021Q3"),
    ]
    ordered_docs = order_documents(docs)
    lighthouse = select_by_priority(ordered_docs, "lighthouse")
    assert {d["ticker"] for d in lighthouse} == {"BMRI", "LSIP"}
    assert "JKON" not in {d["ticker"] for d in select_by_priority(ordered_docs, "lq45")}
    assert len(select_by_priority(ordered_docs, "all")) == 5
