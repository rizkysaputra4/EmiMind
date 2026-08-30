"""Unit tests for table extraction and numeric parsing."""

from __future__ import annotations

from pathlib import Path

from services.extraction.pdf import parse_pdf
from services.extraction.tables import (
    detect_unit_from_header,
    extract_tables,
    parse_numeric_value,
    tables_to_facts,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_parse_numeric_value() -> None:
    assert parse_numeric_value("1.530.000") == 1530000.0
    assert parse_numeric_value("(45.200)") == -45200.0
    assert parse_numeric_value("Rp 55.420") == 55420.0
    assert parse_numeric_value("-") == 0.0
    assert parse_numeric_value("1,234.56") == 1234.56


def test_detect_unit_from_header() -> None:
    assert detect_unit_from_header("dalam jutaan Rupiah") == "IDR_MN"
    assert detect_unit_from_header("Dinyatakan dalam miliaran Rupiah") == "IDR_BN"
    assert detect_unit_from_header("in thousand USD") == "USD_TH"
    assert detect_unit_from_header("normal text") == "IDR"


def test_extract_tables_from_fixture() -> None:
    pdf_path = FIXTURES_DIR / "sample_bmri.pdf"
    pdf_bytes = pdf_path.read_bytes()
    pages = parse_pdf(pdf_bytes)

    tables = extract_tables(pdf_bytes, pages)
    assert len(tables) >= 1

    facts = tables_to_facts(
        tables=tables,
        sector="Banking",
        ticker="BMRI",
        fiscal_period="2024Q4",
        doc_id="00000000-0000-0000-0000-000000000001",
    )
    assert len(facts) >= 5
    concept_names = [f.concept_local for f in facts]
    assert any(
        "kredit" in c.lower() or "aset" in c.lower() or "kas" in c.lower() for c in concept_names
    )
