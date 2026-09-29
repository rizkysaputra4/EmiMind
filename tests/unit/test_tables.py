"""Unit tests for table extraction and numeric parsing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from services.extraction.pdf import parse_pdf
from services.extraction.tables import (
    _camelot_cell_bbox,
    build_grid_cells,
    detect_page_unit,
    detect_unit_from_header,
    extract_page_grids,
    extract_tables,
    is_note_reference,
    parse_numeric_value,
    split_mixed_cell,
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
    # thousands are *_K everywhere (grounding.py maps IDR_K / USD_K)
    assert detect_unit_from_header("in thousand USD") == "USD_K"
    assert detect_unit_from_header("normal text") is None


def test_detect_unit_from_header_spec_cases() -> None:
    assert detect_unit_from_header("(Expressed in millions of Rupiah)") == "IDR_MN"
    assert detect_unit_from_header("(Disajikan dalam jutaan Rupiah, kecuali dinyatakan lain)") == "IDR_MN"
    assert detect_unit_from_header("(dalam miliaran Rupiah)") == "IDR_BN"
    assert detect_unit_from_header("in billions of Rupiah") == "IDR_BN"
    assert detect_unit_from_header("(Dalam Ribuan Rupiah, kecuali dinyatakan lain)") == "IDR_K"
    assert detect_unit_from_header("Expressed in thousands of Rupiah") == "IDR_K"
    assert detect_unit_from_header("(Expressed in Rupiah)") == "IDR"
    assert detect_unit_from_header("in thousands of US Dollars") == "USD_K"
    assert detect_unit_from_header("") is None
    # no substring bugs: 'th' in 'otherwise', 'mn' in 'column', 'rp' in 'corporate'
    assert detect_unit_from_header("Unless otherwise stated") is None
    assert detect_unit_from_header("see column two for the corporate segment") is None


def test_detect_page_unit_prefers_header() -> None:
    page = "PT X Tbk\n(Disajikan dalam jutaan Rupiah)\nKas 1.000\n" + "baris\n" * 30
    page +="Catatan: nilai dalam ribuan Rupiah untuk entitas anak"
    assert detect_page_unit(page) == "IDR_MN"


def test_note_reference_detection() -> None:
    assert is_note_reference("2c,2g,4") is True
    assert is_note_reference("2c,2g,62b.(vii)") is True
    assert is_note_reference("5a") is True
    assert is_note_reference("4, 12, 30") is True
    # ambiguous alone (could be a decimal): only a Catatan/Notes column makes it a note ref
    assert is_note_reference("22,27") is False
    assert is_note_reference("1.234.567") is False


def test_split_mixed_cell() -> None:
    assert split_mixed_cell("Total Liabilitas Jangka Pendek 828.016") == 828016.0
    assert split_mixed_cell("Pihak berelasi \n \n1.993.586") == 1993586.0
    assert split_mixed_cell("Total 2025") is None  # a year is not a value
    assert split_mixed_cell("1.000 2.000") is None  # two numbers, no label
    assert split_mixed_cell("Kas") is None


def test_build_grid_cells_note_column_mixed_cells_and_confidence() -> None:
    raw = [
        (0, 0, "Keterangan", [10.0, 10.0, 100.0, 20.0]),
        (0, 1, "Catatan/Notes", [110.0, 10.0, 150.0, 20.0]),
        (0, 2, "2025", [160.0, 10.0, 220.0, 20.0]),
        (1, 0, "Kas dan setara kas", [10.0, 30.0, 100.0, 40.0]),
        (1, 1, "22,27", [110.0, 30.0, 150.0, 40.0]),
        (1, 2, "1.234.567", [160.0, 30.0, 220.0, 40.0]),
        (2, 0, "Piutang usaha", [10.0, 50.0, 100.0, 60.0]),
        (2, 1, "5", [110.0, 50.0, 150.0, 60.0]),
        (2, 2, "45.200", None),
        (3, 0, "Total Liabilitas Jangka Pendek 828.016", [10.0, 70.0, 220.0, 80.0]),
    ]
    cells = {(c.row, c.col): c for c in build_grid_cells(raw, table_confidence=0.85)}
    assert cells[(1, 1)].value is None and cells[(1, 1)].note_ref is True
    assert cells[(2, 1)].value is None and cells[(2, 1)].note_ref is True
    assert cells[(0, 2)].value is None  # header year
    assert cells[(1, 2)].value == 1234567.0
    assert cells[(2, 2)].bbox is None and cells[(2, 2)].value == 45200.0  # no synthetic bbox
    mixed = cells[(3, 0)]
    assert mixed.value == 828016.0 and mixed.value_from_mixed_cell is True
    assert all(c.confidence <= 0.85 for c in cells.values())
    assert mixed.confidence < 0.85


class _FakeCamelotCell:
    def __init__(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.right = self.bottom = True


def test_camelot_cell_bbox_converts_to_top_left_origin() -> None:
    table = SimpleNamespace(flavor="stream", cells=[[_FakeCamelotCell(50, 700, 150, 720)]])
    # PDF points, bottom-left origin y in [700, 720] on an 842pt page -> top-left [122, 142]
    assert _camelot_cell_bbox(table, 0, 0, 842.0) == [50.0, 122.0, 150.0, 142.0]
    assert _camelot_cell_bbox(table, 5, 5, 842.0) is None


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


def test_fs_small_grids_have_real_bboxes(tmp_path: Path) -> None:
    import pymupdf

    pdf_path = tmp_path / "fs_small.pdf"
    build_fs_small(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    grids = extract_page_grids(pdf_bytes, parse_pdf(pdf_bytes))
    assert grids
    doc = pymupdf.open(str(pdf_path))
    try:
        found = 0
        for g in grids:
            assert all(c.confidence <= g.confidence for c in g.cells)
            page = doc[g.page_index - 1]
            for c in g.cells:
                assert c.bbox is None or not (c.bbox[0] == 0 and c.bbox[2] == 500)
                if c.value is None or c.bbox is None or len(c.text.strip()) < 5:
                    continue
                hits = page.search_for(c.text.split()[-1])
                x0, y0, x1, y1 = c.bbox
                if hits:
                    found += 1
                    assert any(
                        h.x0 >= x0 - 3 and h.x1 <= x1 + 3 and h.y0 >= y0 - 3 and h.y1 <= y1 + 3
                        for h in hits
                    ), (c.text, c.bbox)
        assert found >= 5
    finally:
        doc.close()
