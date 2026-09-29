"""Unit tests for page quality heuristics, OCR necessity and printed page labels."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from services.extraction.page_quality import OCR_MIN_CHARS, needs_ocr, non_whitespace_len
from tests.fixtures.m9.build_fixtures import build_scanned


def test_needs_ocr_empty_and_whitespace() -> None:
    assert needs_ocr("") is True
    assert needs_ocr("   \n\t  ") is True


def test_needs_ocr_min_chars_is_50() -> None:
    assert OCR_MIN_CHARS == 50
    # short strings are "near-empty" by spec (< 50 non-whitespace chars) -> OCR
    assert needs_ocr("Jumlah aset 1.234.567") is True
    assert needs_ocr("x" * 49) is True
    assert needs_ocr("x" * 50) is False


def test_needs_ocr_valid_sample_text() -> None:
    page = (
        "Laporan Posisi Keuangan Konsolidasian PT Bank Mandiri (Persero) Tbk\n"
        "Jumlah aset 1.234.567 Jumlah liabilitas 987.654"
    )
    assert non_whitespace_len(page) >= 50
    assert needs_ocr(page) is False


def test_needs_ocr_scanned_fixture(tmp_path: Path) -> None:
    scanned_path = tmp_path / "scanned_test.pdf"
    build_scanned(scanned_path)

    doc = pymupdf.open(str(scanned_path))
    assert len(doc) == 2
    for page_idx in range(len(doc)):
        text = doc[page_idx].get_text("text")
        assert needs_ocr(text) is True
    doc.close()


def test_needs_ocr_corrupted_glyphs() -> None:
    corrupted = "Valid text of a reasonable length for a page " + ("�" * 40)
    assert non_whitespace_len(corrupted) >= 50
    assert needs_ocr(corrupted) is True


def _page_with(doc: pymupdf.Document, *items: tuple[float, float, str, float]) -> pymupdf.Page:
    page = doc.new_page(width=595, height=842)
    for x, y, txt, size in items:
        page.insert_text((x, y), txt, fontsize=size)
    return page


def test_detect_page_label_accepts_standalone_numbers_and_markers() -> None:
    from services.ingest.tasks.index_pages import detect_page_label

    doc = pymupdf.open()
    try:
        assert detect_page_label(_page_with(doc, (290, 820, "42", 10))) == "42"
        assert detect_page_label(_page_with(doc, (290, 820, "iv", 10))) == "iv"
        assert detect_page_label(_page_with(doc, (290, 820, "- 12 -", 10))) == "12"
        assert detect_page_label(_page_with(doc, (550, 30, "7", 10))) == "7"
        # explicit markers inside the 12% band (AALI prints "Lampiran 5/27 Schedule")
        assert detect_page_label(_page_with(doc, (250, 85, "Lampiran 5/27 Schedule", 10))) == "5/27"
        assert detect_page_label(_page_with(doc, (50, 820, "Halaman 1 dari 10", 9))) == "1"
    finally:
        doc.close()


def test_detect_page_label_rejects_false_positives() -> None:
    from services.ingest.tasks.index_pages import detect_page_label

    doc = pymupdf.open()
    try:
        # header year
        assert detect_page_label(_page_with(doc, (50, 30, "2025", 10))) is None
        # a table value in the body (the old detector labelled AALI pages '781', '63', ...)
        assert detect_page_label(_page_with(doc, (400, 500, "781", 10))) is None
        # a bare number just outside the 8% band (block y0 < 92% of the page)
        assert detect_page_label(_page_with(doc, (290, 770, "63", 10))) is None
        # words made of roman letters are not roman numerals
        assert detect_page_label(_page_with(doc, (290, 820, "lid", 10))) is None
        # a sentence in the footer
        assert (
            detect_page_label(
                _page_with(doc, (50, 820, "Catatan atas laporan keuangan merupakan bagian 12", 8))
            )
            is None
        )
        # running header text
        assert (
            detect_page_label(_page_with(doc, (50, 30, "LAPORAN KEUANGAN KONSOLIDASIAN", 10)))
            is None
        )
    finally:
        doc.close()
