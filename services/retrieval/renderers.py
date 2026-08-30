"""Compact markdown evidence table, guidance matrix, and narrative renderers with mandatory inline citations."""

from __future__ import annotations

from typing import Any

from services.kg.types import KGTriple
from services.retrieval.narrative_retriever import NarrativeHit
from services.retrieval.tokens import count_tokens


def render_fact_rows(rows: list[dict[str, Any]]) -> str:
    """Renders financial fact rows as a compact markdown table with citations."""
    if not rows:
        return "_No financial facts available._"

    lines = [
        "| Concept | Value | Unit | Period | Source Citation |",
        "|:---|---:|:---:|:---:|:---|",
    ]

    for r in rows:
        val = r.get("value_numeric")
        val_str = f"{float(val):,.2f}" if val is not None else "N/A"
        unit = r.get("unit") or "IDR"
        period = r.get("fiscal_period") or ""
        concept = r.get("concept_id") or r.get("concept_local") or ""
        ticker = r.get("ticker") or ""
        page = r.get("source_page", 0)
        citation = f"[{ticker}-FS-{period}#p{page}]"

        lines.append(f"| {concept} | {val_str} | {unit} | {period} | {citation} |")

    return "\n".join(lines)


def render_derived_deltas(rows: list[dict[str, Any]]) -> str:
    """Renders derived metric deltas (YoY / QoQ / Margins) as a compact markdown table."""
    if not rows:
        return "_No derived metric deltas available._"

    lines = [
        "| Metric | Value | Unit | Period | Basis / Citation |",
        "|:---|---:|:---:|:---:|:---|",
    ]

    for r in rows:
        val = r.get("value_numeric")
        val_str = f"{float(val):.4f}" if val is not None else "N/A"
        unit = r.get("unit") or "RATIO"
        period = r.get("fiscal_period") or ""
        m_id = r.get("metric_id") or ""
        ticker = r.get("ticker") or ""
        citation = f"[{ticker}-DERIVED-{period}]"

        lines.append(f"| {m_id} | {val_str} | {unit} | {period} | {citation} |")

    return "\n".join(lines)


def render_narrative_chunks(hits: list[NarrativeHit], budget_tokens: int = 1500) -> str:
    """Renders narrative excerpts with section headers and citations, respecting token budget."""
    if not hits:
        return "_No narrative disclosures found._"

    rendered_blocks: list[str] = []
    current_tokens = 0

    for idx, h in enumerate(hits, start=1):
        text_body = h.text_en or h.text_original
        block = f'**[{idx}] {h.section} Excerpt** {h.citation}\n> "{text_body}"\n'
        block_tokens = count_tokens(block)

        if current_tokens + block_tokens > budget_tokens and rendered_blocks:
            break

        rendered_blocks.append(block)
        current_tokens += block_tokens

    return "\n\n".join(rendered_blocks)


def render_peer_percentile_line(
    ticker: str,
    metric_id: str,
    percentile_value: float,
    peer_group_name: str,
    fiscal_period: str,
) -> str:
    """Renders a one-line cross-sectional peer comparison summary."""
    return (
        f"[PEER COMP] {ticker} {metric_id} ranks in the {percentile_value:.1f}th percentile "
        f"of {peer_group_name} for {fiscal_period}."
    )


def render_guidance_actual_table(triples: list[KGTriple]) -> str:
    """Renders guidance targets vs realized actual outcomes as a markdown table."""
    if not triples:
        return "_No guidance targets found for period._"

    lines = [
        "| Guidance Target (source) | Realized Actual (source) | Delta | Status |",
        "|:---|:---|---:|:---:|",
    ]

    for t in triples:
        src = t.src_node
        dst = t.dst_node
        edge = t.edge
        e_payload = edge.get("payload") or {}

        g_payload = src.get("payload") or {}
        act_payload = dst.get("payload") or {}

        metric = g_payload.get("metric", "")
        low = g_payload.get("low")
        high = g_payload.get("high")
        unit = g_payload.get("unit", "RATIO")
        p_target = g_payload.get("period_target", "")
        src_ref = src.get("source_ref") or {}
        src_page = src_ref.get("page", 1)
        src_ticker = src.get("ticker", "")
        src_period = src.get("fiscal_period", "")
        g_cit = f"[{src_ticker}-PUBEX-{src_period}#p{src_page}]"

        if low is not None and high is not None:
            if unit == "RATIO":
                g_str = f"{metric} {float(low) * 100:.1f}-{float(high) * 100:.1f}% ({p_target})"
            else:
                g_str = f"{metric} {float(low):,.0f}-{float(high):,.0f} {unit} ({p_target})"
        elif low is not None:
            if unit == "RATIO":
                g_str = f"{metric} >= {float(low) * 100:.1f}% ({p_target})"
            else:
                g_str = f"{metric} >= {float(low):,.0f} {unit} ({p_target})"
        elif high is not None:
            if unit == "RATIO":
                g_str = f"{metric} <= {float(high) * 100:.1f}% ({p_target})"
            else:
                g_str = f"{metric} <= {float(high):,.0f} {unit} ({p_target})"
        else:
            g_str = f"{metric} target ({p_target})"

        guidance_cell = f"{g_str} {g_cit}"

        # Actual cell
        act_val = act_payload.get("value")
        act_period = dst.get("fiscal_period", "")
        dst_ref = dst.get("source_ref") or {}
        dst_page = dst_ref.get("page", 1)
        dst_ticker = dst.get("ticker", src_ticker)
        act_cit = f"[{dst_ticker}-FS-{act_period}#p{dst_page}]"

        if act_val is not None:
            if unit == "RATIO":
                act_str = f"{float(act_val) * 100:.2f}%"
            else:
                act_str = f"{float(act_val):,.2f} {unit}"
            actual_cell = f"{act_str} {act_cit}"
        else:
            actual_cell = "Pending Disclosures"

        # Delta & Status
        delta_val = e_payload.get("delta")
        hit_bounds = e_payload.get("hit_bounds", True)
        status_badge = "✅ MET" if hit_bounds else "❌ MISSED"

        if delta_val is not None:
            if unit == "RATIO":
                delta_str = f"{float(delta_val) * 100:+.2f}pp"
            else:
                delta_str = f"{float(delta_val):+,.2f}"
        else:
            delta_str = "—"

        lines.append(f"| {guidance_cell} | {actual_cell} | {delta_str} | {status_badge} |")

    return "\n".join(lines)


def render_kg_triples(triples: list[KGTriple]) -> str:
    """Renders causal relationship edges and factor attribution links."""
    if not triples:
        return "_No causal relationship links found._"

    lines: list[str] = []
    for t in triples:
        src = t.src_node
        dst = t.dst_node
        edge = t.edge
        e_type = edge.get("edge_type", "CAUSED_BY")
        conf = edge.get("confidence", 0.70)
        e_payload = edge.get("payload") or {}

        effect = e_payload.get("effect") or (src.get("payload") or {}).get("metric") or "Outcome"
        driver = e_payload.get("driver") or (dst.get("payload") or {}).get("name") or "Factor"

        src_ref = src.get("source_ref") or {}
        src_page = src_ref.get("page", 1)
        src_ticker = src.get("ticker") or ""
        src_period = src.get("fiscal_period") or ""
        citation = (
            f"[{src_ticker}-FS-{src_period}#p{src_page}]" if src_ticker and src_period else ""
        )

        lines.append(
            f"- **[Effect]** `{effect}` was **{e_type}** {driver} "
            f"(confidence: {conf:.2f}) {citation}"
        )

    return "\n".join(lines)
