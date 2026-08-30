"""Worker task: extract_tables executes multi-pass table extraction."""

from __future__ import annotations

import io
from typing import Any

import polars as pl
from sqlalchemy import text

from services.extraction.tables import extract_tables
from services.shared.config import get_settings
from services.shared.logging import get_logger
from services.shared.types import ExtractedTable, PageContent

log = get_logger("ingest.extract_tables")
WORKER_VERSION = "1.0"


async def extract_tables_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Extracts tables from PDF and saves tables.parquet into MinIO."""
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    minio_client = ctx.get("minio_client") or ctx.get("minio")
    if engine is None or minio_client is None:
        raise RuntimeError("Worker context missing database pool or MinIO client.")
    settings = get_settings()

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, doc_hash, minio_key FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        doc_hash = doc["doc_hash"]
        minio_key = doc["minio_key"]

        # 1. Idempotency check
        run_res = await conn.execute(
            text(
                "SELECT status FROM worker_runs WHERE doc_hash = :hash AND worker_name = 'extract_tables' AND worker_version = :ver"
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("extract_tables already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        # 2. Download raw PDF
        pdf_resp = minio_client.get_object(settings.minio_bucket_raw, minio_key)
        try:
            pdf_bytes = pdf_resp.read()
        finally:
            pdf_resp.close()
            pdf_resp.release_conn()

        # 3. Read pages.jsonl
        pages_key = f"{minio_key}.pages.jsonl"
        pages_resp = minio_client.get_object(settings.minio_bucket_raw, pages_key)
        try:
            pages_content = pages_resp.read().decode("utf-8")
        finally:
            pages_resp.close()
            pages_resp.release_conn()

        pages = [
            PageContent.model_validate_json(line)
            for line in pages_content.splitlines()
            if line.strip()
        ]

        # 4. Run table extraction cascade
        tables: list[ExtractedTable] = extract_tables(pdf_bytes, pages)

        # 5. Serialize to Parquet via Polars
        flat_records = []
        for t_idx, table in enumerate(tables):
            for cell in table.cells:
                flat_records.append(
                    {
                        "table_idx": t_idx,
                        "page_num": table.page_num,
                        "extraction_method": table.extraction_method,
                        "table_confidence": table.confidence,
                        "row": cell.row,
                        "col": cell.col,
                        "text": cell.text,
                        "bbox_x0": cell.bbox.x0,
                        "bbox_y0": cell.bbox.y0,
                        "bbox_x1": cell.bbox.x1,
                        "bbox_y1": cell.bbox.y1,
                        "cell_confidence": cell.confidence,
                    }
                )

        parquet_buffer = io.BytesIO()
        if flat_records:
            df = pl.DataFrame(flat_records)
            df.write_parquet(parquet_buffer)
        else:
            df = pl.DataFrame(
                schema={
                    "table_idx": pl.Int64,
                    "page_num": pl.Int64,
                    "extraction_method": pl.String,
                    "table_confidence": pl.Float64,
                    "row": pl.Int64,
                    "col": pl.Int64,
                    "text": pl.String,
                    "bbox_x0": pl.Float64,
                    "bbox_y0": pl.Float64,
                    "bbox_x1": pl.Float64,
                    "bbox_y1": pl.Float64,
                    "cell_confidence": pl.Float64,
                }
            )
            df.write_parquet(parquet_buffer)

        parquet_bytes = parquet_buffer.getvalue()
        tables_key = f"{minio_key}.tables.parquet"
        minio_client.put_object(
            settings.minio_bucket_raw,
            tables_key,
            io.BytesIO(parquet_bytes),
            length=len(parquet_bytes),
            content_type="application/vnd.apache.parquet",
        )

        # 6. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'extract_tables', :ver, 'ok', now())
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

        log.info("extract_tables completed", doc_id=doc_id, tables=len(tables))
        return {"tables": len(tables)}
