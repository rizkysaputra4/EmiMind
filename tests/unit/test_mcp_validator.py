"""Unit tests for EMIMIND MCP Multi-tier Accounting Validator."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from services.mcp.types import (
    CellRef,
    DraftSubmissionPayload,
    ExtractedFactItem,
    OmittedMetricItem,
    PageEvidence,
    PageTable,
    PageTableCell,
)
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


def _make_core_evidence() -> dict[int, PageEvidence]:
    """Helper creating minimal valid evidence for core statement pages 5, 6, 7, 8."""
    return {
        5: PageEvidence(
            page_index=5,
            text_source="pdf_text",
            page_text="Total aset 100.000 aset lancar 40.000 aset tidak lancar 60.000 kas 10.000",
            tables=[
                PageTable(
                    table_index=0,
                    unit_hint="jutaan rupiah",
                    cells=[
                        PageTableCell(row=1, col=1, text="100.000", value=100000.0),
                        PageTableCell(row=2, col=1, text="40.000", value=40000.0),
                        PageTableCell(row=3, col=1, text="60.000", value=60000.0),
                        PageTableCell(row=4, col=1, text="10.000", value=10000.0),
                    ],
                )
            ],
        ),
        6: PageEvidence(
            page_index=6,
            text_source="pdf_text",
            page_text="Liabilitas 40.000 liabilitas lancar 20.000 tidak lancar 20.000 ekuitas 60.000",
            tables=[
                PageTable(
                    table_index=0,
                    unit_hint="jutaan rupiah",
                    cells=[
                        PageTableCell(row=1, col=1, text="40.000", value=40000.0),
                        PageTableCell(row=2, col=1, text="20.000", value=20000.0),
                        PageTableCell(row=3, col=1, text="20.000", value=20000.0),
                        PageTableCell(row=4, col=1, text="60.000", value=60000.0),
                    ],
                )
            ],
        ),
        7: PageEvidence(
            page_index=7,
            text_source="pdf_text",
            page_text="Pendapatan 80.000 laba usaha 25.000 laba bersih 18.000",
            tables=[
                PageTable(
                    table_index=0,
                    unit_hint="jutaan rupiah",
                    cells=[
                        PageTableCell(row=1, col=1, text="80.000", value=80000.0),
                        PageTableCell(row=2, col=1, text="25.000", value=25000.0),
                        PageTableCell(row=3, col=1, text="18.000", value=18000.0),
                    ],
                )
            ],
        ),
        8: PageEvidence(
            page_index=8,
            text_source="pdf_text",
            page_text="Arus kas operasi 22.000",
            tables=[
                PageTable(
                    table_index=0,
                    unit_hint="jutaan rupiah",
                    cells=[
                        PageTableCell(row=1, col=1, text="22.000", value=22000.0),
                    ],
                )
            ],
        ),
    }


def test_validator_correct_cell_ref_millions_scale_passes() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    # Attach correct cell_ref to Assets (table 0, row 1, col 1 = 100,000 * 1,000,000)
    facts[0] = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("100000000000"),
        source_page=5,
        statement="BS",
        cell_ref=CellRef(table_index=0, row=1, col=1),
    )

    payload = DraftSubmissionPayload(doc_id="doc_cell_ok", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    evidence = _make_core_evidence()
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC", evidence=evidence, page_count=10)

    assert report.status == "VALID"
    assert report.errors_count == 0
    assert not any(i.category == "GROUNDING_CELL" for i in report.issues)


def test_validator_cell_ref_transposed_digit_fails_grounding_cell() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    # Fact value has a transposed digit: 100200000000 instead of 100000000000
    facts[0] = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("100200000000"),
        source_page=5,
        statement="BS",
        cell_ref=CellRef(table_index=0, row=1, col=1),
    )

    payload = DraftSubmissionPayload(doc_id="doc_cell_bad", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    evidence = _make_core_evidence()
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC", evidence=evidence, page_count=10)

    assert report.status == "INVALID"
    cell_issue = next(i for i in report.issues if i.category == "GROUNDING_CELL")
    assert "GROUNDING_CELL" == cell_issue.category
    assert 5 in cell_issue.target_pages


def test_validator_text_fact_absent_fails_grounding_text() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    # Remove cell_ref and point to page with no matching text
    evidence = _make_core_evidence()
    evidence[5].page_text = "Laporan Posisi Keuangan tanpa angka sama sekali"
    evidence[5].tables = []  # No tables either

    payload = DraftSubmissionPayload(doc_id="doc_text_bad", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC", evidence=evidence, page_count=10)

    assert report.status == "INVALID"
    text_issue = next(i for i in report.issues if i.category == "GROUNDING_TEXT")
    assert "GROUNDING_TEXT" == text_issue.category
    assert 5 in text_issue.target_pages


def test_validator_ocr_page_miss_gives_warning_status_valid() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    evidence = _make_core_evidence()
    # Change page 5 to OCR page with missing number in OCR text
    evidence[5].text_source = "ocr"
    evidence[5].page_text = "Teks buram hasil scan tanpa angka yang jelas"
    evidence[5].tables = []

    payload = DraftSubmissionPayload(doc_id="doc_ocr_warn", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC", evidence=evidence, page_count=10)

    # Should produce WARNING GROUNDING_OCR, but overall status VALID (no ERRORs)
    assert report.status == "VALID"
    ocr_issue = next(i for i in report.issues if i.category == "GROUNDING_OCR")
    assert ocr_issue.severity.value == "WARNING"
    assert ocr_issue.details.get("needs_review") is True


def test_validator_source_page_exceeds_page_count_fails_provenance() -> None:
    contract = make_test_contract("GENERIC")
    facts = _core_facts()
    page_count = 10
    # source_page = page_count + 1 = 11
    facts[0] = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("100000000000"),
        source_page=page_count + 1,
        statement="BS",
    )

    payload = DraftSubmissionPayload(doc_id="doc_prov_bad", ticker="ASII", fiscal_period="2024Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="GENERIC", page_count=page_count)

    assert report.status == "INVALID"
    prov_issue = next(i for i in report.issues if i.category == "PROVENANCE")
    assert "PROVENANCE" == prov_issue.category
    assert 11 in prov_issue.target_pages


def test_validator_aali_synthetic_fixture_fails_synthetic_label_and_split() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "m9" / "aali_synthetic_payload.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    payload = DraftSubmissionPayload.model_validate(data)
    # Page 3 evidence has only top-level revenue, not the 700/300 split or placeholder labels
    evidence = {
        3: PageEvidence(
            page_index=3,
            text_source="pdf_text",
            page_text="Laporan Laba Rugi Komprehensif PT Astra Agro Lestari Tbk\nPendapatan Bersih: 1.000\nBeban: 800",
            tables=[],
        )
    }

    contract = make_test_contract("GENERIC")
    report = validate_draft_submission(payload, contract=contract, evidence=evidence, page_count=50)

    assert report.status == "INVALID"
    categories = [i.category for i in report.issues]
    assert "SYNTHETIC_LABEL" in categories
    assert "SYNTHETIC_SPLIT" in categories


def test_validator_genuine_grounded_split_50_50_passes() -> None:
    contract = make_test_contract("GENERIC")
    facts = [
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("1000"),
            source_page=28,
            statement="NOTE",
            source_label_original="Total Pendapatan",
        ),
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("500"),
            source_page=28,
            statement="NOTE",
            source_label_original="Minyak Kelapa Sawit",
            segment={"segment": "Minyak Kelapa Sawit", "type": "product"},
        ),
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("500"),
            source_page=28,
            statement="NOTE",
            source_label_original="Inti Sawit",
            segment={"segment": "Inti Sawit", "type": "product"},
        ),
    ]

    payload = DraftSubmissionPayload(doc_id="doc_grounded_split", ticker="AALI", fiscal_period="2025Q4", facts=facts)
    evidence = {
        28: PageEvidence(
            page_index=28,
            text_source="pdf_text",
            page_text="Catatan 28. Rincian Pendapatan:\nMinyak Kelapa Sawit: 500\nInti Sawit: 500\nTotal: 1.000",
            tables=[],
        )
    }

    report = validate_draft_submission(payload, contract=contract, evidence=evidence, page_count=50)

    categories = [i.category for i in report.issues]
    assert "SYNTHETIC_LABEL" not in categories
    assert "SYNTHETIC_SPLIT" not in categories


def test_validator_placeholder_label_verbatim_on_page_passes_synthetic_label() -> None:
    contract = make_test_contract("GENERIC")
    facts = [
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("1000"),
            source_page=15,
            statement="NOTE",
        ),
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("700"),
            source_page=15,
            statement="NOTE",
            source_label_original="Primary Operations",
            segment={"segment": "Primary Operations", "type": "product"},
        ),
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("300"),
            source_page=15,
            statement="NOTE",
            source_label_original="Other Operations",
            segment={"segment": "Other Operations", "type": "product"},
        ),
    ]

    payload = DraftSubmissionPayload(doc_id="doc_verbatim_label", ticker="AALI", fiscal_period="2025Q4", facts=facts)
    # The text literally has "Primary Operations" and "Other Operations" and the numbers
    evidence = {
        15: PageEvidence(
            page_index=15,
            text_source="pdf_text",
            page_text="Segment Breakdown:\nPrimary Operations: 700\nOther Operations: 300\nTotal: 1.000",
            tables=[],
        )
    }

    report = validate_draft_submission(payload, contract=contract, evidence=evidence, page_count=50)

    categories = [i.category for i in report.issues]
    assert "SYNTHETIC_LABEL" not in categories
    assert "SYNTHETIC_SPLIT" not in categories


def test_validator_only_child_lainnya_without_verbatim_fails_synthetic_label() -> None:
    contract = make_test_contract("GENERIC")
    facts = [
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("1000"),
            source_page=10,
            statement="NOTE",
            source_label_original="Lainnya",
            segment={"segment": "Lainnya", "type": "product"},
        ),
    ]

    payload = DraftSubmissionPayload(doc_id="doc_only_child_lainnya", ticker="AALI", fiscal_period="2025Q4", facts=facts)
    evidence = {
        10: PageEvidence(
            page_index=10,
            text_source="pdf_text",
            page_text="Pendapatan jasa dan perdagangan: 1.000",
            tables=[],
        )
    }

    report = validate_draft_submission(payload, contract=contract, evidence=evidence, page_count=50)

    assert report.status == "INVALID"
    label_issue = next(i for i in report.issues if i.category == "SYNTHETIC_LABEL")
    assert label_issue.concept_id == "ifrs:Revenue"


def test_validator_segmented_fact_without_source_page_fails_segment_provenance() -> None:
    contract = make_test_contract("GENERIC")
    facts = [
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("500"),
            source_page=None,
            statement="NOTE",
            segment={"segment": "CPO", "type": "product"},
        ),
    ]

    payload = DraftSubmissionPayload(doc_id="doc_seg_no_page", ticker="AALI", fiscal_period="2025Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, page_count=50)

    assert report.status == "INVALID"
    seg_prov = next(i for i in report.issues if i.category == "SEGMENT_PROVENANCE")
    assert seg_prov.concept_id == "ifrs:Revenue"


def test_validator_loan_matrix_children_summing_to_total_passes() -> None:
    contract = make_test_contract("BANK")
    facts = [
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("80000000000"),
            source_page=22,
            statement="NOTE",
            source_label_original="Total Pinjaman yang Diberikan",
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("45500000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "Korporasi", "type": "customer_type"},
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("17200000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "Komersial", "type": "customer_type"},
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("11000000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "Retail", "type": "customer_type"},
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("6300000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "UMKM", "type": "customer_type"},
        ),
    ]

    payload = DraftSubmissionPayload(doc_id="doc_loan_sum_ok", ticker="BMRI", fiscal_period="2025Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="BANK", page_count=50)

    categories = [i.category for i in report.issues]
    assert "SUM_MISMATCH" not in categories


def test_validator_children_off_by_five_percent_fails_sum_mismatch() -> None:
    contract = make_test_contract("BANK")
    # Total is 80B, but children sum to 76B (4B discrepancy = 5% off)
    facts = [
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("80000000000"),
            source_page=22,
            statement="NOTE",
            source_label_original="Total Pinjaman yang Diberikan",
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("41500000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "Korporasi", "type": "customer_type"},
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("17200000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "Komersial", "type": "customer_type"},
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("11000000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "Retail", "type": "customer_type"},
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("6300000000"),
            source_page=22,
            statement="NOTE",
            segment={"segment": "UMKM", "type": "customer_type"},
        ),
    ]

    payload = DraftSubmissionPayload(doc_id="doc_loan_sum_bad", ticker="BMRI", fiscal_period="2025Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="BANK", page_count=50)

    assert report.status == "INVALID"
    sum_issue = next(i for i in report.issues if i.category == "SUM_MISMATCH")
    assert sum_issue.concept_id == "idx:LoansGross"
    assert "80,000,000,000" in sum_issue.feedback_message
    assert "76,000,000,000" in sum_issue.feedback_message


def test_validator_note_total_equal_prior_year_bs_fails_tie_out_with_column_hint() -> None:
    contract = make_test_contract("BANK")
    # Current year BS Loans is 80B
    # Agent extracted note total idx:LoansGross = 70B (prior year column value)
    facts = [
        ExtractedFactItem(
            concept_id="idx:LoansAndAdvances",
            value_numeric=Decimal("80000000000"),
            source_page=6,
            statement="BS",
            source_label_original="Kredit yang Diberikan",
        ),
        ExtractedFactItem(
            concept_id="idx:LoansGross",
            value_numeric=Decimal("70000000000"),
            source_page=22,
            statement="NOTE",
            source_label_original="Jumlah Pinjaman yang Diberikan (Catatan 12)",
        ),
    ]

    payload = DraftSubmissionPayload(doc_id="doc_prior_year_col", ticker="BMRI", fiscal_period="2025Q4", facts=facts)
    report = validate_draft_submission(payload, contract=contract, sector="BANK", page_count=50)

    assert report.status == "INVALID"
    tie_issue = next(i for i in report.issues if i.category == "TIE_OUT")
    assert tie_issue.concept_id == "idx:LoansGross"
    assert "check you used the current-period column" in tie_issue.feedback_message.lower()




