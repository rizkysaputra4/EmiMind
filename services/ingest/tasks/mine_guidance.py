"""Worker task extracting management guidance targets into Knowledge Graph nodes."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from services.kg.guidance_miner import mine_guidance
from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("ingest.mine_guidance")
WORKER_VERSION = "1.0"


async def mine_guidance_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Ingestion worker task: mines guidance statements and creates GUIDANCE kg_nodes."""
    doc_uuid = UUID(doc_id)
    pool = ctx.get("db_pool") or create_pool()

    nodes_created: list[int] = []

    async with pool.connect() as conn:
        # 1. Fetch document metadata
        d_res = await conn.execute(
            text("SELECT id, ticker, fiscal_period FROM documents WHERE id = :id"),
            {"id": str(doc_uuid)},
        )
        doc = d_res.mappings().first()
        if not doc:
            log.warning("Document not found for guidance mining", doc_id=doc_id)
            return {"status": "not_found", "nodes_created": 0}

        ticker = doc["ticker"]
        fiscal_period = doc["fiscal_period"]

        # 2. Fetch narrative chunks for document
        nc_res = await conn.execute(
            text(
                """
                SELECT id, section, claim_type, text_original, text_en, source_page
                FROM narrative_chunks
                WHERE source_doc_id = :doc_id
                ORDER BY id ASC;
                """
            ),
            {"doc_id": str(doc_uuid)},
        )
        chunks = nc_res.mappings().all()

        for chunk in chunks:
            text_to_mine = chunk["text_en"] or chunk["text_original"] or ""
            # Mine guidance
            payloads = await mine_guidance(text_to_mine, source_period=fiscal_period)
            for p in payloads:
                # Insert GUIDANCE node in kg_nodes
                source_ref = {
                    "doc_id": str(doc_uuid),
                    "page": chunk["source_page"],
                    "chunk_id": chunk["id"],
                }
                # Serialize payload converting Decimals to float
                raw_payload = p.model_dump(mode="json")
                node_res = await conn.execute(
                    text(
                        """
                        INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref, created_at)
                        VALUES ('GUIDANCE', :ticker, :period, CAST(:payload AS jsonb), CAST(:source_ref AS jsonb), now())
                        RETURNING id;
                        """
                    ),
                    {
                        "ticker": ticker,
                        "period": fiscal_period,
                        "payload": json.dumps(raw_payload),
                        "source_ref": json.dumps(source_ref),
                    },
                )
                new_id = node_res.scalar_one()
                nodes_created.append(new_id)

        await conn.commit()

    log.info(
        "Guidance mining completed for document",
        doc_id=doc_id,
        ticker=ticker,
        nodes_count=len(nodes_created),
    )
    return {
        "status": "success",
        "doc_id": doc_id,
        "ticker": ticker,
        "nodes_created": len(nodes_created),
        "node_ids": nodes_created,
    }
