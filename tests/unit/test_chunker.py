"""Unit tests for semantic narrative chunking and section classification."""

from services.narrative.chunker import chunk_pages, classify_section, is_digit_heavy
from services.shared.types import PageContent


def test_classify_section() -> None:
    assert (
        classify_section("Tinjauan kinerja perseroan", "Management Discussion & Analysis") == "MDA"
    )
    assert classify_section("Analisis profil risiko kredit dan likuiditas") == "RISK"
    assert classify_section("Panduan target pertumbuhan kredit 2025") == "GUIDANCE"
    assert classify_section("Catatan atas laporan keuangan konsolidasian") == "FOOTNOTE"
    assert classify_section("Informasi umum perusahaan") == "OTHER"


def test_is_digit_heavy() -> None:
    assert is_digit_heavy("123.456 789.012 345.678") is True
    assert is_digit_heavy("Sepanjang tahun 2024 bank mencatatkan pertumbuhan laba.") is False


def test_chunk_pages() -> None:
    pages = [
        PageContent(
            page_num=1,
            text="DISKUSI DAN ANALISIS MANAJEMEN\n\nPerseroan mencatatkan kinerja memuaskan pada tahun 2024 didukung oleh transformasi digital yang berkelanjutan.",
            language="id",
            has_text_layer=True,
        ),
    ]

    chunks = chunk_pages(pages, ticker="BMRI", doc_type="FS_QUARTERLY", fiscal_period="2024Q4")
    assert len(chunks) == 1
    assert chunks[0].section == "MDA"
    assert "transformasi digital" in chunks[0].text_original
    assert chunks[0].mentioned_periods == ["2024Q4"]
