"""Unit tests for number normalization and grounding utilities."""

from __future__ import annotations

from decimal import Decimal

from services.mcp.grounding import (
    check_cell_grounding,
    check_text_grounding,
    normalize_candidates,
    resolve_scale,
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
