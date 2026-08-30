"""Unit tests for PDF parsing and language detection."""

from __future__ import annotations

from pathlib import Path

from services.extraction.pdf import detect_language, parse_pdf

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_detect_language_indonesian() -> None:
    text = "Laporan posisi keuangan konsolidasian untuk tahun yang berakhir pada tanggal 31 Desember 2024."
    lang = detect_language(text)
    assert lang == "id"


def test_detect_language_english() -> None:
    text = "Consolidated financial statements for the year ended 31 December 2024 and independent auditor report."
    lang = detect_language(text)
    assert lang == "en"


def test_parse_sample_pdf() -> None:
    pdf_path = FIXTURES_DIR / "sample_bmri.pdf"
    assert pdf_path.exists()

    pdf_bytes = pdf_path.read_bytes()
    pages = parse_pdf(pdf_bytes)

    assert len(pages) == 3
    assert pages[0].page_num == 1
    assert pages[0].has_text_layer is True
    assert "DISKUSI DAN ANALISIS MANAJEMEN" in pages[0].text
    assert pages[1].page_num == 2
    assert "LAPORAN POSISI KEUANGAN" in pages[1].text
