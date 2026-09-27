"""Unit and mock tests for EMIMIND MCP Ingestion Server tools."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.mcp.server import (
    commit_verified_report,
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
from tests.fixtures.m9.build_fixtures import build_fs_small


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
        ExtractedFactItem(concept_id="ifrs:Assets", value_numeric=Decimal("2000000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CurrentAssets", value_numeric=Decimal("800000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:NonCurrentAssets", value_numeric=Decimal("1200000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Liabilities", value_numeric=Decimal("1500000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("500000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:NonCurrentLiabilities", value_numeric=Decimal("1000000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("500000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("300000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Revenue", value_numeric=Decimal("600000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:OperatingProfit", value_numeric=Decimal("200000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:ProfitLoss", value_numeric=Decimal("150000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("180000000000"), source_page=4, statement="CF"),
        ExtractedFactItem(concept_id="ifrs:EquityAttributableToOwnersOfParent", value_numeric=Decimal("480000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:ProfitLossAttributableToOwnersOfParent", value_numeric=Decimal("145000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="idx:Capex", value_numeric=Decimal("40000000000"), source_page=4, statement="CF"),
        ExtractedFactItem(concept_id="idx:LoansAndAdvances", value_numeric=Decimal("1400000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="idx:CustomerDeposits", value_numeric=Decimal("1300000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="idx:CASA", value_numeric=Decimal("950000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="idx:NetInterestIncome", value_numeric=Decimal("250000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="idx:NetInterestMargin", value_numeric=Decimal("5.35"), source_page=20, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:NonPerformingLoansGross", value_numeric=Decimal("15000000000"), source_page=22, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CapitalAdequacyRatio", value_numeric=Decimal("21.5"), source_page=25, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:BOPO", value_numeric=Decimal("58.2"), source_page=26, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CostOfCredit", value_numeric=Decimal("0.95"), source_page=26, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:LoanToDepositRatio", value_numeric=Decimal("84.2"), source_page=27, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:NPLCoverageRatio", value_numeric=Decimal("310.5"), source_page=28, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:ReturnOnAssetsBank", value_numeric=Decimal("3.15"), source_page=25, statement="NOTE"),
        # Granular Segmented Fact Items
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("400000000000"),
            source_page=15,
            statement="IS",
            segment={"segment": "Kredit Korporasi / Wholesale", "type": "product_segment", "pct_total": 66.7},
        ),
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("200000000000"),
            source_page=15,
            statement="IS",
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
async def test_get_metric_ontology() -> None:
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
async def test_submit_discovered_metric() -> None:
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


@pytest.mark.asyncio
async def test_segmented_facts_order_and_alias_validation() -> None:
    """Verify that segmented facts before or after unsegmented facts do not break math equations."""
    from services.mcp.types import DraftSubmissionPayload, ExtractedFactItem
    from services.mcp.validator import validate_draft_submission
    from tests.unit._mcp_contract_fixtures import make_test_contract

    contract = make_test_contract("CPO", doc_id="doc_1", ticker="LSIP", fiscal_period="2025FY")
    required_cids = {r.concept_id for r in contract.required_facts}
    assert "idx:MaturePlantedArea" in required_cids
    assert "idx:FfbProduction" in required_cids
    assert "idx:CPOProductionVolume" in required_cids

    # Segmented facts placed BEFORE unsegmented facts
    facts = [
        # Segmented revenue first
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("4000000000"),
            source_page=10,
            statement="IS",
            segment={"segment": "CPO", "type": "product"},
        ),
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("1000000000"),
            source_page=10,
            statement="IS",
            segment={"segment": "PK", "type": "product"},
        ),
        # Unsegmented Core Facts
        ExtractedFactItem(concept_id="ifrs:Assets", value_numeric=Decimal("10000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CurrentAssets", value_numeric=Decimal("4000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:NonCurrentAssets", value_numeric=Decimal("6000000000"), source_page=1, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Liabilities", value_numeric=Decimal("3000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("1000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:NonCurrentLiabilities", value_numeric=Decimal("2000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("7000000000"), source_page=2, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("2000000000"), source_page=1, statement="BS"),
        # Total Revenue (5,000,000,000)
        ExtractedFactItem(concept_id="ifrs:Revenue", value_numeric=Decimal("5000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:CostOfSales", value_numeric=Decimal("3000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:GrossProfit", value_numeric=Decimal("2000000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:OperatingProfit", value_numeric=Decimal("1500000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:ProfitLoss", value_numeric=Decimal("1200000000"), source_page=3, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("1800000000"), source_page=4, statement="CF"),
        # CPO specific facts (testing alias idx:CpoProduction vs idx:CPOProductionVolume)
        ExtractedFactItem(concept_id="idx:MaturePlantedArea", value_numeric=Decimal("90000"), unit="HECTARES", source_page=5, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:FfbProduction", value_numeric=Decimal("1000000"), unit="TONNES", source_page=5, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CpoProduction", value_numeric=Decimal("250000"), unit="TONNES", source_page=5, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:OilExtractionRate", value_numeric=Decimal("22.5"), unit="PERCENT", source_page=5, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CPOAveragePriceASP", value_numeric=Decimal("12500"), unit="IDR_PER_KG", source_page=5, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CPOCashCostPerKg", value_numeric=Decimal("6500"), unit="IDR_PER_KG", source_page=5, statement="NOTE"),
    ]

    payload = DraftSubmissionPayload(
        doc_id="doc_1",
        ticker="LSIP",
        fiscal_period="2025FY",
        facts=facts,
    )

    report = validate_draft_submission(payload, contract=contract, sector="CPO")
    assert report.status == "VALID", f"Validation failed with issues: {report.issues}"
    assert report.errors_count == 0


@pytest.mark.asyncio
async def test_inspect_document_real_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "XXXX_2025_TW2_RDF_x.pdf"
    build_fs_small(pdf_path)

    insert_executed = False
    insert_params: dict[str, Any] = {}

    class MockResult:
        def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
            self._data = data or []

        def mappings(self) -> MockResult:
            return self

        def first(self) -> dict[str, Any] | None:
            return self._data[0] if self._data else None

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> MockResult:
        nonlocal insert_executed, insert_params
        sql_str = str(sql)
        if "FROM documents WHERE doc_hash" in sql_str:
            return MockResult([])
        if "FROM issuer_profile WHERE ticker" in sql_str:
            return MockResult([{"name": "PT XXXX Tbk", "sector": "BANK", "sub_sector": "BANK"}])
        if "INSERT INTO documents" in sql_str:
            insert_executed = True
            insert_params = params or {}
            return MockResult([])
        return MockResult([])

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = mock_execute
    mock_conn.commit = AsyncMock()

    class MockConnectCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_conn

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_engine = MagicMock()
    mock_engine.connect.return_value = MockConnectCtx()

    with patch("services.mcp.server.get_engine", return_value=mock_engine):
        res = await inspect_document(str(pdf_path), ticker="XXXX")

    assert res.status == InspectionStatus.AUTHORIZED
    assert res.fiscal_period == "2025Q2"
    assert insert_executed is True
    assert insert_params["period_end"] == date(2025, 6, 30)
    assert insert_params["page_count"] == 8
    assert insert_params["fiscal_period"] == "2025Q2"


@pytest.mark.asyncio
async def test_inspect_document_needs_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "random_scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy content")

    insert_executed = False

    class MockResult:
        def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
            self._data = data or []

        def mappings(self) -> MockResult:
            return self

        def first(self) -> dict[str, Any] | None:
            return self._data[0] if self._data else None

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> MockResult:
        nonlocal insert_executed
        sql_str = str(sql)
        if "INSERT INTO documents" in sql_str:
            insert_executed = True
        return MockResult([])

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = mock_execute
    mock_conn.commit = AsyncMock()

    class MockConnectCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_conn

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_engine = MagicMock()
    mock_engine.connect.return_value = MockConnectCtx()

    with (
        patch("services.mcp.server.get_engine", return_value=mock_engine),
        patch("services.extraction.metadata_extractor.propose_metadata", new=AsyncMock(return_value=None)),
    ):
        res = await inspect_document(str(pdf_path))

    assert res.status == InspectionStatus.NEEDS_METADATA
    assert insert_executed is False
    assert "Please call inspect_document again passing fiscal_period explicitly" in res.message


@pytest.mark.asyncio
async def test_commit_no_invented_segment() -> None:
    insert_params = None

    class MockResult:
        def mappings(self) -> MockResult:
            return self

        def first(self) -> dict[str, Any] | None:
            return None

        def fetchall(self) -> list[Any]:
            return []

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> MockResult:
        nonlocal insert_params
        if "INSERT INTO financial_facts" in str(sql):
            insert_params = params
        return MockResult()

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = mock_execute
    mock_conn.commit = AsyncMock()

    class MockConnectCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_conn

        async def __aexit__(self, *args: Any) -> None:
            pass

    mock_engine = MagicMock()
    mock_engine.connect.return_value = MockConnectCtx()

    payload = DraftSubmissionPayload(
        doc_id="doc_test_1",
        ticker="LSIP",
        fiscal_period="2024Q4",
        facts=[
            ExtractedFactItem(
                concept_id="idx:CostOfGoodsSoldComponent",
                value_numeric=Decimal("123000000"),
                source_page=15,
                statement="IS",
                source_label_original="Beban pupuk",
                segment=None,
            )
        ],
    )
    with (
        patch("services.mcp.server.get_engine", return_value=mock_engine),
        patch("services.mcp.server.compute_for_document", return_value=MagicMock(computed=0)),
        patch("services.mcp.server.refresh_profile_task", return_value=None),
        patch("services.mcp.server.calculate_valuation", return_value={}),
    ):
        res = await commit_verified_report(payload.model_dump_json())

    assert res.status == "COMMITTED"
    assert insert_params is not None
    assert insert_params["seg"] is None


@pytest.mark.asyncio
async def test_commit_cashflow_statement_and_period_type() -> None:
    insert_params = None

    class MockResult:
        def mappings(self) -> MockResult:
            return self

        def first(self) -> dict[str, Any] | None:
            return None

        def fetchall(self) -> list[Any]:
            return [("ifrs:CashFlowsFromUsedInOperatingActivities", "FLOW_PERIOD")]

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> MockResult:
        nonlocal insert_params
        if "INSERT INTO financial_facts" in str(sql):
            insert_params = params
        return MockResult()

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = mock_execute
    mock_conn.commit = AsyncMock()

    class MockConnectCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_conn

        async def __aexit__(self, *args: Any) -> None:
            pass

    mock_engine = MagicMock()
    mock_engine.connect.return_value = MockConnectCtx()

    payload = DraftSubmissionPayload(
        doc_id="doc_test_2",
        ticker="BMRI",
        fiscal_period="2024Q4",
        facts=[
            ExtractedFactItem(
                concept_id="ifrs:CashFlowsFromOperatingActivities",
                value_numeric=Decimal("500000000"),
                source_page=4,
                statement="CF",
            )
        ],
    )
    with (
        patch("services.mcp.server.get_engine", return_value=mock_engine),
        patch("services.mcp.server.compute_for_document", return_value=MagicMock(computed=0)),
        patch("services.mcp.server.refresh_profile_task", return_value=None),
        patch("services.mcp.server.calculate_valuation", return_value={}),
    ):
        res = await commit_verified_report(payload.model_dump_json())

    assert res.status == "COMMITTED"
    assert insert_params is not None
    assert insert_params["statement"] == "CF"
    assert insert_params["period_type"] == "duration_ytd"


@pytest.mark.asyncio
async def test_commit_invalid_fiscal_period_rejects() -> None:
    insert_executed = False

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> Any:
        nonlocal insert_executed
        if "INSERT INTO" in str(sql):
            insert_executed = True
        return MagicMock()

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = mock_execute

    payload = DraftSubmissionPayload(
        doc_id="doc_test_3",
        ticker="BMRI",
        fiscal_period="XXXX",
        facts=[
            ExtractedFactItem(
                concept_id="ifrs:Assets",
                value_numeric=Decimal("100"),
                source_page=1,
                statement="BS",
            )
        ],
    )
    res = await commit_verified_report(payload.model_dump_json())
    assert res.status == "ERROR"
    assert res.facts_committed == 0
    assert insert_executed is False


@pytest.mark.asyncio
async def test_commit_persists_bbox() -> None:
    insert_params = None

    class MockResult:
        def mappings(self) -> MockResult:
            return self

        def first(self) -> dict[str, Any] | None:
            return None

        def fetchall(self) -> list[Any]:
            return []

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> MockResult:
        nonlocal insert_params
        if "INSERT INTO financial_facts" in str(sql):
            insert_params = params
        return MockResult()

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = mock_execute
    mock_conn.commit = AsyncMock()

    class MockConnectCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_conn

        async def __aexit__(self, *args: Any) -> None:
            pass

    mock_engine = MagicMock()
    mock_engine.connect.return_value = MockConnectCtx()

    test_bbox = [10.5, 20.0, 100.2, 50.8]
    payload = DraftSubmissionPayload(
        doc_id="doc_test_4",
        ticker="BMRI",
        fiscal_period="2024Q4",
        facts=[
            ExtractedFactItem(
                concept_id="ifrs:Assets",
                value_numeric=Decimal("2000000000000"),
                source_page=1,
                statement="BS",
                bbox=test_bbox,
            )
        ],
    )
    with (
        patch("services.mcp.server.get_engine", return_value=mock_engine),
        patch("services.mcp.server.compute_for_document", return_value=MagicMock(computed=0)),
        patch("services.mcp.server.refresh_profile_task", return_value=None),
        patch("services.mcp.server.calculate_valuation", return_value={}),
    ):
        res = await commit_verified_report(payload.model_dump_json())

    assert res.status == "COMMITTED"
    assert insert_params is not None
    assert insert_params["source_bbox"] == json.dumps(test_bbox)




