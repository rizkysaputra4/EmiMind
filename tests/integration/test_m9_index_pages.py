"""Integration tests for page indexer (M9.2.2)."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shutil
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.ingest.tasks.index_pages import WORKER_VERSION, index_pages_task
from services.mcp.server import get_engine
from services.shared.config import get_settings
from services.shared.minio_client import ensure_bucket, get_minio
from tests.fixtures.m9.build_fixtures import build_fs_small, build_scanned


async def _verify_fs_small_pages(engine: AsyncEngine, doc_id: str, doc_hash: str, minio_client: Any, raw_bucket: str) -> None:
    async with engine.connect() as conn:
        count_res = await conn.execute(
            text("SELECT count(*) FROM document_pages WHERE doc_id = :id"),
            {"id": doc_id},
        )
        assert count_res.scalar() == 8

        bounds_res = await conn.execute(
            text("SELECT min(page_index), max(page_index) FROM document_pages WHERE doc_id = :id"),
            {"id": doc_id},
        )
        bounds_row = bounds_res.first()
        assert bounds_row is not None
        min_page, max_page = bounds_row[0], bounds_row[1]
        assert min_page == 1
        assert max_page == 8

        rows = (
            await conn.execute(
                text("SELECT page_index, image_key, text_source FROM document_pages WHERE doc_id = :id ORDER BY page_index"),
                {"id": doc_id},
            )
        ).mappings().all()

        for row in rows:
            image_key = row["image_key"]
            assert image_key == f"thumbnails/{doc_id}/page_{row['page_index']}.webp"
            stat = minio_client.stat_object(raw_bucket, image_key)
            assert stat.size > 0
            assert row["text_source"] == "pdf_text"

        runs_res = await conn.execute(
            text(
                """
                SELECT status FROM worker_runs
                WHERE doc_hash = :hash AND worker_name = 'index_pages' AND worker_version = :ver
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        runs = runs_res.mappings().all()
        assert len(runs) == 1
        assert runs[0]["status"] == "ok"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_index_pages_fs_small(tmp_path: Path) -> None:
    engine = get_engine()  # type: ignore[no-untyped-call]
    settings = get_settings()
    minio_client = get_minio(settings)
    ensure_bucket(minio_client, settings.minio_bucket_raw)

    pdf_path = tmp_path / "fs_small.pdf"
    build_fs_small(pdf_path)
    pdf_bytes = pdf_path.read_bytes()

    doc_id = str(uuid.uuid4())
    doc_hash = f"hash_{doc_id}"
    minio_key = f"raw/FS_ANNUAL/TEST_FS/{doc_id}.pdf"

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
                    :id, 'TEST_FS', 'FS_ANNUAL', '2025-12-31', '2025Q4', 'id',
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

    ctx = {"db_pool": engine, "minio_client": minio_client, "settings": settings}

    try:
        # Run index_pages_task first time
        result = await index_pages_task(ctx, doc_id)
        assert result["status"] == "ok"
        assert result["pages"] == 8

        # Idempotency: run second time
        second_result = await index_pages_task(ctx, doc_id)
        assert second_result["status"] == "already_ok"

        # Verify pages and worker_runs
        await _verify_fs_small_pages(engine, doc_id, doc_hash, minio_client, settings.minio_bucket_raw)

    finally:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": doc_id})
            await conn.execute(text("DELETE FROM worker_runs WHERE doc_hash = :hash"), {"hash": doc_hash})
            await conn.commit()

        with contextlib.suppress(Exception):
            minio_client.remove_object(settings.minio_bucket_raw, minio_key)
            for p in range(1, 9):
                minio_client.remove_object(settings.minio_bucket_raw, f"thumbnails/{doc_id}/page_{p}.webp")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_index_pages_scanned(tmp_path: Path) -> None:
    if not shutil.which("tesseract"):
        pytest.skip("tesseract is not on PATH, skipping OCR integration test on scanned.pdf")

    engine = get_engine()  # type: ignore[no-untyped-call]
    settings = get_settings()
    minio_client = get_minio(settings)
    ensure_bucket(minio_client, settings.minio_bucket_raw)

    pdf_path = tmp_path / "scanned.pdf"
    build_scanned(pdf_path)
    pdf_bytes = pdf_path.read_bytes()

    doc_id = str(uuid.uuid4())
    doc_hash = f"hash_{doc_id}"
    minio_key = f"raw/FS_ANNUAL/TEST_SCANNED/{doc_id}.pdf"

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
                    :id, 'TEST_SCANNED', 'FS_ANNUAL', '2025-12-31', '2025Q4', 'id',
                    :url, :minio_key, :doc_hash, 2, 'raw'
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

    ctx = {"db_pool": engine, "minio_client": minio_client, "settings": settings}

    try:
        result = await index_pages_task(ctx, doc_id)
        assert result["status"] == "ok"
        assert result["pages"] == 2

        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT page_index, text_source, length(page_text) AS text_len FROM document_pages WHERE doc_id = :id ORDER BY page_index"),
                    {"id": doc_id},
                )
            ).mappings().all()

            assert len(rows) == 2
            for row in rows:
                assert row["text_source"] == "ocr"
                assert row["text_len"] > 50

    finally:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": doc_id})
            await conn.execute(text("DELETE FROM worker_runs WHERE doc_hash = :hash"), {"hash": doc_hash})
            await conn.commit()

        with contextlib.suppress(Exception):
            minio_client.remove_object(settings.minio_bucket_raw, minio_key)
            for p in range(1, 3):
                minio_client.remove_object(settings.minio_bucket_raw, f"thumbnails/{doc_id}/page_{p}.webp")
