"""Unit tests for EMIMIND MCP Multi-tier Accounting Validator."""

from __future__ import annotations

from decimal import Decimal

from services.mcp.types import DraftSubmissionPayload, ExtractedFactItem, OmittedMetricItem
from services.mcp.validator import validate_draft_submission
from tests.unit._mcp_contract_fixtures import make_test_contract


def _core_facts() -> list[ExtractedFactItem]:
    return [
        ExtractedFactItem(concept_id="ifrs:Assets", value_numeric=Decimal("100000000000"), source_page=5, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CurrentAssets", value_numeric=Decimal("40000000000"), source_page=5, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:NonCurrentAssets", value_numeric=Decimal("60000000000"), source_page=5, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Liabilities", value_numeric=Decimal("40000000000"), source_page=6, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:NonCurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("60000000000"), source_page=6, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("10000000000"), source_page=5, statement="BS"),
        ExtractedFactItem(concept_id="ifrs:Revenue", value_numeric=Decimal("80000000000"), source_page=7, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:OperatingProfit", value_numeric=Decimal("25000000000"), source_page=7, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:ProfitLoss", value_numeric=Decimal("18000000000"), source_page=7, statement="IS"),
        ExtractedFactItem(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("22000000000"), source_page=8, statement="CF"),
    ]


def test_validator_balanced_submission_pass() -> None:
    contract = make_test_contract("GENERIC")
    payload = DraftSubmissionPayload(
        doc_id="doc_valid_1",
        ticker="ASII",
        fiscal_period="2024Q4",
        facts=_core_facts(),
    )

    report = validate_draft_submission(payload, contract=contract, sector="GENERIC")
    assert report.status == "VALID"
    assert report.errors_count == 0


def test_validator_balance_sheet_unbalanced_fail() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    # Equity 50B instead of 60B -> mismatch of 10B
    facts[6] = ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("50000000000"), source_page=6, statement="BS")

    payload = DraftSubmissionPayload(doc_id="doc_invalid_1", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC")
    assert report.status == "INVALID"
    assert report.errors_count >= 1
    categories = [i.category for i in report.issues]
    assert "BALANCE_SHEET_UNBALANCED" in categories

    bs_issue = next(i for i in report.issues if i.category == "BALANCE_SHEET_UNBALANCED")
    assert "Balance Sheet Unbalanced" in bs_issue.feedback_message
    assert 5 in bs_issue.target_pages
    assert 6 in bs_issue.target_pages


def test_validator_scale_mismatch_detection() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    facts[6] = ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("60000000"), source_page=6, statement="BS")
    payload = DraftSubmissionPayload(doc_id="doc_scale_1", ticker="ASII", fiscal_period="2024Q4", facts=facts)

    report = validate_draft_submission(payload, contract=contract, sector="GENERIC")
    assert report.status == "INVALID"
    categories = [i.category for i in report.issues]
    assert "SCALE_MISMATCH" in categories
    scale_issue = next(i for i in report.issues if i.category == "SCALE_MISMATCH")
    assert "Scale Mismatch Detected" in scale_issue.feedback_message
    assert "thousands instead of millions" in scale_issue.feedback_message


def test_validator_missing_mandatory_sector_kpi_fails() -> None:
    contract = make_test_contract("BANK")
    payload = DraftSubmissionPayload(doc_id="doc_bank_missing", ticker="BMRI", fiscal_period="2024Q4", facts=_core_facts())

    report = validate_draft_submission(payload, contract=contract, sector="BANK")
    assert report.status == "INVALID"
    categories = [i.category for i in report.issues]
    assert "MISSING_MANDATORY_METRIC_OR_EXPLANATION" in categories

    # Coverage block should reflect the shortfall
    assert report.coverage.critical.expected > 0
    assert len(report.coverage.critical.missing) >= 1
    assert "idx:LoansAndAdvances" in report.coverage.critical.missing


def test_validator_missing_metric_feedback_includes_search_hints() -> None:
    contract = make_test_contract("BANK")
    payload = DraftSubmissionPayload(doc_id="doc_hints", ticker="BMRI", fiscal_period="2024Q4", facts=_core_facts())
    report = validate_draft_submission(payload, contract=contract, sector="BANK")

    deposit_issue = next(
        i for i in report.issues
        if i.category == "MISSING_MANDATORY_METRIC_OR_EXPLANATION" and i.concept_id == "idx:CustomerDeposits"
    )
    # search_hints + module title + synonyms must appear in the feedback
    assert "Catatan Simpanan Nasabah" in deposit_issue.feedback_message
    assert "Dana Pihak Ketiga" in deposit_issue.feedback_message or "DPK" in deposit_issue.feedback_message


