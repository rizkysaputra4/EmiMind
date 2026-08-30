"""Worker task: parse_layout extracts page text and layout structures."""

from __future__ import annotations

import io
from typing import Any

from sqlalchemy import text

from services.extraction.pdf import parse_pdf
from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger("ingest.parse_layout")
WORKER_VERSION = "1.0"


async def parse_layout(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Extracts text per page, language, and bounding boxes, uploading pages.jsonl to MinIO."""
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    minio_client = ctx.get("minio_client") or ctx.get("minio")
    if engine is None or minio_client is None:
        raise RuntimeError("Worker context missing database pool or MinIO client.")
    settings = get_settings()

    async with engine.connect() as conn:
        # Fetch document details
        res = await conn.execute(
            text("SELECT id, doc_hash, minio_key FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        doc_hash = doc["doc_hash"]
        minio_key = doc["minio_key"]

        # 1. Check worker_runs idempotency
        run_res = await conn.execute(
            text(
                "SELECT status FROM worker_runs WHERE doc_hash = :hash AND worker_name = 'parse_layout' AND worker_version = :ver"
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("parse_layout already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        # 2. Download raw PDF bytes from MinIO
        response = minio_client.get_object(settings.minio_bucket_raw, minio_key)
        try:
            pdf_bytes = response.read()
        finally:
            response.close()
            response.release_conn()

        # 3. Parse PDF layout
        pages = parse_pdf(pdf_bytes)

        # 4. Serialize pages as JSONL to MinIO
        jsonl_lines = [page.model_dump_json() for page in pages]
        jsonl_bytes = "\n".join(jsonl_lines).encode("utf-8")
        pages_key = f"{minio_key}.pages.jsonl"

        minio_client.put_object(
            settings.minio_bucket_raw,
            pages_key,
            io.BytesIO(jsonl_bytes),
            length=len(jsonl_bytes),
            content_type="application/x-ndjson",
        )

        # 5. Update documents status & page_count
        await conn.execute(
            text("UPDATE documents SET status = 'parsed', page_count = :count WHERE id = :id"),
            {"count": len(pages), "id": doc_id},
        )

        # 6. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'parse_layout', :ver, 'ok', now())
                ON CONFLICT (doc_hash, worker_name, worker_version)
                DO UPDATE SET status = 'ok', finished_at = now();
                """
            ),
            {
                "hash": doc_hash,
                "ver": WORKER_VERSION,
            },
        )
        await conn.commit()

        log.info("parse_layout completed", doc_id=doc_id, pages=len(pages))
        return {"pages": len(pages)}
