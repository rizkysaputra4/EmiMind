"""Integration tests for page router with real database, FTS, ANN, and fixture PDFs."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from services.ingest.tasks.embed_pages import embed_pages_task
from services.ingest.tasks.index_pages import index_pages_task
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.mcp.types import RouteQuery
from services.narrative.embedder import Embedder
from services.retrieval.page_router import route_pages
from services.shared.config import get_settings
from services.shared.minio_client import ensure_bucket, get_minio
from tests.fixtures.m9.build_fixtures import build_bilingual, build_fs_small


@pytest.mark.integration
@pytest.mark.asyncio
async def test_page_router_hybrid_and_fts_only(tmp_path: Path) -> None:
    engine = get_engine()  # type: ignore[no-untyped-call]
    settings = get_settings()
    minio_client = get_minio(settings)
    ensure_bucket(minio_client, settings.minio_bucket_raw)

    pdf_path = tmp_path / "fs_small.pdf"
    build_fs_small(pdf_path)
    pdf_bytes = pdf_path.read_bytes()

    doc_id = str(uuid.uuid4())
    doc_hash = f"hash_{doc_id}"
    minio_key = f"raw/FS_ANNUAL/TEST_ROUTER/{doc_id}.pdf"

    minio_client.put_object(
        settings.minio_bucket_raw,
        minio_key,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )

    async with engine.connect() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO documents (
                    id, ticker, doc_type, period_end, fiscal_period, language,
                    source_url, minio_key, doc_hash, page_count, status
                ) VALUES (
                    :id, 'TEST_ROUTER', 'FS_ANNUAL', '2025-12-31', '2025Q4', 'id',
                    :url, :minio_key, :doc_hash, 8, 'raw'
                );
                """
            ),
            {
                "id": doc_id,
                "url": str(pdf_path),
                "minio_key": minio_key,
                "doc_hash": doc_hash,
            },
        )
        await conn.commit()

    ctx = {"db_pool": engine, "settings": settings, "embedder": Embedder()}

    # 1. Index pages
    idx_res = await index_pages_task(ctx, doc_id)
    assert idx_res["pages"] == 8

    # 2. Backfill embeddings
    emb_res = await embed_pages_task(ctx, doc_id, batch_size=32)
    assert emb_res["embedded_count"] == 8

    # 3. Hybrid routing assertions
    q_loans = get_route_query("BANK_LOANS_NPL", "BANK")
    assert q_loans is not None

    q_bs = get_route_query("BALANCE_SHEET", "ALL")
    assert q_bs is not None

    q_cash = get_route_query("CASH_BANKS", "ALL")
    assert q_cash is not None

    async with engine.connect() as conn:
        # Hybrid leg: BANK_LOANS_NPL returns a span covering both p5 and p6
        spans_loans = await route_pages(conn, doc_id, q_loans, top_k=3)
        assert any(
            5 in s.pages and 6 in s.pages for s in spans_loans
        ), f"Expected span covering both p5 and p6, got {spans_loans}"

        # Hybrid leg: BALANCE_SHEET returns a span containing p2
        spans_bs = await route_pages(conn, doc_id, q_bs, top_k=3)
        assert any(
            2 in s.pages for s in spans_bs
        ), f"Expected span containing p2, got {spans_bs}"

        # Hybrid leg: CASH_BANKS returns p8
        spans_cash = await route_pages(conn, doc_id, q_cash, top_k=3)
        assert any(
            8 in s.pages for s in spans_cash
        ), f"Expected span containing p8, got {spans_cash}"

    # 4. FTS-only mode: set all embeddings to NULL
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE document_pages SET embedding = NULL WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        await conn.commit()

        # FTS-only leg: BANK_LOANS_NPL returns a span covering both p5 and p6
        spans_loans_fts = await route_pages(conn, doc_id, q_loans, top_k=3)
        assert any(
            5 in s.pages and 6 in s.pages for s in spans_loans_fts
        ), f"FTS-only: Expected span covering both p5 and p6, got {spans_loans_fts}"

        # FTS-only leg: BALANCE_SHEET returns a span containing p2
        spans_bs_fts = await route_pages(conn, doc_id, q_bs, top_k=3)
        assert any(
            2 in s.pages for s in spans_bs_fts
        ), f"FTS-only: Expected span containing p2, got {spans_bs_fts}"

        # FTS-only leg: CASH_BANKS returns p8
        spans_cash_fts = await route_pages(conn, doc_id, q_cash, top_k=3)
        assert any(
            8 in s.pages for s in spans_cash_fts
        ), f"FTS-only: Expected span containing p8, got {spans_cash_fts}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_page_router_bilingual_english_query(tmp_path: Path) -> None:
    engine = get_engine()  # type: ignore[no-untyped-call]
    settings = get_settings()
    minio_client = get_minio(settings)
    ensure_bucket(minio_client, settings.minio_bucket_raw)

    pdf_path = tmp_path / "bilingual.pdf"
    build_bilingual(pdf_path)
    pdf_bytes = pdf_path.read_bytes()

    doc_id = str(uuid.uuid4())
    doc_hash = f"hash_{doc_id}"
    minio_key = f"raw/FS_ANNUAL/TEST_BILINGUAL/{doc_id}.pdf"

    minio_client.put_object(
        settings.minio_bucket_raw,
        minio_key,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )

    async with engine.connect() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO documents (
                    id, ticker, doc_type, period_end, fiscal_period, language,
                    source_url, minio_key, doc_hash, page_count, status
                ) VALUES (
                    :id, 'TEST_BILINGUAL', 'FS_ANNUAL', '2025-12-31', '2025Q4', 'mixed',
                    :url, :minio_key, :doc_hash, 1, 'raw'
                );
                """
            ),
            {
                "id": doc_id,
                "url": str(pdf_path),
                "minio_key": minio_key,
                "doc_hash": doc_hash,
            },
        )
        await conn.commit()

    ctx = {"db_pool": engine, "settings": settings, "embedder": Embedder()}
    await index_pages_task(ctx, doc_id)

    # English-only query finds p1
    en_query = RouteQuery(
        terms_id=[],
        terms_en=["consolidated statement of financial position", "cash and cash equivalents"],
        max_pages=2,
    )

    async with engine.connect() as conn:
        spans = await route_pages(conn, doc_id, en_query, top_k=1)
        assert any(
            1 in s.pages for s in spans
        ), f"Expected English query to find p1, got {spans}"
