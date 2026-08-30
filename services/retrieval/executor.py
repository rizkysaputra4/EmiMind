"""Retrieval executor executing planned SQL, vector, and narrative retrieval steps."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.kg.traversal import find_guidance_actual_triples, traverse
from services.kg.types import KGTriple
from services.retrieval.narrative_retriever import NarrativeHit, retrieve_narrative
from services.retrieval.planner import RetrievalPlan
from services.shared.db import ACTIVE_FACTS_PREDICATE
from services.shared.logging import get_logger

log = get_logger("retrieval.executor")


class EvidenceBundle(BaseModel):
    """Aggregated raw evidence bundle returned by retrieval executor."""

    facts: list[dict[str, Any]] = Field(default_factory=list)
    deltas: list[dict[str, Any]] = Field(default_factory=list)
    narrative: list[NarrativeHit] = Field(default_factory=list)
    kg_triples: list[KGTriple] = Field(default_factory=list)
    guidance_triples: list[KGTriple] = Field(default_factory=list)
    frame: dict[str, Any] | None = None
    market: dict[str, Any] | None = None


async def execute_plan(
    conn: AsyncConnection,
    plan: RetrievalPlan,
) -> EvidenceBundle:
    """Executes all steps in a RetrievalPlan and returns the unified EvidenceBundle."""
    bundle = EvidenceBundle()

    # 1. Execute L2 Fact Steps
    if plan.l2_steps:
        all_tickers = list({s.ticker for s in plan.l2_steps})
        all_periods = list({p for s in plan.l2_steps for p in s.periods})

        l2_sql = f"""
        SELECT id, ticker, fiscal_period, concept_id, concept_local, value_numeric, unit,
               source_page, source_bbox, extraction_conf AS confidence, extraction_method AS method
        FROM financial_facts
        WHERE {ACTIVE_FACTS_PREDICATE}
          AND ticker = ANY(:tickers)
          AND fiscal_period = ANY(:periods)
        ORDER BY fiscal_period DESC, concept_id ASC
        LIMIT 100;
        """
        res = await conn.execute(text(l2_sql), {"tickers": all_tickers, "periods": all_periods})
        bundle.facts = [dict(r) for r in res.mappings()]

    # 2. Execute L3 Derived Metrics Steps
    if plan.l3_steps:
        all_tickers = list({s.ticker for s in plan.l3_steps})
        all_periods = list({p for s in plan.l3_steps for p in s.periods})

        l3_sql = """
        SELECT metric_id, ticker, fiscal_period, value_numeric, unit, inputs, peer_group_id
        FROM derived_metrics
        WHERE ticker = ANY(:tickers)
          AND fiscal_period = ANY(:periods)
        ORDER BY fiscal_period DESC, metric_id ASC
        LIMIT 100;
        """
        res = await conn.execute(text(l3_sql), {"tickers": all_tickers, "periods": all_periods})
        bundle.deltas = [dict(r) for r in res.mappings()]

    # 3. Execute L4 Narrative Steps
    if plan.l4_steps:
        narrative_hits: list[NarrativeHit] = []
        for s in plan.l4_steps:
            hits = await retrieve_narrative(
                conn=conn,
                query=s.query,
                filters=s.filters,
                top_k=s.top_k,
            )
            narrative_hits.extend(hits)
        bundle.narrative = narrative_hits

    # 4. Execute L5 Knowledge Graph Steps
    if plan.l5_steps:
        for s5 in plan.l5_steps:
            if s5.intent == "GUIDANCE_CHECK":
                g_triples = await find_guidance_actual_triples(
                    conn=conn,
                    ticker=s5.ticker,
                    periods=[s5.period],
                )
                bundle.guidance_triples.extend(g_triples)
            # Causal / Explanation traversal
            elif s5.root_node_id:
                triples = await traverse(
                    conn=conn,
                    root_id=s5.root_node_id,
                    edge_types=["CAUSED_BY", "REALIZED_AS"],
                    max_hops=s5.hops,
                )
                bundle.kg_triples.extend(triples)
            else:
                # Find candidate root claim nodes for ticker
                r_nodes = await conn.execute(
                    text(
                        """
                            SELECT id FROM kg_nodes
                            WHERE ticker = :ticker AND node_type IN ('CLAIM', 'EVENT')
                            ORDER BY id DESC LIMIT 3;
                            """
                    ),
                    {"ticker": s5.ticker},
                )
                for r_row in r_nodes.fetchall():
                    triples = await traverse(
                        conn=conn,
                        root_id=r_row[0],
                        edge_types=["CAUSED_BY", "REALIZED_AS"],
                        max_hops=s5.hops,
                    )
                    bundle.kg_triples.extend(triples)

    # 5. Execute L6 Issuer Profile Steps
    if plan.l6_steps:
        primary_ticker = plan.l6_steps[0].ticker
        res = await conn.execute(
            text(
                "SELECT ticker, name, sector, sub_sector, profile_summary_en, last_facts_period, key_kpis "
                "FROM issuer_profile WHERE ticker = :ticker"
            ),
            {"ticker": primary_ticker},
        )
        row = res.mappings().first()
        if row:
            bundle.frame = dict(row)

    # 6. Execute L7 Market Technical Regime Steps
    if plan.l7_steps:
        primary_ticker = plan.l7_steps[0].ticker
        res = await conn.execute(
            text("SELECT * FROM technical_state WHERE ticker = :ticker LIMIT 1"),
            {"ticker": primary_ticker},
        )
        row = res.mappings().first()
        if row:
            bundle.market = dict(row)

    return bundle
