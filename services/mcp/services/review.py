"""Review, ontology query, metric discovery, and processed documents service."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.derive.valuation import calculate_valuation as default_calculate_valuation
from services.mcp.services.common import get_engine
from services.mcp.types import (
    DiscoveredMetricCandidate,
    DiscoveredMetricResult,
    MetricOntologyDefinition,
    MetricOntologyQueryResult,
)


async def get_issuer_context(
    ticker: str,
    period: str | None = None,
    *,
    engine: AsyncEngine | None = None,
    valuation_fn: Callable[..., Any] = default_calculate_valuation,
) -> dict[str, Any]:
    """Retrieves existing financial facts and derived metrics for an issuer to aid in comparative extraction."""
    eng = engine or get_engine()
    ticker_clean = ticker.upper()

    async with eng.connect() as conn:
        facts_res = await conn.execute(
            text(
                """
                SELECT concept_id, fiscal_period, value_numeric, unit
                FROM financial_facts
                WHERE ticker = :ticker
                ORDER BY fiscal_period DESC, concept_id ASC
                LIMIT 50;
                """
            ),
            {"ticker": ticker_clean},
        )
        facts = [dict(r) for r in facts_res.mappings()]

        derived_res = await conn.execute(
            text(
                """
                SELECT metric_id, fiscal_period, value_numeric, unit
                FROM derived_metrics
                WHERE ticker = :ticker
                ORDER BY fiscal_period DESC, metric_id ASC
                LIMIT 25;
                """
            ),
            {"ticker": ticker_clean},
        )
        metrics = [dict(r) for r in derived_res.mappings()]

        val = await valuation_fn(conn, ticker_clean, is_live=True)

        return {
            "ticker": ticker_clean,
            "target_period": period,
            "existing_facts": facts,
            "existing_metrics": metrics,
            "live_valuation": val,
        }


async def get_metric_ontology(
    sector: str | None = None,
    query: str | None = None,
    category: str | None = None,
    *,
    engine: AsyncEngine | None = None,
) -> MetricOntologyQueryResult:
    """Queries canonical financial and operational metric definitions from the EMIMIND Ontology registry."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        conditions: list[str] = []
        params: dict[str, Any] = {}

        if sector:
            conditions.append(
                "(:sec = ANY(sector_applicability) OR 'ALL' = ANY(sector_applicability))"
            )
            params["sec"] = sector.upper()

        if category:
            conditions.append("category = :cat")
            params["cat"] = category.upper()

        if query:
            conditions.append(
                "(metric_id ILIKE :q OR name_en ILIKE :q OR name_id ILIKE :q OR array_to_string(synonyms_id, ' ') ILIKE :q OR array_to_string(synonyms_en, ' ') ILIKE :q)"
            )
            params["q"] = f"%{query}%"

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT
                metric_id, name_en, name_id, category, sector_applicability,
                importance, value_type, unit, flow_stock_type, extraction_mode,
                calculation_formula, dependencies, source_priority, synonyms_id, synonyms_en
            FROM metric_definitions
            {where_clause}
            ORDER BY category ASC, metric_id ASC;
        """
        res = await conn.execute(text(sql), params)
        rows = [dict(r) for r in res.mappings()]
        metrics = [
            MetricOntologyDefinition(
                metric_id=r["metric_id"],
                name_en=r["name_en"],
                name_id=r["name_id"],
                category=r["category"],
                sector_applicability=r["sector_applicability"] or ["ALL"],
                importance=r["importance"],
                value_type=r["value_type"],
                unit=r["unit"],
                flow_stock_type=r["flow_stock_type"],
                extraction_mode=r["extraction_mode"],
                calculation_formula=r["calculation_formula"],
                dependencies=r["dependencies"] or [],
                source_priority=r["source_priority"] or [],
                synonyms_id=r["synonyms_id"] or [],
                synonyms_en=r["synonyms_en"] or [],
            )
            for r in rows
        ]
        return MetricOntologyQueryResult(
            total_found=len(metrics),
            sector=sector or "ALL",
            metrics=metrics,
        )


async def submit_discovered_metric(
    candidate: DiscoveredMetricCandidate,
    *,
    engine: AsyncEngine | None = None,
) -> DiscoveredMetricResult:
    """Submits a newly discovered industry/operational KPI candidate from a financial filing into EMIMIND memory."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        exist_res = await conn.execute(
            text("SELECT metric_id, name_en FROM metric_definitions WHERE metric_id = :id"),
            {"id": candidate.metric_id},
        )
        if exist_res.mappings().first():
            return DiscoveredMetricResult(
                status="EXISTING",
                metric_id=candidate.metric_id,
                message=f"Metric '{candidate.metric_id}' already exists in canonical ontology.",
            )

        await conn.execute(
            text(
                """
                INSERT INTO metric_definitions (
                    metric_id, name_en, name_id, category, sector_applicability, importance,
                    value_type, unit, flow_stock_type, extraction_mode,
                    source_priority, synonyms_id, synonyms_en, updated_at
                ) VALUES (
                    :id, :name_en, :name_id, :cat, ARRAY[:sec]::TEXT[], :imp,
                    :val_type, :unit, :flow_stock, 'EXTRACTED_RAW',
                    ARRAY[:src]::TEXT[], :syn_id, :syn_en, now()
                )
                ON CONFLICT (metric_id) DO NOTHING;
                """
            ),
            {
                "id": candidate.metric_id,
                "name_en": candidate.name_en,
                "name_id": candidate.name_id,
                "cat": candidate.category.upper(),
                "sec": candidate.sector_code.upper(),
                "imp": candidate.importance.upper(),
                "val_type": candidate.value_type.upper(),
                "unit": candidate.unit,
                "flow_stock": candidate.flow_stock_type,
                "src": candidate.typical_source,
                "syn_id": candidate.synonyms_id,
                "syn_en": candidate.synonyms_en,
            },
        )

        await conn.execute(
            text(
                """
                INSERT INTO concept_map (local_label, sector, canonical_concept_id, confidence, created_by)
                VALUES (:label, :sec, :id, 0.85, 'agent_discovery')
                ON CONFLICT DO NOTHING;
                """
            ),
            {
                "label": candidate.name_id,
                "sec": candidate.sector_code.upper(),
                "id": candidate.metric_id,
            },
        )

        await conn.commit()
        return DiscoveredMetricResult(
            status="PROMOTED",
            metric_id=candidate.metric_id,
            message=f"Successfully registered discovered metric candidate '{candidate.metric_id}' ({candidate.name_en}) into ontology registry.",
        )


