"""Worker task linking causal relationship edges across document narrative chunks."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from services.kg.causal_linker import link_causes_for_doc
from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("ingest.link_causes")
WORKER_VERSION = "1.0"


async def link_causes_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Ingestion worker task: discovers and links causal factor attribution graphs."""
    doc_uuid = UUID(doc_id)
    pool = ctx.get("db_pool") or create_pool()

    async with pool.connect() as conn:
        report = await link_causes_for_doc(conn, doc_uuid)
        await conn.commit()

    log.info(
        "Causal linking completed for document",
        doc_id=doc_id,
        chunks=report.chunks_analyzed,
        edges=len(report.edges_created),
    )
    return {
        "status": "success",
        "doc_id": doc_id,
        "chunks_analyzed": report.chunks_analyzed,
        "edges_created": report.edges_created,
    }
