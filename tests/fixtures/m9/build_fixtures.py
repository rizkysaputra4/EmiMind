"""Synthetic PDF fixture builder for M9 tests.

Generates deterministic synthetic PDFs using PyMuPDF:
1. fs_small.pdf (8 pages): core financial statements, granular notes, MD&A, borderless cash table
2. scanned.pdf (2 pages): pure raster images with no extractable text layer
3. bilingual.pdf (1 page): Indonesian and English columns side-by-side
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf
import pytest

GROUND_TRUTH: dict[str, Any] = {
    "modules": {
        "COVER": 1,
        "BALANCE_SHEET": 2,
        "INCOME_STATEMENT": 3,
        "CASH_FLOW": 4,
        "BANK_LOANS_NPL": [5, 6],
        "MDA": 7,
        "CASH_BANKS": 8,
    },
    "scale": 1_000_000,
    "unit": "IDR_MN",
    "concepts": {
        "ifrs:Assets": {2025: 100000.0, 2024: 90000.0},
        "ifrs:Liabilities": {2025: 70000.0, 2024: 65000.0},
        "ifrs:Equity": {2025: 30000.0, 2024: 25000.0},
        "ifrs:Revenue": {2025: 20000.0, 2024: 18000.0},
        "ifrs:CostOfSales": {2025: 12000.0, 2024: 11000.0},
        "ifrs:GrossProfit": {2025: 8000.0, 2024: 7000.0},
        "ifrs:OperatingProfit": {2025: 5000.0, 2024: 4500.0},
        "ifrs:ProfitLoss": {2025: 4000.0, 2024: 3600.0},
        "ifrs:CashFlowsFromOperatingActivities": {2025: 6000.0, 2024: 5000.0},
        "ifrs:CashFlowsFromInvestingActivities": {2025: -2000.0, 2024: -1500.0},
        "ifrs:CashFlowsFromFinancingActivities": {2025: -1000.0, 2024: -1000.0},
        "ifrs:NetCashFlow": {2025: 3000.0, 2024: 2500.0},
        "idx:LoansGross": {2025: 80000.0},
        "ifrs:CashAndCashEquivalents": {2025: 10000.0, 2024: 8000.0},
    },
    "loan_segments": {
        "Korporasi": 45500.0,
        "Komersial": 17200.0,
        "Retail": 11000.0,
        "UMKM": 6300.0,
    },
    "loan_collectibility": {
        "Lancar": 70000.0,
        "Dalam Perhatian Khusus": 5000.0,
        "Kurang Lancar": 2000.0,
        "Diragukan": 1000.0,
        "Macet": 2000.0,
    },
    "cash_by_bank": {
        "PT Bank Mandiri (Persero) Tbk": {2025: 5000.0, 2024: 4000.0},
        "PT Bank Central Asia Tbk": {2025: 3000.0, 2024: 2500.0},
        "PT Bank Rakyat Indonesia Tbk": {2025: 2000.0, 2024: 1500.0},
    },
}


def _draw_table_grid(
    page: pymupdf.Page,
    cols: list[float],
    rows: list[float],
) -> None:
    """Draws grid lines for a ruled table."""
    for y in rows:
        page.draw_line(pymupdf.Point(cols[0], y), pymupdf.Point(cols[-1], y))
    for x in cols:
        page.draw_line(pymupdf.Point(x, rows[0]), pymupdf.Point(x, rows[-1]))


def _add_cover_page(doc: pymupdf.Document) -> None:
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(
        (50, 150),
        "PT Contoh Tbk — Laporan Keuangan 31 Desember 2025\n\n"
        "LAPORAN KEUANGAN TAHUNAN\n"
        "UNTUK TAHUN YANG BERAKHIR PADA TANGGAL 31 DESEMBER 2025\n"
        "DAN LAPORAN AUDITOR INDEPENDEN",
        fontsize=14,
    )


def _add_balance_sheet_page(doc: pymupdf.Document) -> None:
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(
        (50, 40),
        "PT Contoh Tbk\n"
        "LAPORAN POSISI KEUANGAN KONSOLIDASIAN\n"
        "Per 31 Desember 2025 dan 2024\n"
        "(Dalam jutaan Rupiah)",
        fontsize=10,
    )
    bs_cols = [50.0, 270.0, 330.0, 430.0, 530.0]
    bs_row_y = [110.0 + i * 22.0 for i in range(11)]
    _draw_table_grid(p2, bs_cols, bs_row_y)

    bs_cells = [
        ("Keterangan", "Catatan", "31 Des 2025", "31 Des 2024"),
        ("Kas dan setara kas", "13", "10.000", "8.000"),
        ("Kredit yang diberikan", "12", "80.000", "72.000"),
        ("Aset lainnya", "", "10.000", "10.000"),
        ("Jumlah aset", "", "100.000", "90.000"),
        ("Liabilitas segera", "", "20.000", "20.000"),
        ("Simpanan nasabah", "", "50.000", "45.000"),
        ("Jumlah liabilitas", "", "70.000", "65.000"),
        ("Modal saham", "", "20.000", "20.000"),
        ("Saldo laba", "", "10.000", "5.000"),
    ]
    for idx, (lbl, cat, v25, v24) in enumerate(bs_cells):
        y = bs_row_y[idx] + 16.0
        p2.insert_text((55, y), lbl, fontsize=9)
        p2.insert_text((275, y), cat, fontsize=9)
        p2.insert_text((335, y), v25, fontsize=9)
        p2.insert_text((435, y), v24, fontsize=9)

    y_eq = bs_row_y[10] + 16.0
    p2.insert_text((55, y_eq), "Jumlah ekuitas", fontsize=9)
    p2.insert_text((335, y_eq), "30.000", fontsize=9)
    p2.insert_text((435, y_eq), "25.000", fontsize=9)


def _add_income_statement_page(doc: pymupdf.Document) -> None:
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text(
        (50, 40),
        "PT Contoh Tbk\n"
        "LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF LAIN\n"
        "Untuk Tahun yang Berakhir pada Tanggal 31 Desember 2025\n"
        "(Dalam jutaan Rupiah)",
        fontsize=10,
    )
    is_cols = [50.0, 270.0, 330.0, 430.0, 530.0]
    is_row_y = [110.0 + i * 22.0 for i in range(8)]
    _draw_table_grid(p3, is_cols, is_row_y)

    is_cells = [
        ("Keterangan", "Catatan", "31 Des 2025", "31 Des 2024"),
        ("Pendapatan usaha", "14", "20.000", "18.000"),
        ("Beban pokok pendapatan", "15", "12.000", "11.000"),
        ("Laba kotor", "", "8.000", "7.000"),
        ("Beban usaha", "", "3.000", "2.500"),
        ("Laba usaha", "", "5.000", "4.500"),
        ("Laba tahun berjalan", "", "4.000", "3.600"),
    ]
    for idx, (lbl, cat, v25, v24) in enumerate(is_cells):
        y = is_row_y[idx] + 16.0
        p3.insert_text((55, y), lbl, fontsize=9)
        p3.insert_text((275, y), cat, fontsize=9)
        p3.insert_text((335, y), v25, fontsize=9)
        p3.insert_text((435, y), v24, fontsize=9)


def _add_cash_flow_page(doc: pymupdf.Document) -> None:
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text(
        (50, 40),
        "PT Contoh Tbk\n"
        "LAPORAN ARUS KAS KONSOLIDASIAN\n"
        "Untuk Tahun yang Berakhir pada Tanggal 31 Desember 2025\n"
        "(Dalam jutaan Rupiah)",
        fontsize=10,
    )
    cf_cols = [50.0, 270.0, 330.0, 430.0, 530.0]
    cf_row_y = [110.0 + i * 22.0 for i in range(6)]
    _draw_table_grid(p4, cf_cols, cf_row_y)

    cf_cells = [
        ("Keterangan", "Catatan", "31 Des 2025", "31 Des 2024"),
        ("Arus kas dari aktivitas operasi", "", "6.000", "5.000"),
        ("Arus kas dari aktivitas investasi", "", "(2.000)", "(1.500)"),
        ("Arus kas dari aktivitas pendanaan", "", "(1.000)", "(1.000)"),
        ("Kenaikan bersih kas dan setara kas", "", "3.000", "2.500"),
    ]
    for idx, (lbl, cat, v25, v24) in enumerate(cf_cells):
        y = cf_row_y[idx] + 16.0
        p4.insert_text((55, y), lbl, fontsize=9)
        p4.insert_text((275, y), cat, fontsize=9)
        p4.insert_text((335, y), v25, fontsize=9)
        p4.insert_text((435, y), v24, fontsize=9)


def _add_notes_page(doc: pymupdf.Document) -> None:
    p5 = doc.new_page(width=595, height=842)
    p5.insert_text(
        (50, 40),
        "CATATAN ATAS LAPORAN KEUANGAN KONSOLIDASIAN\n"
        "12. KREDIT YANG DIBERIKAN\n"
        "Rincian kredit yang diberikan berdasarkan kolektibilitas dan segmen usaha adalah sebagai berikut:\n"
        "(Dalam jutaan Rupiah)",
        fontsize=10,
    )
    n12_cols = [50.0, 190.0, 260.0, 330.0, 400.0, 470.0, 540.0]
    n12_p5_rows = [120.0 + i * 22.0 for i in range(5)]
    _draw_table_grid(p5, n12_cols, n12_p5_rows)

    p5_matrix = [
        ("Kolektibilitas", "Korporasi", "Komersial", "Retail", "UMKM", "Jumlah"),
        ("Lancar", "40.000", "15.000", "10.000", "5.000", "70.000"),
        ("Dalam Perhatian Khusus", "3.000", "1.000", "500", "500", "5.000"),
        ("Kurang Lancar", "1.000", "500", "200", "300", "2.000"),
    ]
    for idx, row_vals in enumerate(p5_matrix):
        y = n12_p5_rows[idx] + 16.0
        for c_idx, val in enumerate(row_vals):
            p5.insert_text((n12_cols[c_idx] + 4, y), val, fontsize=8)

    p6 = doc.new_page(width=595, height=842)
    p6.insert_text(
        (50, 40),
        "CATATAN ATAS LAPORAN KEUANGAN KONSOLIDASIAN\n"
        "12. KREDIT YANG DIBERIKAN (lanjutan)\n"
        "(Dalam jutaan Rupiah)",
        fontsize=10,
    )
    n12_p6_rows = [100.0 + i * 22.0 for i in range(5)]
    _draw_table_grid(p6, n12_cols, n12_p6_rows)

    p6_matrix = [
        ("Kolektibilitas", "Korporasi", "Komersial", "Retail", "UMKM", "Jumlah"),
        ("Diragukan", "500", "200", "100", "200", "1.000"),
        ("Macet", "1.000", "500", "200", "300", "2.000"),
        ("Jumlah kredit", "45.500", "17.200", "11.000", "6.300", "80.000"),
    ]
    for idx, row_vals in enumerate(p6_matrix):
        y = n12_p6_rows[idx] + 16.0
        for c_idx, val in enumerate(row_vals):
            p6.insert_text((n12_cols[c_idx] + 4, y), val, fontsize=8)


def _add_mda_and_cash_pages(doc: pymupdf.Document) -> None:
    p7 = doc.new_page(width=595, height=842)
    p7.insert_text(
        (50, 60),
        "PEMBAHASAN DAN ANALISIS MANAJEMEN\n\n"
        "Tinjauan Kinerja Keuangan dan Operasional\n\n"
        "Pada tahun 2025, PT Contoh Tbk mencatatkan peningkatan pendapatan sebesar 11,1% menjadi "
        "Rp20.000 miliar dibandingkan tahun 2024 sebesar Rp18.000 miliar. Pertumbuhan ini didorong oleh "
        "ekspansi kredit korporasi dan efisiensi biaya operasional. Laba bersih mencapai Rp4.000 miliar "
        "dengan rasio NPL gross terjaga pada level 2,5%.\n\n"
        "Total kredit yang diberikan mencapai Rp80.000 miliar, tumbuh dari Rp72.000 miliar pada tahun 2024. "
        "Segmen korporasi mendominasi dengan kontribusi Rp45.500 miliar, diikuti oleh segmen komersial "
        "sebesar Rp17.200 miliar dan retail sebesar Rp11.000 miliar.",
        fontsize=10,
    )

    p8 = doc.new_page(width=595, height=842)
    p8.insert_text(
        (50, 50),
        "13. KAS DAN SETARA KAS\n"
        "(Dalam jutaan Rupiah)\n\n"
        "Rincian kas dan setara kas berdasarkan penempatan pada bank adalah sebagai berikut:\n",
        fontsize=10,
    )
    b_rows = [
        ("Bank", "31 Des 2025", "31 Des 2024"),
        ("PT Bank Mandiri (Persero) Tbk", "5.000", "4.000"),
        ("PT Bank Central Asia Tbk", "3.000", "2.500"),
        ("PT Bank Rakyat Indonesia Tbk", "2.000", "1.500"),
        ("Jumlah kas dan setara kas", "10.000", "8.000"),
    ]
    cur_y = 130.0
    for bank_lbl, v25, v24 in b_rows:
        p8.insert_text((50, cur_y), bank_lbl, fontsize=9)
        p8.insert_text((350, cur_y), v25, fontsize=9)
        p8.insert_text((450, cur_y), v24, fontsize=9)
        cur_y += 22.0


def build_fs_small(output_path: Path) -> Path:
    """Builds 8-page fs_small.pdf with ruled tables, continuous notes, MD&A, and borderless tables."""
    doc = pymupdf.open()
    _add_cover_page(doc)
    _add_balance_sheet_page(doc)
    _add_income_statement_page(doc)
    _add_cash_flow_page(doc)
    _add_notes_page(doc)
    _add_mda_and_cash_pages(doc)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()
    return output_path


def build_scanned(output_path: Path) -> Path:
    """Builds 2-page scanned.pdf containing only raster image representations of text."""
    tmp_doc = pymupdf.open()

    p1 = tmp_doc.new_page(width=595, height=842)
    p1.insert_text(
        (50, 100),
        "PT CONTOH TBK — DOKUMEN PINDAIAN (SCANNED)\n\n"
        "Halaman 1: Dokumen ini tidak memiliki text layer dan sepenuhnya berupa gambar raster.\n"
        "Ekstraksi teks dari dokumen ini harus menggunakan OCR fallback (Tesseract).",
        fontsize=12,
    )

    p2 = tmp_doc.new_page(width=595, height=842)
    p2.insert_text(
        (50, 100),
        "LAPORAN KEUANGAN HASIL SCAN TAHUN 2025\n\n"
        "Halaman 2: Laporan Posisi Keuangan Pindaian.\n"
        "Jumlah aset tercatat sebesar Rp100.000.000.000 dan liabilitas Rp70.000.000.000.",
        fontsize=12,
    )

    pix1 = tmp_doc[0].get_pixmap(dpi=150)
    pix2 = tmp_doc[1].get_pixmap(dpi=150)
    tmp_doc.close()

    final_doc = pymupdf.open()
    fp1 = final_doc.new_page(width=595, height=842)
    fp1.insert_image(fp1.rect, pixmap=pix1)

    fp2 = final_doc.new_page(width=595, height=842)
    fp2.insert_image(fp2.rect, pixmap=pix2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_doc.save(str(output_path))
    final_doc.close()
    return output_path


def build_bilingual(output_path: Path) -> Path:
    """Builds 1-page bilingual.pdf with Indonesian left column and English right column."""
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)

    p.insert_text((50, 40), "PT CONTOH TBK", fontsize=11)
    p.insert_text((50, 55), "LAPORAN POSISI KEUANGAN KONSOLIDASIAN", fontsize=10)
    p.insert_text((300, 55), "CONSOLIDATED STATEMENT OF FINANCIAL POSITION", fontsize=10)

    id_lines = [
        "Aset Lancar",
        "Kas dan setara kas",
        "Piutang usaha",
        "Persediaan",
        "Jumlah aset lancar",
        "Aset Tidak Lancar",
        "Aset tetap",
        "Jumlah aset",
        "Liabilitas dan Ekuitas",
        "Jumlah liabilitas",
        "Jumlah ekuitas",
    ]

    en_lines = [
        "Current Assets",
        "Cash and cash equivalents",
        "Trade receivables",
        "Inventories",
        "Total current assets",
        "Non-current Assets",
        "Fixed assets",
        "Total assets",
        "Liabilities and Equity",
        "Total liabilities",
        "Total equity",
    ]

    y = 90.0
    for id_text, en_text in zip(id_lines, en_lines, strict=True):
        p.insert_text((50, y), id_text, fontsize=9)
        p.insert_text((300, y), en_text, fontsize=9)
        y += 20.0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()
    return output_path


@pytest.fixture(scope="session")
def m9_fixtures(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Pytest session-scoped fixture creating all synthetic test PDFs."""
    base_dir = tmp_path_factory.mktemp("m9_fixtures")
    fs_path = build_fs_small(base_dir / "fs_small.pdf")
    scanned_path = build_scanned(base_dir / "scanned.pdf")
    bilingual_path = build_bilingual(base_dir / "bilingual.pdf")

    return {
        "fs_small": fs_path,
        "scanned": scanned_path,
        "bilingual": bilingual_path,
    }


@pytest.fixture(scope="session")
def fs_small_pdf_path(m9_fixtures: dict[str, Path]) -> Path:
    return m9_fixtures["fs_small"]


@pytest.fixture(scope="session")
def scanned_pdf_path(m9_fixtures: dict[str, Path]) -> Path:
    return m9_fixtures["scanned"]


@pytest.fixture(scope="session")
def bilingual_pdf_path(m9_fixtures: dict[str, Path]) -> Path:
    return m9_fixtures["bilingual"]


@pytest.fixture(scope="session")
def m9_ground_truth() -> dict[str, Any]:
    return GROUND_TRUTH
