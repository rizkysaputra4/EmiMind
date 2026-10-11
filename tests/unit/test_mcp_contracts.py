"""Unit tests for EMIMIND MCP Extraction Contracts.

The real build_extraction_contract is async and reads from Postgres. That path
is covered by tests/integration/test_extraction_contract_from_db.py. Here we
smoke-test only the pure-Python fixture builder used by other unit tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.mcp.contracts import (
    applies_to_sub_sector,
    build_extraction_contract,
    get_route_query,
    load_page_router_queries,
)
from tests.unit._mcp_contract_fixtures import make_test_contract


def test_fixture_generic_contract_has_core_rules() -> None:
    contract = make_test_contract("GENERIC", doc_id="test_doc_1", ticker="ASII", fiscal_period="2024Q4")

    assert contract.ticker == "ASII"
    assert contract.fiscal_period == "2024Q4"
    assert contract.doc_id == "test_doc_1"

    concept_ids = {r.concept_id for r in contract.required_facts}
    for cid in [
        "ifrs:Assets", "ifrs:Liabilities", "ifrs:Equity", "ifrs:Revenue",
        "ifrs:ProfitLoss", "ifrs:CashFlowsFromUsedInOperatingActivities",
    ]:
        assert cid in concept_ids


def test_fixture_bank_contract_adds_sector_kpis() -> None:
    contract = make_test_contract("BANK", ticker="BMRI")
    concept_ids = {r.concept_id for r in contract.required_facts}
    assert "idx:LoansAndAdvances" in concept_ids
    assert "idx:CustomerDeposits" in concept_ids
    assert "idx:NetInterestIncome" in concept_ids

    # BANK KPIs carry CRITICAL importance and search hints
    loans_rule = next(r for r in contract.required_facts if r.concept_id == "idx:LoansAndAdvances")
    assert loans_rule.importance == "CRITICAL"
    assert loans_rule.search_hints  # non-empty


def test_fixture_cpo_contract_adds_upstream_kpis() -> None:
    contract = make_test_contract("CPO", ticker="LSIP", fiscal_period="2025FY")
    concept_ids = {r.concept_id for r in contract.required_facts}
    assert "idx:CPOProductionVolume" in concept_ids
    assert "idx:MaturePlantedArea" in concept_ids
    assert "idx:OilExtractionRate" in concept_ids


def test_page_router_queries_yaml_schema() -> None:
    """Every module in page_router_queries.yaml must have non-empty terms_id and terms_en."""
    queries = load_page_router_queries()
    assert len(queries) >= 9, "Expected at least 9 modules in page_router_queries.yaml"

    for mod_name, sector_map in queries.items():
        assert isinstance(sector_map, dict), f"Module {mod_name} must map to sector dictionaries"
        assert len(sector_map) > 0, f"Module {mod_name} must have at least one sector config"
        for sector, entry in sector_map.items():
            terms_id = entry.get("terms_id", [])
            terms_en = entry.get("terms_en", [])
            assert isinstance(terms_id, list) and len(terms_id) > 0, (
                f"Module {mod_name} [{sector}] must have non-empty terms_id"
            )
            assert isinstance(terms_en, list) and len(terms_en) > 0, (
                f"Module {mod_name} [{sector}] must have non-empty terms_en"
            )
            assert isinstance(entry.get("max_pages", 6), int)
            assert entry["max_pages"] > 0


@pytest.mark.asyncio
async def test_build_extraction_contract_bank_includes_bank_loans_npl() -> None:
    """build_extraction_contract for a BANK issuer includes BANK_LOANS_NPL with non-empty terms."""
    conn = AsyncMock()
    cursor = MagicMock()
    cursor.mappings.return_value = []
    conn.execute.return_value = cursor

    contract = await build_extraction_contract(
        conn,
        doc_id="test_doc_bmri",
        ticker="BMRI",
        company_name="PT Bank Mandiri (Persero) Tbk",
        sector="BANK",
        fiscal_period="2025Q4",
    )

    mod_names = [m.name for m in contract.granular_note_modules]
    assert "BANK_LOANS_NPL" in mod_names

    bank_loans_mod = next(m for m in contract.granular_note_modules if m.name == "BANK_LOANS_NPL")
    assert bank_loans_mod.route_query is not None
    assert len(bank_loans_mod.route_query.terms_id) > 0
    assert len(bank_loans_mod.route_query.terms_en) > 0


@pytest.mark.asyncio
async def test_build_extraction_contract_plantation_includes_plantation_area() -> None:
    """build_extraction_contract for a PLANTATION issuer includes PLANTATION_AREA with non-empty terms."""
    conn = AsyncMock()
    cursor = MagicMock()
    cursor.mappings.return_value = []
    conn.execute.return_value = cursor

    contract = await build_extraction_contract(
        conn,
        doc_id="test_doc_lsip",
        ticker="LSIP",
        company_name="PT PP London Sumatra Indonesia Tbk",
        sector="PLANTATION",
        fiscal_period="2025Q4",
    )

    mod_names = [m.name for m in contract.granular_note_modules]
    assert "PLANTATION_AREA" in mod_names

    plantation_mod = next(m for m in contract.granular_note_modules if m.name == "PLANTATION_AREA")
    assert plantation_mod.route_query is not None
    assert len(plantation_mod.route_query.terms_id) > 0
    assert len(plantation_mod.route_query.terms_en) > 0


@pytest.mark.asyncio
async def test_build_extraction_contract_includes_core_modules() -> None:
    """build_extraction_contract attaches core statement route queries."""
    conn = AsyncMock()
    cursor = MagicMock()
    cursor.mappings.return_value = []
    conn.execute.return_value = cursor

    contract = await build_extraction_contract(
        conn,
        doc_id="test_doc_core",
        ticker="BMRI",
        company_name="PT Bank Mandiri (Persero) Tbk",
        sector="BANK",
        fiscal_period="2025Q4",
    )

    for core_mod in ["BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW", "MDA"]:
        assert core_mod in contract.core_modules
        rq = contract.core_modules[core_mod]
        assert len(rq.terms_id) > 0
        assert len(rq.terms_en) > 0



@pytest.mark.parametrize(
    ("applicability", "sub_sector", "expected"),
    [
        (["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "COAL", False),
        (["MINING", "BASIC_MATERIALS", "NICKEL"], "COAL", False),
        (["COAL", "MINING", "ENERGY"], "COAL", True),
        (["COAL", "NICKEL", "GOLD_COPPER", "TIN_MINING", "MINING"], "COAL", True),
        (["MINING", "ENERGY", "BASIC_MATERIALS"], "COAL", True),  # no sub-sector tag
        (["GOLD_COPPER", "MINING"], None, True),  # sub-sector unknown: keep everything
        (["GOLD_COPPER", "MINING"], "OTHER", True),
    ],
)
def test_mining_metrics_follow_issuer_sub_sector(
    applicability: list[str], sub_sector: str | None, expected: bool
) -> None:
    assert applies_to_sub_sector(applicability, "MINING", sub_sector) is expected


def test_mining_modules_have_route_queries() -> None:
    for mod in ("MINING_PRODUCTION_AND_SALES", "MINING_RESERVES_AND_RESOURCES"):
        assert get_route_query(mod, "MINING") is not None
    rq = get_route_query("COGS_COMPONENTS", "MINING")
    assert rq is not None and "beban pokok pendapatan" in rq.terms_id
