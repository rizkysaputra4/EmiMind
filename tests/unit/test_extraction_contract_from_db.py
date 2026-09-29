"""Verify that build_extraction_contract correctly assembles a contract from DB rows.

Uses a mocked async connection whose .execute returns pre-canned mappings — this
exercises the SQL-issuing / row-assembly path without needing a live Postgres.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.mcp.contracts import build_extraction_contract


def _make_mock_conn(metric_rows: list[dict], module_rows: list[dict], narrative_rows: list[dict]) -> AsyncMock:
    """Return an AsyncMock connection whose .execute returns three canned result sets in order:
    metrics, modules, narratives (matching the order in build_extraction_contract)."""
    call_iter = iter([metric_rows, module_rows, narrative_rows])

    async def execute(stmt, params=None):
        rows = next(call_iter)
        cursor = MagicMock()
        cursor.mappings.return_value = rows
        return cursor

    conn = AsyncMock()
    conn.execute.side_effect = execute
    return conn


@pytest.mark.asyncio
async def test_build_extraction_contract_assembles_from_rows() -> None:
    metric_rows = [
        {
            "metric_id": "ifrs:Assets", "name_en": "Total Assets", "name_id": "Total Aset",
            "label_bilingual": "Total Aset / Total Assets", "category": "BALANCE_SHEET",
            "sector_applicability": ["ALL"], "importance": "CRITICAL",
            "value_type": "MONETARY", "unit": "IDR", "statement_type": "BALANCE_SHEET",
            "extraction_mode": "EXTRACTED_RAW",
            "calculation_formula": None, "dependencies": [], "synonyms_id": ["Aset"],
            "synonyms_en": ["Assets"], "search_hints": ["Laporan Posisi Keuangan"],
            "extraction_guideline": "Extract total assets from Neraca.",
            "expected_segment_fields": [],
        },
        {
            "metric_id": "idx:LoansAndAdvances", "name_en": "Loans", "name_id": "Kredit",
            "label_bilingual": "Kredit yang Diberikan / Loans", "category": "BALANCE_SHEET",
            "sector_applicability": ["BANK"], "importance": "CRITICAL",
            "value_type": "MONETARY", "unit": "IDR", "statement_type": "BALANCE_SHEET",
            "extraction_mode": "EXTRACTED_RAW",
            "calculation_formula": None, "dependencies": [],
            "synonyms_id": ["Kredit yang Diberikan"], "synonyms_en": ["Loans"],
            "search_hints": ["Catatan Kredit yang Diberikan"],
            "extraction_guideline": None, "expected_segment_fields": ["segment", "type"],
        },
    ]
    module_rows = [
        {
            "sector_code": "BANK", "module_name": "BANK_LOANS_BY_SEGMENT",
            "typical_note_title": "Catatan Kredit per Segmen",
            "description": "Loans by segment",
            "target_concepts": ["idx:LoansAndAdvances"],
            "expected_segment_fields": ["segment", "type", "pct_total"],
            "guideline": "Extract each segment.", "is_mandatory": True,
        }
    ]
    narrative_rows = [
        {
            "topic": "Segment Operations & Revenue Drivers",
            "expected_section": "FOOTNOTE",
            "target_note_description": "Catatan Segmen",
            "guideline": "Explain segment moves.",
        }
    ]

    conn = _make_mock_conn(metric_rows, module_rows, narrative_rows)

    contract = await build_extraction_contract(
        conn,
        doc_id="doc_1",
        ticker="BMRI",
        company_name="PT Bank Mandiri (Persero) Tbk",
        sector="BANK",
        fiscal_period="2024Q4",
    )

    # Contract identity
    assert contract.doc_id == "doc_1"
    assert contract.ticker == "BMRI"
    assert contract.sector == "BANK"

    # Metrics assembled with new fields
    cids = {r.concept_id for r in contract.required_facts}
    assert "ifrs:Assets" in cids
    assert "idx:LoansAndAdvances" in cids

    loans = next(r for r in contract.required_facts if r.concept_id == "idx:LoansAndAdvances")
    assert loans.importance == "CRITICAL"
    assert loans.required is True  # CRITICAL always required
    assert "Catatan Kredit yang Diberikan" in loans.search_hints
    assert "Kredit yang Diberikan" in loans.synonyms_id

    # Granular modules
    assert len(contract.granular_note_modules) == 1
    assert contract.granular_note_modules[0].name == "BANK_LOANS_BY_SEGMENT"

    # Narratives
    assert len(contract.required_narratives) == 1
    assert contract.required_narratives[0].topic == "Segment Operations & Revenue Drivers"

    # Sector guidelines include the CRITICAL count line
    joined = "\n".join(contract.sector_specific_guidelines)
    assert "CRITICAL" in joined
    assert "BMRI" in joined


@pytest.mark.asyncio
async def test_build_extraction_contract_empty_sector_still_valid() -> None:
    """Unknown sector: still returns a well-formed empty contract."""
    conn = _make_mock_conn([], [], [])
    contract = await build_extraction_contract(
        conn,
        doc_id="doc_unknown",
        ticker="XXXX",
        company_name="Unknown Co",
        sector="UNKNOWN_SECTOR",
        fiscal_period="2024Q4",
    )
    assert contract.required_facts == []
    assert contract.granular_note_modules == []
    assert contract.required_narratives == []
    assert contract.sector == "UNKNOWN_SECTOR"
