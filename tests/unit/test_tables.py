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
from tests.fixtures.m9.build_fixtures import build_fs_small

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_parse_numeric_value() -> None:
    assert parse_numeric_value("1.530.000") == 1530000.0
    assert parse_numeric_value("(45.200)") == -45200.0
    assert parse_numeric_value("(12.345)") == -12345.0
    assert parse_numeric_value("1.234.567,89") == 1234567.89
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


def test_fs_small_p2_table_grid(tmp_path: Path) -> None:
    pdf_path = tmp_path / "fs_small.pdf"
    build_fs_small(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    pages = parse_pdf(pdf_bytes)

    tables = extract_tables(pdf_bytes, pages)
    p2_tables = [t for t in tables if t.page_num == 2]
    assert len(p2_tables) >= 1

    t = p2_tables[0]
    assert t.unit_hint == "IDR_MN"  # indicates millions

    # Find cell with "Jumlah aset"
    asset_cells = [c for c in t.cells if "Jumlah aset" in c.text]
    assert len(asset_cells) == 1
    asset_row_idx = asset_cells[0].row

    # Current year column is column 2
    cy_cells = [c for c in t.cells if c.row == asset_row_idx and c.col == 2]
    assert len(cy_cells) == 1
    assert cy_cells[0].value == 100000.0  # Ground truth total assets in millions


def test_fs_small_p8_borderless_table(tmp_path: Path) -> None:
    pdf_path = tmp_path / "fs_small.pdf"
    build_fs_small(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    pages = parse_pdf(pdf_bytes)

    tables = extract_tables(pdf_bytes, pages)
    p8_tables = [t for t in tables if t.page_num == 8]
    assert len(p8_tables) >= 1

    t = p8_tables[0]
    assert t.extraction_method in ("camelot_stream", "pdfplumber")

    bank_expected = {
        "PT Bank Mandiri (Persero) Tbk": 5000.0,
        "PT Bank Central Asia Tbk": 3000.0,
        "PT Bank Rakyat Indonesia Tbk": 2000.0,
        "Jumlah kas dan setara kas": 10000.0,
    }

    for bank_name, expected_val in bank_expected.items():
        label_cells = [c for c in t.cells if bank_name in c.text]
        assert len(label_cells) >= 1, f"Missing row for {bank_name}"
        row_idx = label_cells[0].row
        val_cells = [c for c in t.cells if c.row == row_idx and c.col == 1]
        assert len(val_cells) >= 1, f"Missing value cell for {bank_name}"
        assert val_cells[0].value == expected_val
