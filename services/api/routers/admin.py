"""Admin and ingestion pipeline monitoring router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.api.deps import get_db_conn
from services.shared.logging import get_logger

log = get_logger("api.admin")
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/ingest")
async def get_ingest_dashboard(
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, Any]:
    """Provides high-level system telemetry on document ingestion, unmapped labels, and worker runs."""
    # Docs by status
    docs_res = await conn.execute(
        text("SELECT status, count(*) AS count FROM documents GROUP BY status;")
    )
    docs_by_status = {r["status"]: r["count"] for r in docs_res.mappings()}

    # Unmapped concepts review queue depth
    unmapped_res = await conn.execute(text("SELECT count(*) FROM concept_review;"))
    unmapped_count = unmapped_res.scalar() or 0

    # Open citation reports
    reports_res = await conn.execute(
        text("SELECT status, count(*) AS count FROM citation_reports GROUP BY status;")
    )
    reports_by_status = {r["status"]: r["count"] for r in reports_res.mappings()}

    # Total facts and narrative chunks
    facts_res = await conn.execute(text("SELECT count(*) FROM financial_facts;"))
    facts_count = facts_res.scalar() or 0

    chunks_res = await conn.execute(text("SELECT count(*) FROM narrative_chunks;"))
    chunks_count = chunks_res.scalar() or 0

    return {
        "status": "healthy",
        "documents": docs_by_status,
        "total_financial_facts": facts_count,
        "total_narrative_chunks": chunks_count,
        "unmapped_labels_queue": unmapped_count,
        "citation_reports": reports_by_status,
    }
