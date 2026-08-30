"""Token budgeter enforcing strict bucket limits across evidence categories."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from services.market.renderers import render_technical_state
from services.retrieval.executor import EvidenceBundle
from services.retrieval.renderers import (
    render_derived_deltas,
    render_fact_rows,
    render_guidance_actual_table,
    render_kg_triples,
    render_narrative_chunks,
)
from services.retrieval.tokens import count_tokens


class BudgetedBundle(BaseModel):
    """Budgeted and formatted evidence ready for prompt assembly."""

    frame_md: str = ""
    facts_md: str = ""
    derived_md: str = ""
    narrative_md: str = ""
    guidance_md: str = ""
    kg_md: str = ""
    market_md: str = ""
    sidecar_ids: list[int] = Field(default_factory=list)
    total_tokens: int = 0


async def budget(
    bundle: EvidenceBundle,
    facts_cap: int = 1500,
    derived_cap: int = 800,
    narrative_cap: int = 1800,
    frame_cap: int = 500,
    kg_cap: int = 1000,
) -> BudgetedBundle:
    """Renders and trims evidence sections to satisfy token budget caps."""
    sidecar_ids: list[int] = []

    # 1. Budget L6 Issuer Profile
    frame_md = ""
    if bundle.frame and bundle.frame.get("profile_summary_en"):
        frame_ticker = bundle.frame.get("ticker", "")
        frame_period = bundle.frame.get("last_facts_period") or ""
        profile_citation = (
            f"[{frame_ticker}-PROFILE-{frame_period}]" if frame_ticker and frame_period else ""
        )
        header = (
            f"### {bundle.frame.get('name', '')} ({frame_ticker}) Profile "
            f"{profile_citation}".rstrip()
        )
        raw_frame = f"{header}\n{bundle.frame['profile_summary_en']}"
        if count_tokens(raw_frame) <= frame_cap:
            frame_md = raw_frame
        else:
            frame_md = raw_frame[: frame_cap * 4]

    # 2. Budget L2 Facts
    facts_md = ""
    if bundle.facts:
        kept_facts: list[dict[str, Any]] = []
        for r in bundle.facts:
            candidate = [*kept_facts, r]
            cand_md = render_fact_rows(candidate)
            if count_tokens(cand_md) <= facts_cap:
                kept_facts.append(r)
            elif r.get("id"):
                sidecar_ids.append(r["id"])
        facts_md = render_fact_rows(kept_facts)

    # 3. Budget L3 Derived Metrics
    derived_md = ""
    if bundle.deltas:
        kept_deltas: list[dict[str, Any]] = []
        for r in bundle.deltas:
            candidate = [*kept_deltas, r]
            cand_md = render_derived_deltas(candidate)
            if count_tokens(cand_md) <= derived_cap:
                kept_deltas.append(r)
        derived_md = render_derived_deltas(kept_deltas)

    # 4. Budget L4 Narrative Chunks
    narrative_md = ""
    if bundle.narrative:
        narrative_md = render_narrative_chunks(bundle.narrative, budget_tokens=narrative_cap)

    # 5. Budget Guidance Table
    guidance_md = ""
    if bundle.guidance_triples:
        cand_guidance = render_guidance_actual_table(bundle.guidance_triples)
        if count_tokens(cand_guidance) <= kg_cap:
            guidance_md = cand_guidance

    # 6. Budget KG Causal Triples
    kg_md = ""
    if bundle.kg_triples:
        cand_kg = render_kg_triples(bundle.kg_triples)
        if count_tokens(cand_kg) <= kg_cap:
            kg_md = cand_kg

    # 7. Budget Market Technical State
    market_md = ""
    if bundle.market:
        market_md = render_technical_state(bundle.market)

    total_tokens = (
        count_tokens(frame_md)
        + count_tokens(facts_md)
        + count_tokens(derived_md)
        + count_tokens(narrative_md)
        + count_tokens(guidance_md)
        + count_tokens(kg_md)
        + count_tokens(market_md)
    )

    return BudgetedBundle(
        frame_md=frame_md,
        facts_md=facts_md,
        derived_md=derived_md,
        narrative_md=narrative_md,
        guidance_md=guidance_md,
        kg_md=kg_md,
        market_md=market_md,
        sidecar_ids=sidecar_ids,
        total_tokens=total_tokens,
    )
