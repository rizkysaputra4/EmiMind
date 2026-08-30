"""Unit tests for markdown table and narrative evidence renderers."""

from __future__ import annotations

from services.retrieval.narrative_retriever import NarrativeHit
from services.retrieval.renderers import (
    render_derived_deltas,
    render_fact_rows,
    render_narrative_chunks,
    render_peer_percentile_line,
)


def test_render_fact_rows() -> None:
    rows = [
        {
            "ticker": "BMRI",
            "fiscal_period": "2024Q4",
            "concept_id": "idx:NetInterestIncome",
            "value_numeric": 72300000000000.0,
            "unit": "IDR",
            "source_page": 2,
        }
    ]
    md = render_fact_rows(rows)
    assert "| idx:NetInterestIncome |" in md
    assert "[BMRI-FS-2024Q4#p2]" in md


def test_render_derived_deltas() -> None:
    rows = [
        {
            "ticker": "BMRI",
            "fiscal_period": "2024Q4",
            "metric_id": "yoy.revenue",
            "value_numeric": 0.1245,
            "unit": "RATIO",
        }
    ]
    md = render_derived_deltas(rows)
    assert "| yoy.revenue |" in md
    assert "[BMRI-DERIVED-2024Q4]" in md


def test_render_narrative_chunks() -> None:
    hits = [
        NarrativeHit(
            chunk_id=1,
            ticker="BMRI",
            fiscal_period="2024Q4",
            section="MDA",
            source_page=1,
            text_original="Pertumbuhan kredit mencapai 16.3% YoY.",
            text_en="Loan growth reached 16.3% YoY.",
            rerank_score=0.92,
            citation="[BMRI-FS-2024Q4#p1]",
        )
    ]
    md = render_narrative_chunks(hits, budget_tokens=500)
    assert "**[1] MDA Excerpt** [BMRI-FS-2024Q4#p1]" in md
    assert "Loan growth reached 16.3% YoY." in md


def test_render_peer_percentile_line() -> None:
    line = render_peer_percentile_line("BMRI", "bank.nim", 75.0, "KBMI 4 Banks", "2024Q4")
    assert (
        "[PEER COMP] BMRI bank.nim ranks in the 75.0th percentile of KBMI 4 Banks for 2024Q4."
        in line
    )
