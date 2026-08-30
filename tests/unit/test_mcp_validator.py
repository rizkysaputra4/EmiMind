"""Unit tests for EMIMIND MCP Multi-tier Accounting Validator."""

from __future__ import annotations

from decimal import Decimal

from services.mcp.types import DraftSubmissionPayload, ExtractedFactItem
from services.mcp.validator import validate_draft_submission


def test_validator_balanced_submission_pass() -> None:
    facts = [
        ExtractedFactItem(concept_id="ifrs:Assets", value_numeric=Decimal("100000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:CurrentAssets", value_numeric=Decimal("40000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:NonCurrentAssets", value_numeric=Decimal("60000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:Liabilities", value_numeric=Decimal("40000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:NonCurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("60000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("10000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:Revenue", value_numeric=Decimal("80000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:OperatingProfit", value_numeric=Decimal("25000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:ProfitLoss", value_numeric=Decimal("18000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("22000000000"), source_page=8),
    ]

    payload = DraftSubmissionPayload(
        doc_id="doc_valid_1",
        ticker="ASII",
        fiscal_period="2024Q4",
        facts=facts,
    )

    report = validate_draft_submission(payload, sector="GENERIC")
    assert report.status == "VALID"
    assert report.errors_count == 0


def test_validator_balance_sheet_unbalanced_fail() -> None:
    facts = [
        ExtractedFactItem(concept_id="ifrs:Assets", value_numeric=Decimal("100000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:CurrentAssets", value_numeric=Decimal("40000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:NonCurrentAssets", value_numeric=Decimal("60000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:Liabilities", value_numeric=Decimal("40000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:NonCurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6),
        # Equity is 50B instead of 60B -> mismatch of 10B
        ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("50000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("10000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:Revenue", value_numeric=Decimal("80000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:OperatingProfit", value_numeric=Decimal("25000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:ProfitLoss", value_numeric=Decimal("18000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("22000000000"), source_page=8),
    ]

    payload = DraftSubmissionPayload(
        doc_id="doc_invalid_1",
        ticker="ASII",
        fiscal_period="2024Q4",
        facts=facts,
    )

    report = validate_draft_submission(payload, sector="GENERIC")
    assert report.status == "INVALID"
    assert report.errors_count >= 1
    categories = [i.category for i in report.issues]
    assert "BALANCE_SHEET_UNBALANCED" in categories

    # Diagnostic feedback check
    bs_issue = next(i for i in report.issues if i.category == "BALANCE_SHEET_UNBALANCED")
    assert "Balance Sheet Unbalanced" in bs_issue.feedback_message
    assert 5 in bs_issue.target_pages
    assert 6 in bs_issue.target_pages


def test_validator_scale_mismatch_detection() -> None:
    # Scale error: Assets in millions (100B), Liabilities in millions (40B), but Equity in thousands (60M)
    facts = [
        ExtractedFactItem(concept_id="ifrs:Assets", value_numeric=Decimal("100000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:CurrentAssets", value_numeric=Decimal("40000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:NonCurrentAssets", value_numeric=Decimal("60000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:Liabilities", value_numeric=Decimal("40000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:NonCurrentLiabilities", value_numeric=Decimal("20000000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:Equity", value_numeric=Decimal("60000000"), source_page=6),
        ExtractedFactItem(concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("10000000000"), source_page=5),
        ExtractedFactItem(concept_id="ifrs:Revenue", value_numeric=Decimal("80000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:OperatingProfit", value_numeric=Decimal("25000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:ProfitLoss", value_numeric=Decimal("18000000000"), source_page=7),
        ExtractedFactItem(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("22000000000"), source_page=8),
    ]

    payload = DraftSubmissionPayload(
        doc_id="doc_scale_1",
        ticker="ASII",
        fiscal_period="2024Q4",
        facts=facts,
    )

    report = validate_draft_submission(payload, sector="GENERIC")
    assert report.status == "INVALID"
    categories = [i.category for i in report.issues]
    assert "SCALE_MISMATCH" in categories
    scale_issue = next(i for i in report.issues if i.category == "SCALE_MISMATCH")
    assert "Scale Mismatch Detected" in scale_issue.feedback_message
    assert "thousands instead of millions" in scale_issue.feedback_message
