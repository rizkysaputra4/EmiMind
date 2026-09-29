"""Unit tests for EMIMIND MCP Multi-tier Accounting Validator.

Every payload is validated against page evidence shaped like a real IDX statement page (the
validator refuses to validate without evidence). `_evidence()` renders one line per fact,
"<label> <value in millions>", under a "Disajikan dalam jutaan Rupiah" header.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from services.mcp.types import (
    CellRef,
    ConceptDefinition,
    DraftSubmissionPayload,
    ExtractedFactItem,
    ExtractedNarrativeItem,
    OmittedMetricItem,
    PageEvidence,
    PageTable,
    PageTableCell,
)
from services.mcp.validator import narrative_md5, validate_draft_submission
from tests.unit._mcp_contract_fixtures import (
    PAGE_HEADER,
    make_test_contract,
    printed_value,
    render_evidence,
)

HEADER = PAGE_HEADER


def _printed(f: ExtractedFactItem) -> str:
    return printed_value(f)


def _evidence(
    facts: list[ExtractedFactItem], extra: dict[int, str] | None = None
) -> dict[int, PageEvidence]:
    return render_evidence(facts, extra)


def F(  # noqa: N802 - short fact constructor for readability
    cid: str,
    value: str,
    page: int | None,
    stmt: str | None,
    label: str | None,
    **kw: object,
) -> ExtractedFactItem:
    return ExtractedFactItem(
        concept_id=cid,
        value_numeric=Decimal(value),
        source_page=page,
        statement=stmt,  # type: ignore[arg-type]
        source_label_original=label,
        **kw,  # type: ignore[arg-type]
    )


def _core_facts() -> list[ExtractedFactItem]:
    return [
        F("ifrs:Assets", "100000000000", 5, "BS", "Total aset"),
        F("ifrs:CurrentAssets", "40000000000", 5, "BS", "Total aset lancar"),
        F("ifrs:NonCurrentAssets", "60000000000", 5, "BS", "Total aset tidak lancar"),
        F("ifrs:Liabilities", "40000000000", 6, "BS", "Total liabilitas"),
        F("ifrs:CurrentLiabilities", "20000000000", 6, "BS", "Total liabilitas jangka pendek"),
        F("ifrs:NonCurrentLiabilities", "20000000000", 6, "BS", "Total liabilitas jangka panjang"),
        F("ifrs:Equity", "60000000000", 6, "BS", "Total ekuitas"),
        F("ifrs:CashAndCashEquivalents", "10000000000", 5, "BS", "Kas dan setara kas"),
        F("ifrs:Revenue", "80000000000", 7, "IS", "Pendapatan"),
        F("ifrs:OperatingProfit", "25000000000", 7, "IS", "Laba usaha"),
        F("ifrs:ProfitLoss", "18000000000", 7, "IS", "Laba tahun berjalan"),
        F("ifrs:CashFlowsFromUsedInOperatingActivities", "22000000000", 8, "CF", "Kas neto dari aktivitas operasi"),
    ]


def _bank_extra_facts() -> list[ExtractedFactItem]:
    return [
        F("idx:LoansAndAdvances", "70000000000", 12, "BS", "Kredit yang diberikan"),
        F("idx:CustomerDeposits", "35000000000", 14, "BS", "Simpanan nasabah"),
        F("idx:CASA", "25000000000", 14, "BS", "Giro dan tabungan"),
        F("idx:NetInterestIncome", "15000000000", 15, "IS", "Pendapatan bunga bersih"),
        F("idx:NetInterestMargin", "5.25", 20, "NOTE", "Marjin bunga bersih", unit="PERCENT", period_type="duration_ytd"),
        F("idx:NonPerformingLoansGross", "1200000000", 22, "NOTE", "Kredit bermasalah", period_type="instant"),
        F("idx:CapitalAdequacyRatio", "21.5", 25, "NOTE", "Rasio kecukupan modal", unit="PERCENT", period_type="instant"),
        F("idx:BOPO", "62.4", 26, "NOTE", "BOPO", unit="PERCENT", period_type="duration_ytd"),
        F("idx:CostOfCredit", "1.10", 26, "NOTE", "Biaya kredit", unit="PERCENT", period_type="duration_ytd"),
        F("idx:LoanToDepositRatio", "85.4", 27, "NOTE", "Rasio kredit terhadap simpanan", unit="PERCENT", period_type="instant"),
    ]


def _validate(facts: list[ExtractedFactItem], sector: str = "GENERIC", **kw: object):  # type: ignore[no-untyped-def]
    payload = DraftSubmissionPayload(
        doc_id="doc_test", ticker=str(kw.pop("ticker", "ASII")), fiscal_period=str(kw.pop("fiscal_period", "2024Q4")),
        facts=facts,
        narratives=kw.pop("narratives", []),  # type: ignore[arg-type]
        omitted_kpis=kw.pop("omitted_kpis", []),  # type: ignore[arg-type]
    )
    evidence = kw.pop("evidence", None)
    if evidence is None:
        evidence = _evidence(facts)
    return validate_draft_submission(
        payload,
        contract=make_test_contract(sector),
        sector=sector,
        evidence=evidence,  # type: ignore[arg-type]
        page_count=int(kw.pop("page_count", 50)),  # type: ignore[call-overload]
        **kw,  # type: ignore[arg-type]
    )


def _cats(report, severity: str = "ERROR") -> set[str]:  # type: ignore[no-untyped-def]
    return {i.category for i in report.issues if i.severity.value == severity}


# ---------------------------------------------------------------------------
# Evidence is mandatory
# ---------------------------------------------------------------------------


def test_validator_without_evidence_is_document_not_indexed() -> None:
    payload = DraftSubmissionPayload(doc_id="doc_x", ticker="ASII", fiscal_period="2024Q4", facts=_core_facts())
    report = validate_draft_submission(payload, contract=make_test_contract("GENERIC"), evidence=None, page_count=10)
    assert report.status == "INVALID"
    assert "DOCUMENT_NOT_INDEXED" in _cats(report)


def test_validator_balanced_submission_pass() -> None:
    report = _validate(_core_facts())
    assert report.status == "VALID", report.issues
    assert report.errors_count == 0


def test_validator_balance_sheet_unbalanced_fail() -> None:
    facts = _core_facts()
    facts[6] = F("ifrs:Equity", "50000000000", 6, "BS", "Total ekuitas")
    report = _validate(facts)
    assert report.status == "INVALID"
    bs_issue = next(i for i in report.issues if i.category == "BALANCE_SHEET_UNBALANCED")
    assert "Balance Sheet Unbalanced" in bs_issue.feedback_message
    assert 5 in bs_issue.target_pages
    assert 6 in bs_issue.target_pages


def test_validator_scale_mismatch_detection() -> None:
    facts = _core_facts()
    facts[6] = F("ifrs:Equity", "60000000", 6, "BS", "Total ekuitas")
    report = _validate(facts)
    assert report.status == "INVALID"
    scale_issue = next(i for i in report.issues if i.category == "SCALE_MISMATCH")
    assert "thousands instead of millions" in scale_issue.feedback_message


def test_validator_syirkah_plug_only_for_banks() -> None:
    facts = [*_core_facts(), F("idx:TemporarySyirkahFunds", "5000000000", 6, "BS", "Dana syirkah temporer", period_type="instant")]
    facts[0] = F("ifrs:Assets", "105000000000", 5, "BS", "Total aset")
    facts[2] = F("ifrs:NonCurrentAssets", "65000000000", 5, "BS", "Total aset tidak lancar")
    assert "BALANCE_SHEET_UNBALANCED" not in _cats(_validate(facts, sector="BANK"))
    assert "BALANCE_SHEET_UNBALANCED" in _cats(_validate(facts, sector="GENERIC"))


# ---------------------------------------------------------------------------
# Coverage and omissions
# ---------------------------------------------------------------------------


def test_validator_missing_mandatory_sector_kpi_fails() -> None:
    report = _validate(_core_facts(), sector="BANK", ticker="BMRI")
    assert report.status == "INVALID"
    assert "MISSING_MANDATORY_METRIC_OR_EXPLANATION" in _cats(report)
    assert "idx:LoansAndAdvances" in report.coverage.critical.missing


def test_validator_missing_metric_feedback_includes_search_hints() -> None:
    report = _validate(_core_facts(), sector="BANK", ticker="BMRI")
    deposit_issue = next(
        i for i in report.issues
        if i.category == "MISSING_MANDATORY_METRIC_OR_EXPLANATION" and i.concept_id == "idx:CustomerDeposits"
    )
    assert "Catatan Simpanan Nasabah" in deposit_issue.feedback_message
    assert "Dana Pihak Ketiga" in deposit_issue.feedback_message or "DPK" in deposit_issue.feedback_message


def _npl_coverage_omission(pages: list[int]) -> OmittedMetricItem:
    return OmittedMetricItem(
        metric_id="idx:NPLCoverageRatio",
        reason="NOT_DISCLOSED_IN_REPORT",
        explanation="The interim financial report does not disclose NPL coverage percentage explicitly in footnotes.",
        search_pages_checked=pages,
    )


def test_validator_omitted_sector_kpi_with_explanation_passes() -> None:
    facts = _core_facts() + _bank_extra_facts()
    report = _validate(facts, sector="BANK", ticker="BMRI", omitted_kpis=[_npl_coverage_omission([22, 23, 24])])
    assert report.status == "VALID", report.issues
    assert report.coverage.high.omitted_with_justification >= 1


def test_validator_omission_contradicted_by_document_text() -> None:
    facts = _core_facts() + _bank_extra_facts()
    document_text = {p: ev.page_text for p, ev in _evidence(facts).items()}
    document_text[23] = HEADER + "Rasio cakupan NPL 245,10% 230,00%"
    report = _validate(
        facts, sector="BANK", ticker="BMRI",
        omitted_kpis=[_npl_coverage_omission([22, 23, 24])], document_text=document_text,
    )
    assert report.status == "INVALID"
    issue = next(i for i in report.issues if i.category == "OMISSION_CONTRADICTED")
    assert issue.concept_id == "idx:NPLCoverageRatio"
    assert 23 in issue.target_pages


def test_validator_omission_pages_outside_document_rejected() -> None:
    facts = _core_facts() + _bank_extra_facts()
    report = _validate(facts, sector="BANK", ticker="BMRI", omitted_kpis=[_npl_coverage_omission(list(range(1, 200)))])
    assert report.status == "INVALID"
    assert any(i.category == "PROVENANCE" and i.concept_id == "idx:NPLCoverageRatio" for i in report.issues)


def test_validator_contradictory_omission_flagged() -> None:
    facts = _core_facts() + _bank_extra_facts()
    omitted = [
        OmittedMetricItem(
            metric_id="idx:NPLCoverageRatio",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="It is disclosed in MD&A on the operational highlights page, but we chose not to extract it.",
            search_pages_checked=[22, 23],
        )
    ]
    report = _validate(facts, sector="BANK", ticker="BMRI", omitted_kpis=omitted)
    assert report.status == "INVALID"
    assert "CONTRADICTORY_OMISSION" in _cats(report)


def test_validator_coverage_block_tracks_buckets() -> None:
    facts = [*_core_facts(), *_bank_extra_facts()[:2], _bank_extra_facts()[3], _bank_extra_facts()[5]]
    report = _validate(facts, sector="BANK", ticker="BMRI")
    assert report.coverage.critical.expected > 0
    assert report.coverage.critical.found > 0
    assert report.coverage.high.expected >= 3


def test_validator_retry_still_missing_message() -> None:
    report = _validate(
        _core_facts(), sector="BANK", ticker="BMRI",
        retry_attempt=2, previous_attempt_misses=["idx:LoansAndAdvances", "idx:CustomerDeposits"],
    )
    retry_issue = next(i for i in report.issues if i.category == "RETRY_STILL_MISSING")
    assert "Attempt 2/3" in retry_issue.feedback_message
    assert "idx:LoansAndAdvances" in retry_issue.feedback_message


# ---------------------------------------------------------------------------
# Schema, period types, identity
# ---------------------------------------------------------------------------


def test_validator_missing_statement_fails() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "100000000000", 5, None, "Total aset")
    report = _validate(facts)
    assert report.status == "INVALID"
    issue = next(i for i in report.issues if i.category == "SCHEMA" and "missing required 'statement'" in i.feedback_message)
    assert "ifrs:Assets" in issue.feedback_message


def test_validator_missing_label_fails() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "100000000000", 5, "BS", None)
    report = _validate(facts, evidence=_evidence(_core_facts()))
    assert any(i.category == "SCHEMA" and "source_label_original" in i.feedback_message for i in report.issues)


def test_validator_invalid_period_type_fails() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "100000000000", 5, "BS", "Total aset", period_type="invalid_type")
    report = _validate(facts)
    assert report.status == "INVALID"
    issue = next(i for i in report.issues if i.category == "SCHEMA" and "invalid period_type" in i.feedback_message)
    assert "ifrs:Assets" in issue.feedback_message


def test_validator_legacy_period_type_is_not_coerced() -> None:
    facts = _core_facts()
    facts[8] = F("ifrs:Revenue", "80000000000", 7, "IS", "Pendapatan", period_type="duration_q")
    assert "SCHEMA" in _cats(_validate(facts))


def test_validator_income_statement_fact_as_instant_is_period_type_mismatch() -> None:
    facts = _core_facts()
    facts[8] = F("ifrs:Revenue", "80000000000", 7, "IS", "Pendapatan", period_type="instant")
    assert "PERIOD_TYPE_MISMATCH" in _cats(_validate(facts))


def test_validator_flow_concept_as_instant_is_period_type_mismatch() -> None:
    cdef = ConceptDefinition(metric_id="ifrs:CostOfSales", name_id="Beban Pokok Penjualan", flow_stock_type="FLOW_PERIOD")
    facts = [F("ifrs:CostOfSales", "3000000000", 7, "NOTE", "Beban pokok penjualan", period_type="instant")]
    report = _validate(facts, concept_defs={"ifrs:CostOfSales": cdef})
    assert "PERIOD_TYPE_MISMATCH" in _cats(report)


def test_validator_unknown_note_concept_needs_explicit_period_type() -> None:
    facts = [F("idx:BiayaPanen", "604326000000", 7, "NOTE", "Biaya panen")]
    report = _validate(facts, concept_defs={})
    assert any(i.category == "SCHEMA" and "period_type" in i.feedback_message for i in report.issues)
    assert "CONCEPT_NOT_IN_ONTOLOGY" in _cats(report, "WARNING")
    flow_as_instant = [F("idx:BiayaPanen", "604326000000", 7, "NOTE", "Biaya panen", period_type="instant")]
    assert "PERIOD_TYPE_MISMATCH" in _cats(_validate(flow_as_instant, concept_defs={}))  # 'biaya' = cost
    stock = [F("idx:LuasKebunPlasma", "29313", 7, "NOTE", "Luas kebun plasma", unit="HECTARES", period_type="instant")]
    assert "PERIOD_TYPE_MISMATCH" not in _cats(_validate(stock, concept_defs={}))
    cogs_component = [F("idx:CostOfGoodsSoldComponent", "604326000000", 7, "NOTE", "Biaya panen", period_type="instant")]
    assert "PERIOD_TYPE_MISMATCH" in _cats(_validate(cogs_component, concept_defs={}))


def test_validator_duplicate_identity_in_payload() -> None:
    facts = [*_core_facts(), F("ifrs:Revenue", "80000000000", 7, "IS", "Pendapatan")]
    report = _validate(facts)
    assert "DUPLICATE_FACT" in _cats(report)


def test_validator_same_concept_different_period_type_is_not_duplicate() -> None:
    facts = [*_core_facts(), F("ifrs:Revenue", "30000000000", 7, "IS", "Pendapatan", period_type="duration_qtd")]
    assert "DUPLICATE_FACT" not in _cats(_validate(facts))


# ---------------------------------------------------------------------------
# Concept <-> label
# ---------------------------------------------------------------------------

_CCE = ConceptDefinition(
    metric_id="ifrs:CashAndCashEquivalents",
    name_id="Kas dan Setara Kas",
    name_en="Cash and Cash Equivalents",
    synonyms_id=["Kas dan Bank", "Kas dan Deposito"],
    flow_stock_type="STOCK_POINT_IN_TIME",
)


def test_validator_concept_label_mismatch_kas_is_not_cash_equivalents() -> None:
    facts = [F("ifrs:CashAndCashEquivalents", "33857220000000", 22, "BS", "Kas")]
    report = _validate(facts, concept_defs={"ifrs:CashAndCashEquivalents": _CCE})
    assert "CONCEPT_LABEL_MISMATCH" in _cats(report)


def test_validator_concept_label_match_passes() -> None:
    facts = [F("ifrs:CashAndCashEquivalents", "379877189000000", 38, "CF", "Kas dan setara kas akhir tahun")]
    report = _validate(facts, concept_defs={"ifrs:CashAndCashEquivalents": _CCE})
    assert "CONCEPT_LABEL_MISMATCH" not in _cats(report)


# ---------------------------------------------------------------------------
# Grounding (cell / text / OCR / provenance)
# ---------------------------------------------------------------------------


def _bs_table_page() -> PageEvidence:
    """Page 5 with a real-looking two-period table (current column 1, prior column 2)."""
    return PageEvidence(
        page_index=5,
        text_source="pdf_text",
        page_text=HEADER + "31 Desember 2024 31 Desember 2023\nTotal aset 100.000 90.000",
        tables=[
            PageTable(
                table_index=0,
                confidence=0.9,
                unit_hint="IDR_MN",
                cells=[
                    PageTableCell(row=0, col=1, text="31 Desember 2024", value=None),
                    PageTableCell(row=0, col=2, text="31 Desember 2023", value=None),
                    PageTableCell(row=1, col=0, text="Total aset", value=None),
                    PageTableCell(row=1, col=1, text="100.000", value=100000.0, confidence=0.95, bbox=[300.0, 200.0, 360.0, 210.0]),
                    PageTableCell(row=1, col=2, text="90.000", value=90000.0, confidence=0.95),
                    PageTableCell(row=2, col=0, text="Total liabilitas", value=None),
                    PageTableCell(row=2, col=1, text="40.000", value=40000.0),
                    PageTableCell(row=2, col=2, text="35.000", value=35000.0),
                ],
            )
        ],
    )


def _with_page5(facts: list[ExtractedFactItem]) -> dict[int, PageEvidence]:
    ev = _evidence(facts)
    ev[5] = _bs_table_page()
    ev[5].page_text += "\n" + "\n".join(f"{f.source_label_original} {_printed(f)}" for f in facts if f.source_page == 5 and f.cell_ref is None)
    return ev


def test_validator_correct_cell_ref_millions_scale_passes() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "100000000000", 5, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=1))
    report = _validate(facts, evidence=_with_page5(facts), page_count=10)
    assert report.status == "VALID", report.issues
    assert not any(i.category.startswith("GROUNDING") for i in report.issues)


def test_validator_cell_ref_transposed_digit_fails_grounding_cell() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "100200000000", 5, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=1))
    report = _validate(facts, evidence=_with_page5(facts), page_count=10)
    assert report.status == "INVALID"
    cell_issue = next(i for i in report.issues if i.category == "GROUNDING_CELL")
    assert 5 in cell_issue.target_pages


def test_validator_prior_year_cell_fails_column_period() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "90000000000", 5, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=1, col=2))
    report = _validate(facts, evidence=_with_page5(facts), page_count=10)
    assert "GROUNDING_COLUMN_PERIOD" in _cats(report)


def test_validator_wrong_row_cell_fails_row_label() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "40000000000", 5, "BS", "Total aset", cell_ref=CellRef(table_index=0, row=2, col=1))
    report = _validate(facts, evidence=_with_page5(facts), page_count=10)
    assert "ROW_LABEL_MISMATCH" in _cats(report)


def test_validator_text_fact_absent_fails_grounding_text() -> None:
    facts = _core_facts()
    evidence = _evidence(facts)
    evidence[5].page_text = "Laporan Posisi Keuangan tanpa angka sama sekali"
    report = _validate(facts, evidence=evidence, page_count=10)
    assert report.status == "INVALID"
    text_issue = next(i for i in report.issues if i.category == "GROUNDING_TEXT")
    assert 5 in text_issue.target_pages


def test_validator_text_value_far_from_label_fails() -> None:
    facts = _core_facts()
    evidence = _evidence(facts)
    evidence[7].page_text = (
        HEADER + "Pendapatan\nketerangan satu\nketerangan dua\nketerangan tiga\nketerangan empat\n"
        "Lain-lain 80.000\nLaba usaha 25.000\nLaba tahun berjalan 18.000"
    )
    report = _validate(facts, evidence=evidence)
    assert "GROUNDING_TEXT_LABEL_DISTANCE" in _cats(report)


def test_validator_ocr_page_miss_gives_warning_status_valid() -> None:
    facts = _core_facts()
    evidence = _evidence(facts)
    evidence[5].text_source = "ocr"
    evidence[5].page_text = "Teks buram hasil scan tanpa angka yang jelas"
    report = _validate(facts, evidence=evidence, page_count=10)
    assert report.status == "VALID", report.issues
    ocr_issue = next(i for i in report.issues if i.category == "GROUNDING_OCR")
    assert ocr_issue.severity.value == "WARNING"
    assert ocr_issue.details.get("needs_review") is True


def test_validator_ocr_failed_page_is_an_error() -> None:
    facts = _core_facts()
    evidence = _evidence(facts)
    evidence[5].text_source = "ocr_failed"
    evidence[5].page_text = ""
    assert "GROUNDING_OCR_FAILED" in _cats(_validate(facts, evidence=evidence))


def test_validator_source_page_exceeds_page_count_fails_provenance() -> None:
    facts = _core_facts()
    facts[0] = F("ifrs:Assets", "100000000000", 11, "BS", "Total aset")
    report = _validate(facts, page_count=10)
    assert report.status == "INVALID"
    prov_issue = next(i for i in report.issues if i.category == "PROVENANCE")
    assert 11 in prov_issue.target_pages


def test_validator_cited_page_not_indexed_fails_provenance() -> None:
    facts = _core_facts()
    evidence = _evidence(facts)
    del evidence[8]
    assert "PROVENANCE" in _cats(_validate(facts, evidence=evidence))


# ---------------------------------------------------------------------------
# Anti-synthetic
# ---------------------------------------------------------------------------


def test_validator_aali_synthetic_fixture_fails_synthetic_label_and_split() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "m9" / "aali_synthetic_payload.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    payload = DraftSubmissionPayload.model_validate(data)
    evidence = {
        3: PageEvidence(
            page_index=3,
            text_source="pdf_text",
            page_text="Laporan Laba Rugi Komprehensif PT Astra Agro Lestari Tbk\nPendapatan Bersih: 1.000\nBeban: 800",
        )
    }
    report = validate_draft_submission(payload, contract=make_test_contract("GENERIC"), evidence=evidence, page_count=50)
    assert report.status == "INVALID"
    assert {"SYNTHETIC_LABEL", "SYNTHETIC_SPLIT"} <= _cats(report)


def _revenue_split(labels: tuple[str, str], values: tuple[str, str], key: str = "segment") -> list[ExtractedFactItem]:
    return [
        F("ifrs:Revenue", "1000", 28, "NOTE", "Total pendapatan", period_type="duration_ytd"),
        F("ifrs:Revenue", values[0], 28, "NOTE", labels[0], period_type="duration_ytd", segment={key: labels[0], "type": "product"}),
        F("ifrs:Revenue", values[1], 28, "NOTE", labels[1], period_type="duration_ytd", segment={key: labels[1], "type": "product"}),
    ]


def _plain_page(p: int, text: str) -> dict[int, PageEvidence]:
    return {p: PageEvidence(page_index=p, text_source="pdf_text", page_text=text)}


def test_validator_genuine_grounded_split_50_50_passes() -> None:
    facts = _revenue_split(("Minyak Kelapa Sawit", "Inti Sawit"), ("500", "500"))
    evidence = _plain_page(28, "Catatan 28. Rincian Pendapatan:\nMinyak Kelapa Sawit: 500\nInti Sawit: 500\nTotal pendapatan: 1.000")
    report = _validate(facts, evidence=evidence)
    assert not ({"SYNTHETIC_LABEL", "SYNTHETIC_SPLIT"} & _cats(report))


def test_validator_near_round_split_with_ungrounded_child_fails() -> None:
    facts = _revenue_split(("Minyak Kelapa Sawit", "Inti Sawit"), ("703", "297"))
    evidence = _plain_page(28, "Catatan 28. Rincian Pendapatan:\nMinyak Kelapa Sawit: 703\nTotal pendapatan: 1.000")
    assert "SYNTHETIC_SPLIT" in _cats(_validate(facts, evidence=evidence))


def test_validator_placeholder_label_verbatim_on_page_passes_synthetic_label() -> None:
    facts = _revenue_split(("Primary Operations", "Other Operations"), ("700", "300"))
    evidence = _plain_page(28, "Segment Breakdown:\nPrimary Operations: 700\nOther Operations: 300\nTotal pendapatan: 1.000")
    report = _validate(facts, evidence=evidence)
    assert not ({"SYNTHETIC_LABEL", "SYNTHETIC_SPLIT"} & _cats(report))


def test_validator_placeholder_under_other_segment_key_still_rejected() -> None:
    facts = _revenue_split(("Primary Operations", "Other Operations"), ("700", "300"), key="division")
    evidence = _plain_page(28, "Rincian:\nTotal pendapatan: 1.000")
    assert {"SYNTHETIC_LABEL", "SYNTHETIC_SPLIT"} <= _cats(_validate(facts, evidence=evidence))


def test_validator_only_child_lainnya_without_verbatim_fails_synthetic_label() -> None:
    facts = [
        F("ifrs:Revenue", "1000", 10, "NOTE", "Lainnya", period_type="duration_ytd", segment={"segment": "Lainnya", "type": "product"}),
    ]
    evidence = _plain_page(10, "Pendapatan jasa dan perdagangan: 1.000")
    report = _validate(facts, evidence=evidence)
    assert report.status == "INVALID"
    label_issue = next(i for i in report.issues if i.category == "SYNTHETIC_LABEL")
    assert label_issue.concept_id == "ifrs:Revenue"


def test_validator_only_child_lainnya_elsewhere_on_page_still_fails() -> None:
    facts = [
        F("ifrs:Revenue", "1000", 10, "NOTE", "Lainnya", period_type="duration_ytd", segment={"segment": "Lainnya", "type": "product"}),
    ]
    evidence = _plain_page(10, "Pendapatan jasa dan perdagangan: 1.000\n\n\n\n\nLainnya: 12")
    assert "SYNTHETIC_LABEL" in _cats(_validate(facts, evidence=evidence))


def test_validator_segmented_fact_without_source_page_fails_segment_provenance() -> None:
    facts = [F("ifrs:Revenue", "500", None, "NOTE", "CPO", period_type="duration_ytd", segment={"segment": "CPO", "type": "product"})]
    report = _validate(facts, evidence={})
    assert report.status == "INVALID"
    seg_prov = next(i for i in report.issues if i.category == "SEGMENT_PROVENANCE")
    assert seg_prov.concept_id == "ifrs:Revenue"


# ---------------------------------------------------------------------------
# Sums and tie-outs
# ---------------------------------------------------------------------------


def _loan_matrix(korporasi: str) -> list[ExtractedFactItem]:
    def child(seg: str, v: str) -> ExtractedFactItem:
        return F("idx:LoansGross", v, 22, "NOTE", seg, period_type="instant", segment={"segment": seg, "type": "customer_type"})

    return [
        F("idx:LoansGross", "80000000000", 22, "NOTE", "Total pinjaman yang diberikan", period_type="instant"),
        child("Korporasi", korporasi),
        child("Komersial", "17200000000"),
        child("Ritel", "11000000000"),
        child("UMKM", "6300000000"),
    ]


def test_validator_loan_matrix_children_summing_to_total_passes() -> None:
    facts = _loan_matrix("45500000000")
    assert "SUM_MISMATCH" not in _cats(_validate(facts, sector="BANK", ticker="BMRI"))


def test_validator_children_off_by_five_percent_fails_sum_mismatch() -> None:
    facts = _loan_matrix("41500000000")
    report = _validate(facts, sector="BANK", ticker="BMRI")
    assert report.status == "INVALID"
    sum_issue = next(i for i in report.issues if i.category == "SUM_MISMATCH")
    assert sum_issue.concept_id == "idx:LoansGross"
    assert "80,000,000,000" in sum_issue.feedback_message
    assert "76,000,000,000" in sum_issue.feedback_message


def test_validator_sum_groups_by_segment_key_set() -> None:
    # A second breakdown under a different key set is checked on its own (and here is short).
    facts = [
        *_loan_matrix("45500000000"),
        F("idx:LoansGross", "50000000000", 22, "NOTE", "Rupiah", period_type="instant", segment={"currency": "Rupiah"}),
    ]
    issue = next(i for i in _validate(facts, sector="BANK", ticker="BMRI").issues if i.category == "SUM_MISMATCH")
    assert "currency" in issue.feedback_message


def test_validator_note_total_equal_prior_year_bs_fails_tie_out_with_column_hint() -> None:
    facts = [
        F("idx:LoansAndAdvances", "80000000000", 6, "BS", "Kredit yang diberikan"),
        F("idx:LoansGross", "70000000000", 22, "NOTE", "Jumlah pinjaman yang diberikan", period_type="instant"),
    ]
    report = _validate(facts, sector="BANK", ticker="BMRI", fiscal_period="2025Q4")
    tie_issue = next(i for i in report.issues if i.category == "TIE_OUT")
    assert tie_issue.concept_id == "idx:LoansGross"
    assert "check you used the current-period column" in tie_issue.feedback_message.lower()


def test_validator_cash_tie_out_ignores_statement_label() -> None:
    facts = [
        F("ifrs:CashAndCashEquivalents", "33857220000000", 22, "NOTE", "Kas dan setara kas"),
        F("idx:CashAtEndOfPeriod", "379877189000000", 38, "CF", "Kas dan setara kas akhir tahun"),
    ]
    report = _validate(facts, sector="BANK", ticker="BMRI")
    assert any(i.category == "TIE_OUT" and i.details.get("rule") == "bs_cash_to_cf_ending_cash" for i in report.issues)


# ---------------------------------------------------------------------------
# Narratives
# ---------------------------------------------------------------------------


def _narr(text: str, page: int = 15, section: str = "MDA") -> ExtractedNarrativeItem:
    return ExtractedNarrativeItem(section=section, text_original=text, source_page=page, topic="T")


def _narr_report(narr: ExtractedNarrativeItem, page_text: str, **kw: object):  # type: ignore[no-untyped-def]
    return _validate([], evidence=_plain_page(narr.source_page, page_text), narratives=[narr], ticker="LSIP", **kw)


def test_validator_narrative_boilerplate_fails() -> None:
    text = "Catatan atas laporan keuangan terlampir merupakan bagian integral dari laporan keuangan konsolidasian ini"
    report = _narr_report(_narr(text, 5, "FOOTNOTE"), text + ".")
    assert report.status == "INVALID"
    issue = next(i for i in report.issues if i.category == "NARRATIVE_BOILERPLATE")
    assert "boilerplate" in issue.feedback_message.lower()


def test_validator_narrative_not_verbatim_fails() -> None:
    page = "Penjualan CPO meningkat menjadi 1.200.000 ton pada tahun 2025 karena kenaikan produksi TBS inti."
    report = _narr_report(_narr("Manajemen berkomitmen memperkuat penyaluran kredit ke sektor produktif pada 2025."), page)
    assert "NARRATIVE_NOT_VERBATIM" in _cats(report)
    ok = _narr_report(_narr("Penjualan CPO meningkat menjadi 1.200.000 ton pada tahun 2025"), page)
    assert "NARRATIVE_NOT_VERBATIM" not in _cats(ok)


def test_validator_narrative_cross_issuer_duplicate_fails() -> None:
    text_dup = "Direksi berpendapat bahwa cadangan kerugian penurunan nilai telah memadai."
    report = _narr_report(
        _narr(text_dup, 12, "FOOTNOTE"), text_dup,
        cross_issuer_narrative_hashes={narrative_md5(text_dup): "BBCA"},
    )
    assert report.status == "INVALID"
    issue = next(i for i in report.issues if i.category == "NARRATIVE_DUPLICATE")
    assert "BBCA" in issue.feedback_message


def test_validator_narrative_same_issuer_prior_period_passes() -> None:
    text = "Direksi berpendapat bahwa cadangan kerugian penurunan nilai telah memadai."
    report = _narr_report(_narr(text, 12, "FOOTNOTE"), text, cross_issuer_narrative_hashes={narrative_md5(text): "LSIP"})
    assert "NARRATIVE_DUPLICATE" not in _cats(report)


def test_validator_narrative_anchored_mda_passes() -> None:
    anchored_text = "Pendapatan naik 12% menjadi Rp4,2 triliun didorong volume CPO"
    report = _narr_report(_narr(anchored_text), "Analisa manajemen\n" + anchored_text + "\n")
    assert not ({"NARRATIVE_GENERIC", "NARRATIVE_BOILERPLATE", "NARRATIVE_NOT_VERBATIM"} & _cats(report))

    generic_text = "Perusahaan terus berkomitmen untuk memberikan kinerja terbaik bagi seluruh pemangku kepentingan."
    generic_report = _narr_report(_narr(generic_text), generic_text)
    assert generic_report.status == "INVALID"
    assert "NARRATIVE_GENERIC" in _cats(generic_report)


def test_validator_narrative_with_edited_number_or_name_is_not_verbatim() -> None:
    page = (
        "Pada tahun 2025, PT Contoh Tbk mencatatkan peningkatan pendapatan sebesar 11,1% menjadi "
        "Rp20.000 miliar dibandingkan tahun 2024 sebesar Rp18.000 miliar."
    )
    exact = "Pada tahun 2025, PT Contoh Tbk mencatatkan peningkatan pendapatan sebesar 11,1% menjadi Rp20.000 miliar"
    edited_number = exact.replace("11,1%", "25,0%")
    edited_name = exact.replace("PT Contoh Tbk", "PT Bank Lain Tbk")
    assert "NARRATIVE_NOT_VERBATIM" not in _cats(_narr_report(_narr(exact), page))
    assert "NARRATIVE_NOT_VERBATIM" in _cats(_narr_report(_narr(edited_number), page))
    assert "NARRATIVE_NOT_VERBATIM" in _cats(_narr_report(_narr(edited_name), page))
