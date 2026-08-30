"""Unit and mock tests for EMIMIND MCP Ingestion Server tools."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.mcp.server import (
    commit_verified_report,
    get_extraction_contract,
    get_issuer_context,
    inspect_document,
    submit_draft_extraction,
)
from services.mcp.types import DraftSubmissionPayload, ExtractedFactItem, InspectionStatus


@pytest.mark.asyncio
async def test_inspect_nonexistent_file() -> None:
    res = await inspect_document("/non/existent/path/report.pdf")
    assert res.status == InspectionStatus.ERROR
    assert "File not found" in res.message


@pytest.mark.asyncio
async def test_inspect_document_real_fixture() -> None:
    # Use real PDF fixture
    fixture_path = "tests/fixtures/sample_bmri.pdf"
    res = await inspect_document(fixture_path, ticker="BMRI", fiscal_period="2024Q4")
    assert res.status in (InspectionStatus.AUTHORIZED, InspectionStatus.ALREADY_PROCESSED)
    assert res.ticker == "BMRI"
    assert len(res.doc_hash) == 64


@pytest.mark.asyncio
async def test_mcp_submit_draft_extraction_and_commit() -> None:
    facts = [
        ExtractedFactItem(concept_id="ifrs:Assets", value_numeric=Decimal("2000000000000"), source_page=1),
        ExtractedFactItem(concept_id="ifrs:CurrentAssets", value_numeric=Decimal("800000000000"), source_page=1),
        ExtractedFactItem(concept_id="ifrs:NonCurrentAssets", value_numeric=Decimal("1200000000000"), source_page=1),
        ExtractedFactItem(concept_id="ifrs:Liabilities", value_numeric=Decimal("1500000000000"), source_page=2),
        ExtractedFactItem(concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("500000000000"), source_page=2),
        ExtractedFactItem(concept_id="ifrs:NonCurrentLiabilities", value_numeric=Decimal("1000000000000"), source_page=2),
        ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("500000000000"), source_page=2),
        ExtractedFactItem(concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("300000000000"), source_page=1),
        ExtractedFactItem(concept_id="ifrs:Revenue", value_numeric=Decimal("600000000000"), source_page=3),
        ExtractedFactItem(concept_id="ifrs:OperatingProfit", value_numeric=Decimal("200000000000"), source_page=3),
        ExtractedFactItem(concept_id="ifrs:ProfitLoss", value_numeric=Decimal("150000000000"), source_page=3),
        ExtractedFactItem(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("180000000000"), source_page=4),
        ExtractedFactItem(concept_id="idx:LoansAndAdvances", value_numeric=Decimal("1400000000000"), source_page=1),
        ExtractedFactItem(concept_id="idx:CustomerDeposits", value_numeric=Decimal("1300000000000"), source_page=2),
        ExtractedFactItem(concept_id="idx:NetInterestIncome", value_numeric=Decimal("250000000000"), source_page=3),
    ]

    payload = DraftSubmissionPayload(
        doc_id="3d3f701d-9cd6-4696-a11c-f85d23263454",
        ticker="BMRI",
        fiscal_period="2024Q4",
        facts=facts,
    )

    payload_json = json.dumps(payload.model_dump(mode="json"))

    # 1. Test validation endpoint
    val_rep = await submit_draft_extraction(payload_json)
    assert val_rep.status == "VALID"
    assert val_rep.errors_count == 0

    # 2. Test commit endpoint
    commit_rep = await commit_verified_report(payload_json)
    assert commit_rep.status == "COMMITTED"
    assert commit_rep.facts_committed == len(facts)
    assert commit_rep.derived_metrics_computed > 0
