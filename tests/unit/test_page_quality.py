"""Unit tests for page quality heuristics and OCR necessity detection."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from services.extraction.page_quality import needs_ocr
from tests.fixtures.m9.build_fixtures import build_scanned


def test_needs_ocr_empty_and_whitespace() -> None:
    assert needs_ocr("") is True
    assert needs_ocr("   \n\t  ") is True


def test_needs_ocr_valid_sample_text() -> None:
    assert needs_ocr("Jumlah aset 1.234.567") is False
    assert needs_ocr("Laporan Posisi Keuangan Konsolidasian PT Bank Mandiri (Persero) Tbk") is False


def test_needs_ocr_scanned_fixture(tmp_path: Path) -> None:
    scanned_path = tmp_path / "scanned_test.pdf"
    build_scanned(scanned_path)

    doc = pymupdf.open(str(scanned_path))  # type: ignore[no-untyped-call]
    assert len(doc) == 2
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text("text")  # type: ignore[no-untyped-call]
        assert needs_ocr(text) is True
    doc.close()  # type: ignore[no-untyped-call]


def test_needs_ocr_corrupted_glyphs() -> None:
    # 50% replacement characters
    corrupted = "Valid text" + ("\ufffd" * 15)
    assert needs_ocr(corrupted) is True


def test_detect_page_label() -> None:
    from services.ingest.tasks.index_pages import detect_page_label

    doc = pymupdf.open()  # type: ignore[no-untyped-call]

    # Page 1: footer standalone number 42
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((290, 800), "42", fontsize=10)
    assert detect_page_label(p1) == "42"

    # Page 2: footer roman numeral
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((290, 800), "iv", fontsize=10)
    assert detect_page_label(p2) == "iv"

    # Page 3: header standalone number
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((550, 40), "7", fontsize=10)
    assert detect_page_label(p3) == "7"

    # Page 4: header year 2025 (should be ignored)
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text((50, 40), "2025", fontsize=10)
    assert detect_page_label(p4) is None

    # Page 5: normal text, no standalone page number
    p5 = doc.new_page(width=595, height=842)
    p5.insert_text((50, 40), "LAPORAN KEUANGAN KONSOLIDASIAN", fontsize=10)
    p5.insert_text((50, 800), "Halaman 1 dari 10", fontsize=9)
    assert detect_page_label(p5) is None
    doc.close()  # type: ignore[no-untyped-call]
