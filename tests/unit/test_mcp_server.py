"""Unit and mock tests for EMIMIND MCP Ingestion Server tools.

No test here opens a real database connection (tests/unit/conftest.py forbids it): every DB
interaction goes through `FakeDB`, which routes SQL by substring to canned rows and records
every statement, so INSERT parameters can be asserted.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.mcp.server import (
    commit_verified_report,
    get_routed_pages,
    inspect_document,
    submit_draft_extraction,
)
from services.mcp.types import (
    CellRef,
    DraftSubmissionPayload,
    ExtractedCausalLink,
    ExtractedFactItem,
    ExtractedGuidanceItem,
    ExtractedNarrativeItem,
    InspectionStatus,
    ProcessingUsage,
    RoutedPages,
    ValidationReport,
)
from tests.fixtures.m9.build_fixtures import build_fs_small
from tests.unit._mcp_contract_fixtures import make_test_contract, render_page_text

# ---------------------------------------------------------------------------
# Fake database
# ---------------------------------------------------------------------------

Rows = list[dict[str, Any]]


class FakeResult:
    def __init__(self, rows: Rows | None = None) -> None:
        self.rows = rows or []

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> Rows:
        return list(self.rows)

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return [tuple(r.values()) for r in self.rows]

    def __iter__(self) -> Any:
        return iter(self.rows)

    def scalar(self) -> Any:
        return next(iter(self.rows[0].values())) if self.rows else None

    def scalar_one(self) -> Any:
        return self.scalar()


class FakeDB:
    """Routes SQL to canned rows by substring (first match wins) and records every call."""

    def __init__(self, routes: dict[str, Rows | Callable[[dict[str, Any]], Rows]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._ids = 0
        self.conn = AsyncMock()
        self.conn.execute.side_effect = self._execute
        self.conn.commit = AsyncMock()
        self.conn.rollback = AsyncMock()
        db = self

        class _Ctx:
            async def __aenter__(self) -> AsyncMock:
                return db.conn

            async def __aexit__(self, *args: Any) -> None:
                return None

        self.engine = MagicMock()
        self.engine.connect.side_effect = _Ctx

    async def _execute(self, sql: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql_str = str(sql)
        self.calls.append((sql_str, params or {}))
        for key, value in self.routes.items():
            if key in sql_str:
                return FakeResult(value(params or {}) if callable(value) else value)
        if "RETURNING" in sql_str:
            self._ids += 1
            return FakeResult([{"id": self._ids}])
        return FakeResult([])

    def inserts(self, table: str) -> list[dict[str, Any]]:
        return [p for sql, p in self.calls if f"INSERT INTO {table}" in sql]

    def sql_of(self, table: str) -> list[str]:
        return [sql for sql, _p in self.calls if f"INSERT INTO {table}" in sql]


def _page_rows(pages: dict[int, tuple[str, str]]) -> Callable[[dict[str, Any]], Rows]:
    """document_pages rows for the requested page indexes: {page: (text_source, text)}."""

    def rows(params: dict[str, Any]) -> Rows:
        wanted = params.get("pages") or list(pages)
        return [
            {"page_index": p, "text_source": src, "page_text": txt}
            for p, (src, txt) in pages.items()
            if p in wanted
        ]

    return rows


def extraction_db(
    pages: dict[int, tuple[str, str]],
    tables: Rows | None = None,
    *,
    indexed: bool = True,
    metric_rows: Rows | None = None,
    page_count: int = 10,
) -> FakeDB:
    return FakeDB(
        {
            "FROM peer_groups": [{"name": "PT Test Tbk", "sector": "GENERIC"}],
            "SELECT doc_type, page_count FROM documents": [{"doc_type": "FS_ANNUAL", "page_count": page_count}],
            "SELECT 1 FROM document_pages": [{"one": 1}] if indexed else [],
            "SELECT page_index, page_text FROM document_pages": [
                {"page_index": p, "page_text": t} for p, (_s, t) in pages.items()
            ],
            "SELECT page_index, text_source, page_text": _page_rows(pages),
            "FROM document_page_tables": tables or [],
            "FROM metric_definitions": metric_rows or [],
            "narrative_chunks n ON n.text_hash": [],
            "SELECT source_url FROM documents": [{"source_url": None}],
        }
    )


def _open_contract() -> Any:
    contract = make_test_contract("GENERIC")
    for r in contract.required_facts:
        r.required = False
        r.importance = "OPTIONAL"
    return contract


def _commit_patches(db: FakeDB, contract: Any | None = None) -> Any:
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("services.mcp.server.get_engine", return_value=db.engine))
    stack.enter_context(
        patch(
            "services.mcp.server.build_extraction_contract",
            new_callable=AsyncMock,
            return_value=contract or _open_contract(),
        )
    )
    stack.enter_context(patch("services.mcp.server._log_processing_event", new_callable=AsyncMock))
    stack.enter_context(
        patch("services.mcp.server.compute_for_document", new_callable=AsyncMock, return_value=MagicMock(computed=0))
    )
    stack.enter_context(patch("services.mcp.server.refresh_profile_task", new_callable=AsyncMock))
    stack.enter_context(patch("services.mcp.server.calculate_valuation", new_callable=AsyncMock, return_value={}))
    return stack


# A balance-sheet page laid out like an IDX filing: current column 1, prior column 2.
BS_TABLE: Rows = [
    {
        "page_index": 1,
        "table_index": 0,
        "extraction_method": "camelot_lattice",
        "confidence": 0.95,
        "unit_hint": "IDR_MN",
        "cells": [
            {"row": 0, "col": 1, "text": "31 Desember 2024", "value": None},
            {"row": 0, "col": 2, "text": "31 Desember 2023", "value": None},
            {"row": 1, "col": 0, "text": "Total aset", "value": None},
            {"row": 1, "col": 1, "text": "100.000", "value": 100000.0, "bbox": [310.0, 220.0, 360.0, 231.0], "confidence": 0.92},
            {"row": 1, "col": 2, "text": "90.000", "value": 90000.0, "bbox": [400.0, 220.0, 450.0, 231.0], "confidence": 0.92},
        ],
    }
]
BS_TEXT = (
    "PT TEST Tbk\nLAPORAN POSISI KEUANGAN\n(Disajikan dalam jutaan Rupiah)\n"
    "31 Desember 2024 31 Desember 2023\nTotal aset 100.000 90.000\n"
)
IS_TEXT = (
    "LAPORAN LABA RUGI\n(Disajikan dalam jutaan Rupiah)\n2024 2023\n"
    "Pendapatan 80.000 70.000\nLaba tahun berjalan 10.000 9.000\n"
)


def _fact(cid: str, value: str, page: int, stmt: str, label: str, **kw: Any) -> ExtractedFactItem:
    return ExtractedFactItem(
        concept_id=cid,
        value_numeric=Decimal(value),
        source_page=page,
        statement=stmt,  # type: ignore[arg-type]
        source_label_original=label,
        **kw,
    )


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inspect_nonexistent_file() -> None:
    res = await inspect_document("/non/existent/path/report.pdf")
    assert res.status == InspectionStatus.ERROR
    assert "File not found" in res.message


@pytest.mark.asyncio
async def test_inspect_document_real_fixture() -> None:
    db = FakeDB(
        {
            "FROM documents WHERE doc_hash": [],
            "FROM issuer_profile WHERE ticker": [{"name": "PT Bank Mandiri (Persero) Tbk", "sector": "BANK", "sub_sector": "BANK"}],
        }
    )
    with patch("services.mcp.server.get_engine", return_value=db.engine):
        res = await inspect_document("tests/fixtures/sample_bmri.pdf", ticker="BMRI", fiscal_period="2024Q4")
    assert res.status in (InspectionStatus.AUTHORIZED, InspectionStatus.ALREADY_PROCESSED), res.message
    assert res.ticker == "BMRI"
    assert len(res.doc_hash) == 64
    assert db.inserts("documents")


# ---------------------------------------------------------------------------
# Submit + commit end to end (mocked DB, realistic evidence)
# ---------------------------------------------------------------------------

MDA_SENTENCE = "Pendapatan naik 14% menjadi Rp80 miliar didorong volume penjualan CPO"


@pytest.mark.asyncio
async def test_mcp_submit_draft_extraction_and_commit() -> None:
    pages = {
        1: ("pdf_text", BS_TEXT),
        2: ("pdf_text", IS_TEXT),
        3: ("pdf_text", "DISKUSI DAN ANALISIS MANAJEMEN\n" + MDA_SENTENCE + ".\nTarget pertumbuhan pendapatan 2025 sebesar 10% sampai 12%."),
    }
    db = extraction_db(pages, BS_TABLE)
    payload = DraftSubmissionPayload(
        doc_id="doc-e2e",
        ticker="ASII",
        fiscal_period="2024Q4",
        facts=[
            _fact("ifrs:Assets", "100000000000", 1, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=1)),
            _fact("ifrs:Revenue", "80000000000", 2, "IS", "Pendapatan"),
            _fact("ifrs:ProfitLoss", "10000000000", 2, "IS", "Laba tahun berjalan"),
        ],
        narratives=[ExtractedNarrativeItem(section="MDA", text_original=MDA_SENTENCE, source_page=3)],
        causal_links=[
            ExtractedCausalLink(
                metric_affected="ifrs:Revenue", direction="INCREASED", cause_category="VOLUME_GROWTH",
                driver_description="Volume penjualan CPO", source_page=3,
            )
        ],
        guidance=[
            ExtractedGuidanceItem(
                metric="ifrs:Revenue", target_period="2025Q4", target_low=Decimal("10"), target_high=Decimal("12"),
                unit="PERCENT", source_page=3, context_statement="Target pertumbuhan pendapatan 2025 sebesar 10% sampai 12%.",
            )
        ],
    )
    payload_json = json.dumps(payload.model_dump(mode="json"))

    with _commit_patches(db):
        val_rep = await submit_draft_extraction(payload_json)
        assert val_rep.status == "VALID", val_rep.issues
        commit_rep = await commit_verified_report(payload_json)

    assert commit_rep.status == "COMMITTED", commit_rep.message
    assert commit_rep.facts_committed == 3
    assert commit_rep.narratives_committed == 1
    assert commit_rep.guidance_committed == 1
    facts = db.inserts("financial_facts")
    assert [f["grounding"] for f in facts] == ["cell", "text", "text"]
    guidance = [p for sql, p in db.calls if "'GUIDANCE'" in sql]
    assert json.loads(guidance[0]["payload"])["qualifier"] == "range"


@pytest.mark.asyncio
async def test_submit_unindexed_document_is_invalid() -> None:
    db = extraction_db({}, indexed=False)
    payload = DraftSubmissionPayload(
        doc_id="doc-unindexed", ticker="ASII", fiscal_period="2024Q4",
        facts=[_fact("ifrs:Assets", "100000000000", 1, "BS", "Total aset")],
    )
    with _commit_patches(db):
        rep = await submit_draft_extraction(payload.model_dump_json())
    assert rep.status == "INVALID"
    assert any(i.category == "DOCUMENT_NOT_INDEXED" for i in rep.issues)


@pytest.mark.asyncio
async def test_commit_unindexed_document_rejected_no_insert() -> None:
    db = extraction_db({}, indexed=False)
    payload = DraftSubmissionPayload(
        doc_id="doc-unindexed", ticker="ASII", fiscal_period="2024Q4",
        facts=[_fact("ifrs:Assets", "100000000000", 1, "BS", "Total aset")],
    )
    with _commit_patches(db):
        rep = await commit_verified_report(payload.model_dump_json())
    assert rep.status == "REJECTED_VALIDATION_FAILED"
    assert "page index" in rep.message
    assert not db.inserts("financial_facts")


@pytest.mark.asyncio
async def test_evidence_load_failure_is_not_a_bypass() -> None:
    db = extraction_db({1: ("pdf_text", BS_TEXT)}, BS_TABLE)

    def boom(_params: dict[str, Any]) -> Rows:
        raise RuntimeError("connection reset")

    db.routes["FROM document_page_tables"] = boom
    payload = DraftSubmissionPayload(
        doc_id="doc-err", ticker="ASII", fiscal_period="2024Q4",
        facts=[_fact("ifrs:Assets", "100000000000", 1, "BS", "Total aset")],
    )
    with _commit_patches(db):
        rep = await commit_verified_report(payload.model_dump_json())
    assert rep.status == "REJECTED_VALIDATION_FAILED"
    assert not db.inserts("financial_facts")


# ---------------------------------------------------------------------------
# Ontology tools (mocked)
# ---------------------------------------------------------------------------

_ONTOLOGY_ROWS: Rows = [
    {
        "metric_id": "idx:LoansAndAdvances", "name_en": "Total Loans and Advances (Gross)",
        "name_id": "Total Kredit yang Diberikan (Gross)", "category": "BALANCE_SHEET",
        "sector_applicability": ["BANK"], "importance": "CRITICAL", "value_type": "MONETARY", "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "calculation_formula": None,
        "dependencies": [], "source_priority": [], "synonyms_id": ["Kredit yang Diberikan"], "synonyms_en": [],
    },
    {
        "metric_id": "idx:CASA", "name_en": "CASA (Current and Savings Account)", "name_id": "Dana Murah (CASA)",
        "category": "BALANCE_SHEET", "sector_applicability": ["BANK"], "importance": "HIGH", "value_type": "MONETARY",
        "unit": "IDR", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW",
        "calculation_formula": None, "dependencies": [], "source_priority": [], "synonyms_id": [], "synonyms_en": [],
    },
]


@pytest.mark.asyncio
async def test_get_metric_ontology() -> None:
    from services.mcp.server import get_metric_ontology

    def rows(params: dict[str, Any]) -> Rows:
        q = str(params.get("q", "")).strip("%").lower()
        return [r for r in _ONTOLOGY_ROWS if not q or q in r["metric_id"].lower() or q in r["name_en"].lower()]

    db = FakeDB({"FROM metric_definitions": rows})
    with patch("services.mcp.server.get_engine", return_value=db.engine):
        res = await get_metric_ontology(sector="BANK")
        query_res = await get_metric_ontology(query="CASA")
    assert res.total_found == 2
    assert "idx:LoansAndAdvances" in [m.metric_id for m in res.metrics]
    assert query_res.total_found == 1
    assert query_res.metrics[0].metric_id == "idx:CASA"
    assert any(p.get("sec") == "BANK" for _sql, p in db.calls)


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
    new_db = FakeDB({"SELECT metric_id, name_en FROM metric_definitions": []})
    with patch("services.mcp.server.get_engine", return_value=new_db.engine):
        res = await submit_discovered_metric(cand)
    assert res.status == "PROMOTED"
    assert res.metric_id == "idx:GeothermalGenerationGWh"
    assert new_db.inserts("metric_definitions")[0]["id"] == "idx:GeothermalGenerationGWh"

    existing_db = FakeDB({"SELECT metric_id, name_en FROM metric_definitions": [{"metric_id": cand.metric_id, "name_en": cand.name_en}]})
    with patch("services.mcp.server.get_engine", return_value=existing_db.engine):
        res2 = await submit_discovered_metric(cand)
    assert res2.status == "EXISTING"
    assert not existing_db.inserts("metric_definitions")


# ---------------------------------------------------------------------------
# Validator (pure) on a plantation contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_segmented_facts_order_and_alias_validation() -> None:
    """Segmented facts before or after unsegmented facts do not break math equations; aliases count."""
    from services.mcp.validator import validate_draft_submission
    from tests.unit._mcp_contract_fixtures import render_evidence

    contract = make_test_contract("CPO", doc_id="doc_1", ticker="LSIP", fiscal_period="2025FY")
    required_cids = {r.concept_id for r in contract.required_facts}
    assert {"idx:MaturePlantedArea", "idx:FfbProduction", "idx:CPOProductionVolume"} <= required_cids

    def op(cid: str, value: str, label: str, unit: str) -> ExtractedFactItem:
        return _fact(cid, value, 5, "NOTE", label, unit=unit, period_type="duration_ytd")

    facts = [
        _fact("ifrs:Revenue", "4000000000", 10, "NOTE", "CPO", period_type="duration_ytd", segment={"segment": "CPO", "type": "product"}),
        _fact("ifrs:Revenue", "1000000000", 10, "NOTE", "Inti sawit", period_type="duration_ytd", segment={"segment": "Inti sawit", "type": "product"}),
        _fact("ifrs:Assets", "10000000000", 1, "BS", "Total aset"),
        _fact("ifrs:CurrentAssets", "4000000000", 1, "BS", "Total aset lancar"),
        _fact("ifrs:NonCurrentAssets", "6000000000", 1, "BS", "Total aset tidak lancar"),
        _fact("ifrs:Liabilities", "3000000000", 2, "BS", "Total liabilitas"),
        _fact("ifrs:CurrentLiabilities", "1000000000", 2, "BS", "Total liabilitas jangka pendek"),
        _fact("ifrs:NonCurrentLiabilities", "2000000000", 2, "BS", "Total liabilitas jangka panjang"),
        _fact("ifrs:Equity", "7000000000", 2, "BS", "Total ekuitas"),
        _fact("ifrs:CashAndCashEquivalents", "2000000000", 1, "BS", "Kas dan setara kas"),
        _fact("ifrs:Revenue", "5000000000", 3, "IS", "Pendapatan"),
        _fact("ifrs:CostOfSales", "3000000000", 3, "IS", "Beban pokok penjualan"),
        _fact("ifrs:GrossProfit", "2000000000", 3, "IS", "Laba bruto"),
        _fact("ifrs:OperatingProfit", "1500000000", 3, "IS", "Laba usaha"),
        _fact("ifrs:ProfitLoss", "1200000000", 3, "IS", "Laba tahun berjalan"),
        _fact("ifrs:CashFlowsFromUsedInOperatingActivities", "1800000000", 4, "CF", "Kas neto dari aktivitas operasi"),
        _fact("idx:MaturePlantedArea", "90000", 5, "NOTE", "Tanaman menghasilkan", unit="HECTARES", period_type="instant"),
        op("idx:FfbProduction", "1000000", "Produksi TBS", "TONNES"),
        op("idx:CpoProduction", "250000", "Produksi CPO", "TONNES"),
        op("idx:OilExtractionRate", "22.5", "Rendemen minyak sawit", "PERCENT"),
        op("idx:CPOAveragePriceASP", "12500", "Harga jual rata-rata CPO", "IDR_PER_KG"),
        op("idx:CPOCashCostPerKg", "6500", "Biaya kas per kg CPO", "IDR_PER_KG"),
    ]
    # Revenue segments: CPO 4.000 + Inti sawit 1.000 on the note page, which also prints the total.
    evidence = render_evidence(facts, extra={10: "Total pendapatan 5.000"})
    payload = DraftSubmissionPayload(doc_id="doc_1", ticker="LSIP", fiscal_period="2025FY", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="CPO", evidence=evidence, page_count=20)
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
async def test_get_routed_pages_schema_and_tables() -> None:
    from services.retrieval.page_router import RoutedSpan

    class MockResult:
        def __init__(self, data: list[dict[str, Any]]) -> None:
            self._data = data

        def mappings(self) -> MockResult:
            return self

        def first(self) -> dict[str, Any] | None:
            return self._data[0] if self._data else None

        def all(self) -> list[dict[str, Any]]:
            return self._data

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> MockResult:
        sql_str = str(sql)
        if "FROM documents WHERE id = :id" in sql_str:
            return MockResult([{"id": "doc-uuid-1", "ticker": "BMRI", "fiscal_period": "2024Q4", "doc_type": "ANNUAL"}])
        if "FROM issuer_profile WHERE ticker = :ticker" in sql_str:
            return MockResult([{"sector": "BANK"}])
        if "FROM document_pages" in sql_str:
            return MockResult([
                {"page_index": 2, "page_label": "2", "text_source": "pdf_text", "page_text": "Jumlah aset Rp 12.345", "image_key": "raw/p2.png"},
                {"page_index": 3, "page_label": "3", "text_source": "pdf_text", "page_text": "Lanjutan", "image_key": None},
            ])
        if "FROM document_page_tables" in sql_str:
            return MockResult([
                {
                    "page_index": 2,
                    "table_index": 0,
                    "extraction_method": "pdfplumber",
                    "confidence": 0.95,
                    "unit_hint": "jutaan rupiah",
                    "cells": [
                        {
                            "row": 0,
                            "col": 0,
                            "text": "Total Assets",
                            "value": 12345.0,
                            "bbox": [10.0, 20.0, 30.0, 40.0],
                            "confidence": 0.95,
                        }
                    ],
                }
            ])
        return MockResult([])

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

    mock_spans = [RoutedSpan(start_page=2, end_page=3, score=0.045, seed_page=2, pages=[2, 3])]

    with (
        patch("services.mcp.server.get_engine", return_value=mock_engine),
        patch("services.mcp.server.route_pages", new_callable=AsyncMock, return_value=mock_spans),
        patch("services.mcp.server.get_minio") as mock_get_minio,
    ):
        mock_minio = MagicMock()
        mock_minio.presigned_get_object.return_value = "https://minio.local/p2.png"
        mock_get_minio.return_value = mock_minio

        res = await get_routed_pages("doc-uuid-1", "BALANCE_SHEET", include_images=True)

    assert isinstance(res, RoutedPages)
    assert res.doc_id == "doc-uuid-1"
    assert res.module == "BALANCE_SHEET"
    assert res.total_pages_returned == 2
    assert len(res.pages) == 2
    assert res.spans == [[2, 3]]

    p2 = res.pages[0]
    assert p2.page_index == 2
    assert p2.image_url == "https://minio.local/p2.png"
    assert len(p2.tables) == 1
    t0 = p2.tables[0]
    assert t0.table_index == 0
    # served as a text grid; value and bbox stay server-side (resolved from cell_ref)
    assert t0.rows == [["Total Assets"]]
    assert "bbox" not in t0.model_dump_json()


@pytest.mark.asyncio
async def test_get_routed_pages_unknown_module() -> None:
    class MockResult:
        def mappings(self) -> MockResult:
            return self

        def first(self) -> dict[str, Any] | None:
            return {"id": "doc-uuid-1", "ticker": "BMRI", "fiscal_period": "2024Q4", "doc_type": "ANNUAL"}

    async def mock_execute(sql: Any, params: dict[str, Any] | None = None) -> MockResult:
        return MockResult()

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = mock_execute

    class MockConnectCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_conn

        async def __aexit__(self, *args: Any) -> None:
            pass

    mock_engine = MagicMock()
    mock_engine.connect.return_value = MockConnectCtx()

    with patch("services.mcp.server.get_engine", return_value=mock_engine):
        with pytest.raises(ValueError) as exc_info:
            await get_routed_pages("doc-uuid-1", "INVALID_MODULE_XYZ")

    err = str(exc_info.value)
    assert "Unknown module 'INVALID_MODULE_XYZ'" in err
    assert "BALANCE_SHEET" in err


# ---------------------------------------------------------------------------
# Commit path: what exactly is written
# ---------------------------------------------------------------------------


async def _commit(db: FakeDB, facts: list[ExtractedFactItem], **payload_kw: Any) -> Any:
    payload = DraftSubmissionPayload(doc_id="doc-test-1", ticker="ASII", fiscal_period="2024Q4", facts=facts, **payload_kw)
    with _commit_patches(db):
        return await commit_verified_report(json.dumps(payload.model_dump(mode="json")))


@pytest.mark.asyncio
async def test_commit_no_invented_segment() -> None:
    fact = _fact("idx:CostOfGoodsSoldComponent", "123000000", 15, "NOTE", "Beban pupuk", period_type="duration_ytd")
    db = extraction_db({15: ("pdf_text", render_page_text([fact], 15))}, page_count=20)
    rep = await _commit(db, [fact])
    assert rep.status == "COMMITTED", rep.message
    (ins,) = db.inserts("financial_facts")
    assert ins["seg"] is None
    assert ins["period_type"] == "duration_ytd"
    assert any("CONCEPT_NOT_IN_ONTOLOGY" in w for w in rep.warnings)


@pytest.mark.asyncio
async def test_commit_cashflow_statement_and_period_type() -> None:
    fact = _fact("ifrs:CashFlowsFromOperatingActivities", "500000000", 4, "CF", "Kas neto yang diperoleh dari aktivitas operasi")
    metric_rows = [
        {
            "metric_id": "ifrs:CashFlowsFromUsedInOperatingActivities", "name_id": "Arus Kas Bersih dari Aktivitas Operasi",
            "name_en": "Cash Flow from Operating Activities", "synonyms_id": ["Arus Kas Operasional"], "synonyms_en": [],
            "flow_stock_type": "FLOW_PERIOD", "unit": "IDR", "value_type": "MONETARY", "statement_type": "CASH_FLOW",
        }
    ]
    db = extraction_db({4: ("pdf_text", render_page_text([fact], 4))}, metric_rows=metric_rows)
    rep = await _commit(db, [fact])
    assert rep.status == "COMMITTED", rep.message
    (ins,) = db.inserts("financial_facts")
    assert ins["statement"] == "CF"
    assert ins["period_type"] == "duration_ytd"
    assert ins["grounding"] == "text"


@pytest.mark.asyncio
async def test_commit_on_conflict_uses_fact_identity_with_period_type() -> None:
    fact = _fact("ifrs:Revenue", "80000000000", 2, "IS", "Pendapatan")
    db = extraction_db({2: ("pdf_text", IS_TEXT)})
    await _commit(db, [fact])
    (sql,) = db.sql_of("financial_facts")
    assert "ON CONFLICT (ticker, fiscal_period, concept_id, period_type, (coalesce(segment, '{}'::jsonb)))" in sql


@pytest.mark.asyncio
async def test_commit_persists_agent_bbox_for_text_fact() -> None:
    test_bbox = [10.5, 20.0, 100.2, 50.8]
    fact = _fact("ifrs:Revenue", "80000000000", 2, "IS", "Pendapatan", bbox=test_bbox)
    db = extraction_db({2: ("pdf_text", IS_TEXT)})
    rep = await _commit(db, [fact])
    assert rep.status == "COMMITTED", rep.message
    assert db.inserts("financial_facts")[0]["source_bbox"] == json.dumps(test_bbox)


@pytest.mark.asyncio
async def test_commit_uses_grounding_params_table_parser_llm_extract_and_ocr() -> None:
    pages = {
        1: ("pdf_text", BS_TEXT),
        2: ("pdf_text", IS_TEXT),
        3: ("ocr", "LAPORAN LABA RUGI\nburam scan tanpa angka"),
    }
    db = extraction_db(pages, BS_TABLE)
    facts = [
        _fact("ifrs:Assets", "100000000000", 1, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=1)),
        _fact("ifrs:Revenue", "80000000000", 2, "IS", "Pendapatan"),
        _fact("ifrs:ProfitLoss", "10000000000", 3, "IS", "Laba tahun berjalan"),
    ]
    rep = await _commit(db, facts)
    assert rep.status == "COMMITTED", rep.message
    f1, f2, f3 = db.inserts("financial_facts")

    # 1. Cell-grounded: table_parser, min(table 0.95, cell 0.92), the cell's real bbox
    assert f1["method"] == "table_parser"
    assert f1["conf"] == 0.92
    assert f1["source_bbox"] == json.dumps([310.0, 220.0, 360.0, 231.0])
    assert f1["grounding"] == "cell"
    assert f1["needs_review"] is False
    # 2. Text-grounded
    assert (f2["method"], f2["conf"], f2["grounding"], f2["needs_review"]) == ("llm_extract", 0.75, "text", False)
    # 3. OCR page, number not confirmed
    assert (f3["method"], f3["conf"], f3["grounding"], f3["needs_review"]) == ("llm_extract", 0.65, "ocr_unverified", True)


@pytest.mark.asyncio
async def test_commit_min_table_confidence_and_synthetic_bbox_dropped() -> None:
    table = json.loads(json.dumps(BS_TABLE))
    table[0]["confidence"] = 0.8
    table[0]["cells"][3]["bbox"] = [0.0, 15.0, 500.0, 30.0]  # legacy synthesized row box
    db = extraction_db({1: ("pdf_text", BS_TEXT)}, table)
    fact = _fact("ifrs:Assets", "100000000000", 1, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=1))
    rep = await _commit(db, [fact])
    assert rep.status == "COMMITTED", rep.message
    (ins,) = db.inserts("financial_facts")
    assert ins["conf"] == 0.8
    assert ins["source_bbox"] is None


@pytest.mark.asyncio
async def test_commit_fails_grounding_rejected_no_insert() -> None:
    db = extraction_db({1: ("pdf_text", BS_TEXT)}, BS_TABLE)
    bad = _fact("ifrs:Assets", "999999999999", 1, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=1))
    rep = await _commit(db, [bad])
    assert rep.status == "REJECTED_VALIDATION_FAILED"
    assert rep.facts_committed == 0
    assert not db.inserts("financial_facts")


@pytest.mark.asyncio
async def test_commit_prior_year_cell_rejected() -> None:
    db = extraction_db({1: ("pdf_text", BS_TEXT)}, BS_TABLE)
    prior = _fact("ifrs:Assets", "90000000000", 1, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=2))
    rep = await _commit(db, [prior])
    assert rep.status == "REJECTED_VALIDATION_FAILED"
    assert "column" in rep.message
    assert not db.inserts("financial_facts")


@pytest.mark.asyncio
async def test_commit_without_narratives_stores_none() -> None:
    """The old auto-chunk fallback (chunking the whole PDF into narratives) is gone."""
    db = extraction_db({2: ("pdf_text", IS_TEXT)})
    rep = await _commit(db, [_fact("ifrs:Revenue", "80000000000", 2, "IS", "Pendapatan")])
    assert rep.status == "COMMITTED", rep.message
    assert rep.narratives_committed == 0
    assert not db.inserts("narrative_chunks")


@pytest.mark.asyncio
async def test_commit_narrative_dedupe_counts_only_inserted_rows() -> None:
    page = "DISKUSI DAN ANALISIS\n" + MDA_SENTENCE + "."
    db = extraction_db({2: ("pdf_text", IS_TEXT), 3: ("pdf_text", page)})
    # The unique (source_doc_id, text_hash) index swallowed the insert: RETURNING gives no row.
    db.routes = {"INSERT INTO narrative_chunks": [], **db.routes}
    narr = ExtractedNarrativeItem(section="MDA", text_original=MDA_SENTENCE, source_page=3)
    rep = await _commit(db, [_fact("ifrs:Revenue", "80000000000", 2, "IS", "Pendapatan")], narratives=[narr, narr])
    assert rep.status == "COMMITTED", rep.message
    assert len(db.inserts("narrative_chunks")) == 1  # in-payload duplicate skipped before SQL
    assert "ON CONFLICT (source_doc_id, text_hash) DO NOTHING" in db.sql_of("narrative_chunks")[0]
    assert rep.narratives_committed == 0


@pytest.mark.asyncio
async def test_submit_cross_issuer_lookup_is_by_hash() -> None:
    from services.mcp.narrative_checks import narrative_md5

    page = "DISKUSI DAN ANALISIS\n" + MDA_SENTENCE + "."
    db = extraction_db({3: ("pdf_text", page)})
    db.routes["narrative_chunks n ON n.text_hash"] = [{"ord": 1, "ticker": "AALI"}]
    payload = DraftSubmissionPayload(
        doc_id="doc-x", ticker="ASII", fiscal_period="2024Q4", facts=[],
        narratives=[ExtractedNarrativeItem(section="MDA", text_original=MDA_SENTENCE, source_page=3)],
    )
    with _commit_patches(db):
        rep = await submit_draft_extraction(payload.model_dump_json())
    assert any(i.category == "NARRATIVE_DUPLICATE" and "AALI" in i.feedback_message for i in rep.issues)
    lookup = next(p for sql, p in db.calls if "n.text_hash" in sql)
    assert lookup["texts"] == [MDA_SENTENCE]
    assert "LIMIT" not in next(sql for sql, _p in db.calls if "n.text_hash" in sql)
    assert narrative_md5(MDA_SENTENCE)  # same normalization as the SQL twin


@pytest.mark.asyncio
async def test_mcp_usage_logging_in_processing_log() -> None:
    usage_data = {"input_tokens": 12500, "output_tokens": 850, "pages_read": 12}
    payload = DraftSubmissionPayload(
        doc_id="doc_usage_test_123",
        ticker="BMRI",
        fiscal_period="2024Q4",
        facts=[],
        usage=ProcessingUsage(**usage_data),
    )
    payload_json = json.dumps(payload.model_dump(mode="json"))

    logged_events: list[dict[str, Any]] = []

    async def mock_log(conn: Any, **kwargs: Any) -> None:
        logged_events.append(kwargs)

    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute.return_value = MagicMock(
        mappings=lambda: MagicMock(first=lambda: {"sector": "BANK", "name": "PT Bank Mandiri (Persero) Tbk", "page_count": 50}),
        first=lambda: None,
        scalar=lambda: 0,
    )
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    contract = make_test_contract("BANK")

    with (
        patch("services.mcp.server.get_engine", return_value=mock_engine),
        patch("services.mcp.server.build_extraction_contract", new_callable=AsyncMock, return_value=contract),
        patch("services.mcp.server._log_processing_event", side_effect=mock_log),
    ):
        await submit_draft_extraction(payload_json, retry_attempt=1)

    extracted_events = [e for e in logged_events if e.get("action") == "EXTRACTED"]
    assert len(extracted_events) >= 1
    meta = extracted_events[0].get("metadata") or {}
    assert meta.get("input_tokens") == 12500
    assert meta.get("output_tokens") == 850
    assert meta.get("pages_read") == 12

    logged_events.clear()
    with (
        patch("services.mcp.server.get_engine", return_value=mock_engine),
        patch("services.mcp.server.build_extraction_contract", new_callable=AsyncMock, return_value=contract),
        patch(
            "services.mcp.server.validate_draft_submission",
            return_value=ValidationReport(
                status="VALID",
                submission_id="sub_1",
                doc_id="doc_usage_test_123",
                ticker="BMRI",
                fiscal_period="2024Q4",
                errors_count=0,
                warnings_count=0,
                can_retry=False,
                retry_attempt=1,
                max_retries=3,
                issues=[],
            ),
        ),
        patch("services.mcp.server._log_processing_event", side_effect=mock_log),
        patch("services.mcp.server.compute_for_document", new_callable=AsyncMock, return_value=MagicMock(computed=3)),
        patch("services.mcp.server.refresh_profile_task"),
        patch("services.mcp.server.calculate_valuation", return_value={}),
    ):
        await commit_verified_report(payload_json, usage={"input_tokens": 15000, "output_tokens": 900, "pages_read": 14})

    committed_events = [e for e in logged_events if e.get("action") == "COMMITTED"]
    assert len(committed_events) >= 1
    c_meta = committed_events[0].get("metadata") or {}
    assert c_meta.get("input_tokens") == 15000
    assert c_meta.get("output_tokens") == 900
    assert c_meta.get("pages_read") == 14
