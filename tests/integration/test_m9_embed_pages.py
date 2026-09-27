"""Integration tests for page embedding worker (M9.2.4)."""

from __future__ import annotations

import contextlib
import io
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from services.ingest.tasks.embed_pages import embed_pages_task
from services.ingest.tasks.index_pages import index_pages_task
from services.mcp.server import get_engine
from services.narrative.embedder import _deterministic_hash_embedding
from services.shared.config import get_settings
from services.shared.minio_client import ensure_bucket, get_minio
from tests.fixtures.m9.build_fixtures import build_fs_small


class CountingTestEmbedder:
    """Deterministic embedder tracking embed calls and texts."""

    def __init__(self) -> None:
        self.call_count = 0
        self.embedded_text_count = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.embedded_text_count += len(texts)
        return [_deterministic_hash_embedding(t) for t in texts]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_embed_pages_task(tmp_path: Path) -> None:
    engine = get_engine()  # type: ignore[no-untyped-call]
    settings = get_settings()
    minio_client = get_minio(settings)
    ensure_bucket(minio_client, settings.minio_bucket_raw)

    # 1. Build synthetic fs_small.pdf and index it
    pdf_path = tmp_path / "fs_small_embed.pdf"
    build_fs_small(pdf_path)
    pdf_bytes = pdf_path.read_bytes()

    doc_id = str(uuid.uuid4())
    doc_hash = f"hash_{doc_id}"
    minio_key = f"raw/FS_ANNUAL/TEST_EMBED/{doc_id}.pdf"

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
                    :id, 'TEST_EMBED', 'FS_ANNUAL', '2025-12-31', '2025Q4', 'id',
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

    index_ctx = {"db_pool": engine, "minio_client": minio_client, "settings": settings}

    try:
        # Index pages first
        idx_res = await index_pages_task(index_ctx, doc_id)
        assert idx_res["status"] == "ok"
        assert idx_res["pages"] == 8

        # Verify pages exist with NULL embeddings
        async with engine.connect() as conn:
            null_count = await conn.execute(
                text("SELECT count(*) FROM document_pages WHERE doc_id = :id AND embedding IS NULL"),
                {"id": doc_id},
            )
            assert null_count.scalar() == 8

        # 2. Run embed_pages_task with counting embedder in batch_size=4
        counting_embedder = CountingTestEmbedder()
        embed_ctx = {
            "db_pool": engine,
            "embedder": counting_embedder,
            "settings": settings,
        }

        first_res = await embed_pages_task(embed_ctx, doc_id, batch_size=4)
        assert first_res["status"] == "ok"
        assert first_res["embedded_count"] == 8
        assert counting_embedder.call_count == 2
        assert counting_embedder.embedded_text_count == 8

        # Check DB: no NULL embeddings remain
        async with engine.connect() as conn:
            remaining_null = await conn.execute(
                text("SELECT count(*) FROM document_pages WHERE doc_id = :id AND embedding IS NULL"),
                {"id": doc_id},
            )
            assert remaining_null.scalar() == 0

        # 3. Second run must make 0 embed calls
        prev_calls = counting_embedder.call_count
        second_res = await embed_pages_task(embed_ctx, doc_id, batch_size=4)
        assert second_res["status"] == "already_ok"
        assert counting_embedder.call_count == prev_calls  # exactly 0 embed calls

    finally:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": doc_id})
            await conn.execute(text("DELETE FROM worker_runs WHERE doc_hash = :hash"), {"hash": doc_hash})
            await conn.commit()

        with contextlib.suppress(Exception):
            minio_client.remove_object(settings.minio_bucket_raw, minio_key)
            for p in range(1, 9):
                minio_client.remove_object(settings.minio_bucket_raw, f"thumbnails/{doc_id}/page_{p}.webp")
