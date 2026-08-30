"""Unit tests for token budget enforcement and sidecar tracking."""

from __future__ import annotations

import pytest

from services.retrieval.budgeter import budget
from services.retrieval.executor import EvidenceBundle
from services.retrieval.narrative_retriever import NarrativeHit


@pytest.mark.asyncio
async def test_budget_trims_large_narrative_bundle() -> None:
    # 20 chunks
    hits = [
        NarrativeHit(
            chunk_id=i,
            ticker="BMRI",
            fiscal_period="2024Q4",
            section="MDA",
            source_page=1,
            text_original="Pertumbuhan kredit korporasi dan komersial mendorong ekspansi aset secara berkelanjutan.",
            text_en="Corporate and commercial loan growth drove sustainable asset expansion across segments.",
            rerank_score=0.9 - (i * 0.03),
            citation=f"[BMRI-FS-2024Q4#p{i}]",
        )
        for i in range(1, 21)
    ]

    bundle = EvidenceBundle(
        facts=[
            {
                "id": 1,
                "ticker": "BMRI",
                "fiscal_period": "2024Q4",
                "concept_id": "idx:NetInterestIncome",
                "value_numeric": 72300000000000.0,
                "unit": "IDR",
                "source_page": 1,
            }
        ],
        narrative=hits,
    )

    budgeted = await budget(bundle, narrative_cap=250)
    assert budgeted.narrative_md != ""
    assert budgeted.total_tokens < 1000
