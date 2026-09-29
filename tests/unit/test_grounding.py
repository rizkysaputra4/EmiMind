"""Unit tests for number normalization and grounding utilities."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from services.mcp.grounding import (
    check_cell_grounding,
    check_text_grounding,
    ground_fact,
    normalize_candidates,
    resolve_scale,
    token_matches,
    tokenize_numbers,
)
from services.mcp.types import CellRef, ExtractedFactItem, PageEvidence, PageTable, PageTableCell


def test_normalize_candidates_core_cases() -> None:
    # 1. Indonesian thousand dot separator
    res1 = normalize_candidates("1.234.567")
    assert 1234567 in res1 or Decimal("1234567") in res1

    # 2. Parentheses negative
    res2 = normalize_candidates("(12.345)")
    assert -12345 in res2 or Decimal("-12345") in res2

    # 3. Standard comma thousand separator
    res3 = normalize_candidates("1,234,567")
    assert 1234567 in res3 or Decimal("1234567") in res3


def test_normalize_candidates_extended() -> None:
    # Negative with minus sign
    res_neg = normalize_candidates("-500.000")
    assert Decimal("-500000") in res_neg

    # Indonesian currency prefix and decimals
    res_curr = normalize_candidates("Rp 1.234.567,89")
    assert Decimal("1234567.89") in res_curr

    # Trailing ,00
    res_zero = normalize_candidates("1.234.567,00")
    assert Decimal("1234567") in res_zero

    # Embedded in sentence
    res_sent = normalize_candidates("Jumlah aset lancar 1.234.567 dan liabilitas (12.345)")
    assert Decimal("1234567") in res_sent
    assert Decimal("-12345") in res_sent


def test_resolve_scale() -> None:
    assert resolve_scale("jutaan rupiah") == Decimal("1000000")
    assert resolve_scale("IDR_MN") == Decimal("1000000")
    assert resolve_scale("miliaran rupiah") == Decimal("1000000000")
    assert resolve_scale("IDR_BN") == Decimal("1000000000")
    assert resolve_scale("ribuan rupiah") == Decimal("1000")
    assert resolve_scale("IDR_TH") == Decimal("1000")
    assert resolve_scale("IDR") == Decimal("1")
    assert resolve_scale(None, {"scale": 1000000}) == Decimal("1000000")
    assert resolve_scale(None) == Decimal("1")


def test_check_cell_grounding_pass() -> None:
    page_ev = PageEvidence(
        page_index=5,
        text_source="pdf_text",
        page_text="Catatan atas laporan keuangan...",
        tables=[
            PageTable(
                table_index=0,
                unit_hint="jutaan rupiah",
                cells=[
                    PageTableCell(row=2, col=1, text="1.234.567", value=1234567.0, confidence=0.95),
                ],
            )
        ],
    )

    fact = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("1234567000000"),  # 1,234,567 * 1,000,000
        source_page=5,
        cell_ref=CellRef(table_index=0, row=2, col=1),
    )

    is_grounded, err_msg, conf, _bbox = check_cell_grounding(fact, page_ev)
    assert is_grounded is True
    assert err_msg is None
    assert conf == 0.95


def test_check_cell_grounding_fail_mismatch() -> None:
    page_ev = PageEvidence(
        page_index=5,
        text_source="pdf_text",
        tables=[
            PageTable(
                table_index=0,
                unit_hint="jutaan rupiah",
                cells=[
                    PageTableCell(row=2, col=1, text="1.234.567", value=1234567.0),
                ],
            )
        ],
    )

    # Transposed digit in fact value
    fact = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("1234657000000"),
        source_page=5,
        cell_ref=CellRef(table_index=0, row=2, col=1),
    )

    is_grounded, err_msg, _conf, _bbox = check_cell_grounding(fact, page_ev)
    assert is_grounded is False
    assert err_msg is not None
    assert "does not match" in err_msg


def test_check_text_grounding_pass() -> None:
    page_ev = PageEvidence(
        page_index=7,
        text_source="pdf_text",
        page_text="Penjualan produk CPO tercatat sebesar 1.234.567 ton pada tahun berjalan.",
    )

    fact = ExtractedFactItem(
        concept_id="idx:CpoProduction",
        value_numeric=Decimal("1234567"),
        source_page=7,
    )

    is_grounded, err_msg = check_text_grounding(fact, page_ev)
    assert is_grounded is True
    assert err_msg is None


def test_check_text_grounding_fail() -> None:
    page_ev = PageEvidence(
        page_index=7,
        text_source="pdf_text",
        page_text="Penjualan produk CPO tercatat sebesar 999.000 ton pada tahun berjalan.",
    )

    fact = ExtractedFactItem(
        concept_id="idx:CpoProduction",
        value_numeric=Decimal("1234567"),
        source_page=7,
    )

    is_grounded, err_msg = check_text_grounding(fact, page_ev)
    assert is_grounded is False
    assert err_msg is not None
    assert "not found in text" in err_msg


# ---------------------------------------------------------------------------
# One scale, strict tokens (M9 remediation, workstream B item 2)
# ---------------------------------------------------------------------------

def _text_page(text: str, source: str = "pdf_text") -> PageEvidence:
    return PageEvidence(page_index=3, text_source=source, page_text=text)


def _fact(value: str, label: str, unit: str = "IDR") -> ExtractedFactItem:
    return ExtractedFactItem(
        concept_id="ifrs:Revenue",
        value_numeric=Decimal(value),
        unit=unit,
        source_page=3,
        statement="IS",
        source_label_original=label,
    )


def test_year_never_grounds_an_amount() -> None:
    page = _text_page("(Disajikan dalam jutaan Rupiah)\nPendapatan tahun 2025")
    out = ground_fact(_fact("2025000000", "Pendapatan"), page, period_end=date(2025, 12, 31))
    assert not out.ok
    assert out.issues[0][1] == "GROUNDING_TEXT"


def test_only_the_page_scale_is_tried() -> None:
    # The page is in millions: the raw number 80.000 must not ground 80,000 full rupiah.
    page = _text_page("(Disajikan dalam jutaan Rupiah)\nPendapatan 80.000")
    assert ground_fact(_fact("80000000000", "Pendapatan"), page, period_end=None).ok
    assert not ground_fact(_fact("80000", "Pendapatan"), page, period_end=None).ok


def test_percent_fraction_and_percent_number_both_ground() -> None:
    page = _text_page("Rasio kecukupan modal 19,36%")
    for v in ("0.1936", "19.36"):
        assert ground_fact(_fact(v, "Rasio kecukupan modal", unit="PERCENT"), page, period_end=None).ok
    assert not ground_fact(_fact("0.1963", "Rasio kecukupan modal", unit="PERCENT"), page, period_end=None).ok


def test_rupiah_triliun_and_miliar_words() -> None:
    tok = next(t for t in tokenize_numbers("naik menjadi Rp4,2 triliun") if t.multiplier)
    assert token_matches(tok, Decimal("4200000000000"), Decimal(1))
    assert not token_matches(tok, Decimal("4300000000000"), Decimal(1))
    tok_bn = next(t for t in tokenize_numbers("sebesar Rp350 miliar") if t.multiplier)
    assert token_matches(tok_bn, Decimal("350000000000"), Decimal(1))


def test_en_dash_negative_and_dash_cell() -> None:
    neg = next(t for t in tokenize_numbers("Rugi selisih kurs –1.234") if not t.is_dash)
    assert neg.values[0] == Decimal("-1234")
    dash = next(t for t in tokenize_numbers("Liabilitas kontrak - 4.234") if t.is_dash)
    assert token_matches(dash, Decimal(0), Decimal(1_000_000))
    assert not token_matches(dash, Decimal(5), Decimal(1))


def test_unit_hint_codes_and_page_header() -> None:
    assert resolve_scale("IDR_K") == Decimal(1000)
    assert resolve_scale("expressed in billions of rupiah") == Decimal(10) ** 9
    page = _text_page("(Expressed in Millions of Rupiah, Unless Otherwise Stated)\nRevenue 5.511.706")
    fact = ExtractedFactItem(
        concept_id="ifrs:Revenue", value_numeric=Decimal("5511706000000"), source_page=3,
        statement="IS", source_label_original="Revenue",
    )
    out = ground_fact(fact, page, period_end=None)
    assert out.ok and out.scale == Decimal(10) ** 6 and out.scale_source == "page header"


def test_ocr_failed_page_cannot_ground() -> None:
    out = ground_fact(_fact("80000000000", "Pendapatan"), _text_page("", "ocr_failed"), period_end=None)
    assert not out.ok
    assert out.issues[0][1] == "GROUNDING_OCR_FAILED"


def test_cell_confidence_is_min_of_table_and_cell_and_synthetic_bbox_dropped() -> None:
    page = PageEvidence(
        page_index=5,
        tables=[
            PageTable(
                table_index=0,
                confidence=0.85,
                unit_hint="IDR_MN",
                cells=[
                    PageTableCell(row=1, col=0, text="Total aset", value=None),
                    PageTableCell(row=1, col=1, text="1.234", value=1234.0, confidence=0.95, bbox=[0.0, 15.0, 500.0, 30.0]),
                ],
            )
        ],
    )
    fact = ExtractedFactItem(
        concept_id="ifrs:Assets", value_numeric=Decimal("1234000000"), source_page=5, statement="BS",
        source_label_original="Total aset", cell_ref=CellRef(table_index=0, row=1, col=1),
    )
    out = ground_fact(fact, page, period_end=None)
    assert out.ok and out.kind == "cell"
    assert out.confidence == 0.85
    assert out.bbox is None  # legacy synthesized [0, 15r, 500, 15(r+1)] box
