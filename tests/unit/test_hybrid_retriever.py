"""Unit tests for hybrid narrative retriever with mocked ANN + FTS steps."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.retrieval.narrative_retriever import (
    NarrativeFilters,
    retrieve_narrative,
)
from services.shared.types import FiscalPeriod, Ticker


@pytest.mark.asyncio
async def test_retrieve_narrative_mock() -> None:
    conn = AsyncMock()

    # Check vector extension
    vec_res = MagicMock()
    vec_res.first.return_value = ("vector",)

    # FTS query results
    fts_rows = [
        {
            "id": 10,
            "ticker": "BMRI",
            "fiscal_period": "2024Q4",
            "section": "MDA",
            "source_page": 3,
            "text_original": "Pencapaian laba bersih didorong oleh pertumbuhan margin bunga bersih (NIM).",
            "text_en": "Net profit achievement was driven by net interest margin (NIM) growth.",
            "fts_score": 0.85,
        },
        {
            "id": 11,
            "ticker": "BMRI",
            "fiscal_period": "2024Q4",
            "section": "RISK",
            "source_page": 5,
            "text_original": "Risiko suku bunga dan likuiditas dikelola secara ketat.",
            "text_en": "Interest rate and liquidity risk are managed strictly.",
            "fts_score": 0.45,
        },
    ]
    fts_res = MagicMock()
    fts_res.mappings.return_value = fts_rows

    conn.execute.side_effect = [vec_res, fts_res]

    filters = NarrativeFilters(
        tickers=[Ticker("BMRI")],
        periods=[FiscalPeriod("2024Q4")],
        sections=["MDA", "RISK"],
    )

    hits = await retrieve_narrative(
        conn=conn,
        query="net interest margin drivers",
        filters=filters,
        top_k=2,
    )

    assert len(hits) == 2
    assert hits[0].ticker == "BMRI"
    assert hits[0].citation == "[BMRI-FS-2024Q4#p3]"
    assert hits[0].rerank_score >= 0.0