async def get_review_queue(*, engine: AsyncEngine | None = None) -> list[dict[str, Any]]:
    """Retrieves unverified documents and extraction exceptions quarantined in the review queue."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT id, ticker, fiscal_period, doc_id, issue_type, severity, validation_report, status, created_at
                FROM ingest_review_queue
                WHERE status = 'PENDING'
                ORDER BY created_at DESC
                LIMIT 50;
                """
            )
        )
        return [dict(r) for r in res.mappings()]


async def list_processed_documents(
    tickers: list[str] | None = None,
    *,
    engine: AsyncEngine | None = None,
) -> list[dict[str, Any]]:
    """List documents already ingested and extracted, so downloaders can skip re-fetching."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        sql = (
            "SELECT ticker, fiscal_period, doc_type, doc_hash, source_url, minio_key, status "
            "FROM documents WHERE status IN ('parsed','facts_extracted')"
        )
        params: dict[str, Any] = {}
        if tickers:
            sql += " AND ticker = ANY(:tickers)"
            params["tickers"] = [t.upper() for t in tickers]
        res = await conn.execute(text(sql), params)
        out: list[dict[str, Any]] = []
        for row in res.mappings():
            src = row.get("source_url") or ""
            mk = row.get("minio_key") or ""
            file_name = Path(src).name if src else (Path(mk).name if mk else "")
            out.append(
                {
                    "ticker": row["ticker"],
                    "fiscal_period": row["fiscal_period"],
                    "doc_type": row["doc_type"],
                    "doc_hash": row["doc_hash"],
                    "file_name": file_name,
                    "status": row["status"],
                }
            )
        return out
