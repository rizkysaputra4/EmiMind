"""Worker task for calculating derived metrics."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.derive.engine import compute_for_document
from services.shared.logging import get_logger

log = get_logger(__name__)

WORKER_VERSION = "1.0"


async def derive_metrics_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Calculates all applicable derived metrics and peer percentiles for an ingested document."""
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    if engine is None:
        raise RuntimeError("Worker context missing database pool.")

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, doc_hash FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        doc_hash = doc["doc_hash"]

        # 1. Idempotency check
        run_res = await conn.execute(
            text(
                """
                SELECT status FROM worker_runs
                WHERE doc_hash = :hash AND worker_name = 'derive_metrics' AND worker_version = :ver
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("derive_metrics already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

    # 2. Compute derived metrics
    report = await compute_for_document(doc_id, engine)

    # 3. Record worker_runs
    async with engine.connect() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'derive_metrics', :ver, 'ok', now())
                ON CONFLICT (doc_hash, worker_name, worker_version)
                DO UPDATE SET status = 'ok', finished_at = now();
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        await conn.commit()

    return {
        "status": "ok",
        "computed": report.computed,
        "skipped": report.skipped_missing_inputs,
        "errors": report.errors,
    }
