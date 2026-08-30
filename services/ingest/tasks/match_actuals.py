"""Worker task matching guidance against actuals on document ingestion."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from services.kg.actual_matcher import match_actuals_for
from services.shared.db import create_pool
from services.shared.logging import get_logger
from services.shared.types import FiscalPeriod, Ticker

log = get_logger("ingest.match_actuals")
WORKER_VERSION = "1.0"


async def match_actuals_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Ingestion worker task: matches outstanding guidance against newly ingested actuals."""
    doc_uuid = UUID(doc_id)
    pool = ctx.get("db_pool") or create_pool()

    async with pool.connect() as conn:
        d_res = await conn.execute(
            text("SELECT id, ticker, fiscal_period FROM documents WHERE id = :id"),
            {"id": str(doc_uuid)},
        )
        doc = d_res.mappings().first()
        if not doc:
            log.warning("Document not found for actuals matching", doc_id=doc_id)
            return {"status": "not_found", "matched_count": 0}

        ticker = Ticker(doc["ticker"])
        fiscal_period = FiscalPeriod(doc["fiscal_period"])

        report = await match_actuals_for(conn, ticker, fiscal_period)
        await conn.commit()

    log.info(
        "Actuals matching completed for document",
        doc_id=doc_id,
        ticker=ticker,
        period=fiscal_period,
        matched=report.matched_count,
        edges=len(report.edges_created),
    )
    return {
        "status": "success",
        "doc_id": doc_id,
        "ticker": ticker,
        "period": fiscal_period,
        "matched_count": report.matched_count,
        "edges_created": report.edges_created,
    }