def _bank_extra_facts() -> list[ExtractedFactItem]:
    return [
        ExtractedFactItem(concept_id="idx:LoansAndAdvances", value_numeric=Decimal("70000000000"), source_page=12, statement="BS"),
        ExtractedFactItem(concept_id="idx:CustomerDeposits", value_numeric=Decimal("35000000000"), source_page=14, statement="BS"),
        ExtractedFactItem(concept_id="idx:CASA", value_numeric=Decimal("25000000000"), source_page=14, statement="BS"),
        ExtractedFactItem(concept_id="idx:NetInterestIncome", value_numeric=Decimal("15000000000"), source_page=15, statement="IS"),
        ExtractedFactItem(concept_id="idx:NetInterestMargin", value_numeric=Decimal("5.25"), source_page=20, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:NonPerformingLoansGross", value_numeric=Decimal("1200000000"), source_page=22, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CapitalAdequacyRatio", value_numeric=Decimal("21.5"), source_page=25, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:BOPO", value_numeric=Decimal("62.4"), source_page=26, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CostOfCredit", value_numeric=Decimal("1.10"), source_page=26, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:LoanToDepositRatio", value_numeric=Decimal("85.4"), source_page=27, statement="NOTE"),
    ]


def test_validator_omitted_sector_kpi_with_explanation_passes() -> None:
    contract = make_test_contract("BANK")
    bank_facts = _core_facts() + _bank_extra_facts()

    omitted = [
        OmittedMetricItem(
            metric_id="idx:NPLCoverageRatio",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="The interim financial report does not disclose NPL coverage percentage explicitly in footnotes.",
            search_pages_checked=[22, 23, 24],
        )
    ]

    payload = DraftSubmissionPayload(
        doc_id="doc_bank_omitted",
        ticker="BMRI",
        fiscal_period="2024Q4",
        facts=bank_facts,
        omitted_kpis=omitted,
    )

    report = validate_draft_submission(payload, contract=contract, sector="BANK")
    assert report.status == "VALID"
    assert report.errors_count == 0
    assert report.coverage.high.omitted_with_justification >= 1


def test_validator_contradictory_omission_flagged() -> None:
    contract = make_test_contract("BANK")
    bank_facts = _core_facts() + _bank_extra_facts()
    omitted = [
        OmittedMetricItem(
            metric_id="idx:NPLCoverageRatio",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="It is disclosed in MD&A on the operational highlights page, but we chose not to extract it.",
            search_pages_checked=[22, 23],
        )
    ]
    payload = DraftSubmissionPayload(
        doc_id="doc_bank_contra", ticker="BMRI", fiscal_period="2024Q4",
        facts=bank_facts, omitted_kpis=omitted,
    )
    report = validate_draft_submission(payload, contract=contract, sector="BANK")
    assert report.status == "INVALID"
    assert any(i.category == "CONTRADICTORY_OMISSION" for i in report.issues)


def test_validator_coverage_block_tracks_buckets() -> None:
    contract = make_test_contract("BANK")
    facts = [
        *_core_facts(),
        ExtractedFactItem(concept_id="idx:LoansAndAdvances", value_numeric=Decimal("70000000000"), source_page=12, statement="BS"),
        ExtractedFactItem(concept_id="idx:CustomerDeposits", value_numeric=Decimal("35000000000"), source_page=14, statement="BS"),
        ExtractedFactItem(concept_id="idx:NetInterestIncome", value_numeric=Decimal("15000000000"), source_page=15, statement="IS"),
        ExtractedFactItem(concept_id="idx:NetInterestMargin", value_numeric=Decimal("5.25"), source_page=20, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:NonPerformingLoansGross", value_numeric=Decimal("1200000000"), source_page=22, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:CapitalAdequacyRatio", value_numeric=Decimal("21.5"), source_page=25, statement="NOTE"),
        ExtractedFactItem(concept_id="idx:BOPO", value_numeric=Decimal("62.4"), source_page=26, statement="NOTE"),
    ]
    payload = DraftSubmissionPayload(doc_id="doc_cov", ticker="BMRI", fiscal_period="2024Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="BANK")

    # We know from the fixture: BANK adds 6 CRITICAL rules + core CRITICALs.
    # Some are unmet -> report should still capture found/expected counts.
    assert report.coverage.critical.expected > 0
    assert report.coverage.critical.found > 0
    assert report.coverage.high.expected >= 3


def test_validator_retry_still_missing_message() -> None:
    contract = make_test_contract("BANK")
    payload = DraftSubmissionPayload(doc_id="doc_retry", ticker="BMRI", fiscal_period="2024Q4", facts=_core_facts())

    report = validate_draft_submission(
        payload,
        contract=contract,
        sector="BANK",
        retry_attempt=2,
        previous_attempt_misses=["idx:LoansAndAdvances", "idx:CustomerDeposits"],
    )
    retry_issue = next(i for i in report.issues if i.category == "RETRY_STILL_MISSING")
    assert "Attempt 2/3" in retry_issue.feedback_message
    assert "idx:LoansAndAdvances" in retry_issue.feedback_message


def test_validator_missing_statement_fails() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    facts[0] = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("100000000000"),
        source_page=5,
        statement=None,
    )
    payload = DraftSubmissionPayload(doc_id="doc_missing_stmt", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC")
    assert report.status == "INVALID"
    issue = next(i for i in report.issues if i.category == "SCHEMA" and "missing required 'statement'" in i.feedback_message)
    assert "ifrs:Assets" in issue.feedback_message


def test_validator_invalid_period_type_fails() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    facts[0] = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("100000000000"),
        source_page=5,
        statement="BS",
        period_type="invalid_type",
    )
    payload = DraftSubmissionPayload(doc_id="doc_bad_pt", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC")
    assert report.status == "INVALID"
    issue = next(i for i in report.issues if i.category == "SCHEMA" and "invalid period_type" in i.feedback_message)
    assert "ifrs:Assets" in issue.feedback_message

