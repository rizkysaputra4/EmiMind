"""Unit tests for EMIMIND MCP Extraction Contracts."""

from __future__ import annotations

from services.mcp.contracts import build_extraction_contract


def test_build_generic_contract() -> None:
    contract = build_extraction_contract(
        doc_id="test_doc_1",
        ticker="ASII",
        company_name="PT Astra International Tbk",
        sector="AUTOMOTIVE",
        fiscal_period="2024Q4",
    )

    assert contract.ticker == "ASII"
    assert contract.fiscal_period == "2024Q4"
    assert contract.doc_id == "test_doc_1"

    # Verify standard core rules exist
    concept_ids = {r.concept_id for r in contract.required_facts}
    assert "ifrs:Assets" in concept_ids
    assert "ifrs:Liabilities" in concept_ids
    assert "ifrs:Equity" in concept_ids
    assert "ifrs:Revenue" in concept_ids
    assert "ifrs:ProfitLoss" in concept_ids
    assert "ifrs:CashFlowsFromUsedInOperatingActivities" in concept_ids


def test_build_banking_contract() -> None:
    contract = build_extraction_contract(
        doc_id="test_doc_2",
        ticker="BMRI",
        company_name="PT Bank Mandiri (Persero) Tbk",
        sector="BANK",
        fiscal_period="2024Q4",
    )

    concept_ids = {r.concept_id for r in contract.required_facts}
    assert "idx:LoansAndAdvances" in concept_ids
    assert "idx:CustomerDeposits" in concept_ids
    assert "idx:NetInterestIncome" in concept_ids


def test_build_mining_contract() -> None:
    contract = build_extraction_contract(
        doc_id="test_doc_3",
        ticker="NCKL",
        company_name="PT Trimegah Bangun Persada Tbk",
        sector="MINING",
        fiscal_period="2026Q2",
    )

    concept_ids = {r.concept_id for r in contract.required_facts}
    assert "idx:CoalProductionVolume" in concept_ids
    assert "idx:AverageSellingPrice" in concept_ids
