"""Pipeline orchestration task: coordinates the document ingestion sequence."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.ingest.tasks.chunk_narrative import chunk_narrative_task
from services.ingest.tasks.derive_metrics import derive_metrics_task
from services.ingest.tasks.embed_narrative import embed_narrative_task
from services.ingest.tasks.extract_tables import extract_tables_task
from services.ingest.tasks.link_causes import link_causes_task
from services.ingest.tasks.match_actuals import match_actuals_task
from services.ingest.tasks.mine_guidance import mine_guidance_task
from services.ingest.tasks.normalize_facts import normalize_facts_task
from services.ingest.tasks.parse_layout import parse_layout
from services.ingest.tasks.refresh_profile import refresh_profile_task
from services.ingest.tasks.xbrl_sidecar import xbrl_sidecar
from services.shared.logging import get_logger

log = get_logger("ingest.pipeline")


async def ingest_document(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Orchestrates the full sequential ingestion pipeline for a document."""
    engine = ctx.get("db_pool")
    log.info("Starting ingestion pipeline", doc_id=doc_id)

    try:
        # Step 1: XBRL sidecar fast path (parallel-safe)
        xbrl_result = await xbrl_sidecar(ctx, doc_id)
        log.info("Step 1 (XBRL) finished", doc_id=doc_id, result=xbrl_result)

        # Step 2: Parse layout and emit pages.jsonl
        layout_result = await parse_layout(ctx, doc_id)
        log.info("Step 2 (Layout) finished", doc_id=doc_id, result=layout_result)

        # Step 3: Multi-pass table extraction
        tables_result = await extract_tables_task(ctx, doc_id)
        log.info("Step 3 (Tables) finished", doc_id=doc_id, result=tables_result)

        # Step 4: Normalize facts to canonical concept IDs
        normalize_result = await normalize_facts_task(ctx, doc_id)
        log.info("Step 4 (Normalize Facts) finished", doc_id=doc_id, result=normalize_result)

        # Step 5: Semantic narrative chunking
        narrative_result = await chunk_narrative_task(ctx, doc_id)
        log.info("Step 5 (Narrative Chunks) finished", doc_id=doc_id, result=narrative_result)

        # Step 6: Translate & Embed narrative chunks
        embed_result = await embed_narrative_task(ctx, doc_id)
        log.info("Step 6 (Embed Narrative) finished", doc_id=doc_id, result=embed_result)

        # Step 7: Derive financial metrics and cross-sectional peer percentiles
        derive_result = await derive_metrics_task(ctx, doc_id)
        log.info("Step 7 (Derive Metrics) finished", doc_id=doc_id, result=derive_result)

        # Step 8: Refresh L6 Issuer Profile card
        profile_result = await refresh_profile_task(ctx, doc_id)
        log.info("Step 8 (Refresh Profile) finished", doc_id=doc_id, result=profile_result)

        # Step 9: Mine management guidance into KG nodes
        guidance_result = await mine_guidance_task(ctx, doc_id)
        log.info("Step 9 (Mine Guidance) finished", doc_id=doc_id, result=guidance_result)

        # Step 10: Match guidance against newly ingested actuals
        actuals_result = await match_actuals_task(ctx, doc_id)
        log.info("Step 10 (Match Actuals) finished", doc_id=doc_id, result=actuals_result)

        # Step 11: Discover and link causal attribution graphs
        causal_result = await link_causes_task(ctx, doc_id)
        log.info("Step 11 (Link Causes) finished", doc_id=doc_id, result=causal_result)

        # Update final document status if facts or pages are parsed
        if engine:
            async with engine.connect() as conn:
                await conn.execute(
                    text(
                        """
                        UPDATE documents
                        SET status = CASE
                            WHEN status = 'failed' THEN 'failed'
                            WHEN EXISTS (SELECT 1 FROM financial_facts WHERE source_doc_id = :id) THEN 'facts_extracted'
                            ELSE 'parsed'
                        END
                        WHERE id = :id;
                        """
                    ),
                    {"id": doc_id},
                )
                await conn.commit()

        log.info("Document ingestion pipeline completed successfully", doc_id=doc_id)
        return {
            "status": "completed",
            "doc_id": doc_id,
            "xbrl": xbrl_result,
            "layout": layout_result,
            "tables": tables_result,
            "normalize": normalize_result,
            "narrative": narrative_result,
            "embed": embed_result,
            "derive": derive_result,
            "profile": profile_result,
            "guidance": guidance_result,
            "actuals": actuals_result,
            "causal": causal_result,
        }

    except Exception as e:
        log.error("Ingestion pipeline failed", doc_id=doc_id, error=str(e))
        if engine:
            async with engine.connect() as conn:
                await conn.execute(
                    text("UPDATE documents SET status = 'failed' WHERE id = :id"),
                    {"id": doc_id},
                )
                await conn.commit()
        raise
