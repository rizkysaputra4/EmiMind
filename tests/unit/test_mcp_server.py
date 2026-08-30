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
from services.mcp.types import (
    DraftSubmissionPayload,
    ExtractedCausalLink,
    ExtractedFactItem,
    ExtractedNarrativeItem,
    InspectionStatus,
)


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
    # 0. Ensure document exists via inspect
    insp = await inspect_document("tests/fixtures/sample_bmri.pdf", ticker="BMRI", fiscal_period="2024Q4")
    assert insp.doc_id is not None
    doc_id = insp.doc_id

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
        ExtractedFactItem(concept_id="idx:CASA", value_numeric=Decimal("950000000000"), source_page=2),
        ExtractedFactItem(concept_id="idx:NetInterestIncome", value_numeric=Decimal("250000000000"), source_page=3),
        ExtractedFactItem(concept_id="idx:NetInterestMargin", value_numeric=Decimal("5.35"), source_page=20),
        ExtractedFactItem(concept_id="idx:NonPerformingLoansGross", value_numeric=Decimal("15000000000"), source_page=22),
        ExtractedFactItem(concept_id="idx:CapitalAdequacyRatio", value_numeric=Decimal("21.5"), source_page=25),
        ExtractedFactItem(concept_id="idx:BOPO", value_numeric=Decimal("58.2"), source_page=26),
        ExtractedFactItem(concept_id="idx:CostOfCredit", value_numeric=Decimal("0.95"), source_page=26),
        ExtractedFactItem(concept_id="idx:LoanToDepositRatio", value_numeric=Decimal("84.2"), source_page=27),
        ExtractedFactItem(concept_id="idx:NPLCoverageRatio", value_numeric=Decimal("310.5"), source_page=28),
        # Granular Segmented Fact Items
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("400000000000"),
            source_page=15,
            segment={"segment": "Kredit Korporasi / Wholesale", "type": "product_segment", "pct_total": 66.7},
        ),
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("200000000000"),
            source_page=15,
            segment={"segment": "Kredit Ritel & Konsumer", "type": "product_segment", "pct_total": 33.3},
        ),
    ]

    narratives = [
        ExtractedNarrativeItem(
            section="MDA",
            text_original="PT Bank Mandiri (Persero) Tbk mencatatkan pertumbuhan penyaluran kredit...",
            text_en="PT Bank Mandiri (Persero) Tbk recorded loan growth...",
            source_page=10,
            topic="Loan Growth Review",
        )
    ]

    causal_links = [
        ExtractedCausalLink(
            metric_affected="idx:NetInterestIncome",
            direction="INCREASED",
            cause_category="VOLUME_GROWTH",
            driver_description="Pertumbuhan volume kredit wholesale dan retail mendorong peningkatan pendapatan bunga bersih.",
            source_page=10,
            confidence=0.95,
        )
    ]

    payload = DraftSubmissionPayload(
        doc_id=doc_id,
        ticker="BMRI",
        fiscal_period="2024Q4",
        facts=facts,
        narratives=narratives,
        causal_links=causal_links,
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
    assert commit_rep.narratives_committed == 1
    assert commit_rep.derived_metrics_computed > 0


@pytest.mark.asyncio
async def test_get_metric_ontology():
    from services.mcp.server import get_metric_ontology

    # Query banking metrics
    res = await get_metric_ontology(sector="BANK")
    assert res.total_found > 0
    concept_ids = [m.metric_id for m in res.metrics]
    assert "idx:LoansAndAdvances" in concept_ids or "ifrs:Revenue" in concept_ids

    # Query specific search keyword
    query_res = await get_metric_ontology(query="CASA")
    assert query_res.total_found > 0
    assert any("CASA" in m.name_en or "CASA" in m.metric_id for m in query_res.metrics)


@pytest.mark.asyncio
async def test_submit_discovered_metric():
    from services.mcp.server import submit_discovered_metric
    from services.mcp.types import DiscoveredMetricCandidate

    cand = DiscoveredMetricCandidate(
        metric_id="idx:GeothermalGenerationGWh",
        name_en="Geothermal Net Generation",
        name_id="Produksi Listrik Geotermal Neto",
        category="OPERATIONAL",
        sector_code="RENEWABLE_ENERGY",
        importance="HIGH",
        value_type="FLOAT",
        unit="GWH",
        source_page=42,
        sample_text="Total produksi listrik neto dari PLTP Wayang Windu dan Salak mencapai 2.450 GWh.",
        synonyms_id=["Produksi Listrik Bersih", "Net Power Generation"],
    )

    res = await submit_discovered_metric(cand)
    assert res.status in ("PROMOTED", "EXISTING")
    assert res.metric_id == "idx:GeothermalGenerationGWh"

