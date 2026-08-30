"""Generates realistic synthetic fixtures for testing extraction and eval."""

from __future__ import annotations

from pathlib import Path

import pymupdf

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def create_sample_pdf() -> Path:
    """Generates sample_bmri.pdf containing balance sheet, income statement, and MD&A."""
    pdf_path = FIXTURES_DIR / "sample_bmri.pdf"

    doc = pymupdf.open()

    # Page 1: MD&A / Management Discussion & Analysis
    page1 = doc.new_page(width=595, height=842)
    p1_text = """PT BANK MANDIRI (PERSERO) TBK
LAPORAN KEUANGAN KONSOLIDASIAN
UNTUK TAHUN YANG BERAKHIR PADA TANGGAL 31 DESEMBER 2024

DISKUSI DAN ANALISIS MANAJEMEN (MD&A)
Tinjauan Kinerja Keuangan Tahun 2024

Sepanjang tahun 2024, Bank Mandiri mencatatkan kinerja keuangan yang solid di tengah dinamika perekonomian global dan domestik. Laba bersih konsolidasian perseroan tumbuh positif didorong oleh pertumbuhan kredit yang berkualitas dan perbaikan efisiensi operasional.

Pertumbuhan pendapatan bunga bersih tercatat kuat seiring dengan ekspansi portofolio kredit pada segmen korporasi dan komersial. Rasio margin bunga bersih (NIM) terjaga pada level yang sehat melalui optimalisasi dana murah (CASA).

FAKTOR RISIKO
Perseroan secara konsisten menerapkan kerangka manajemen risiko terintegrasi untuk memitigasi risiko kredit, risiko pasar, risiko likuiditas, dan risiko operasional. Kualitas aset terus membaik tercermin dari penurunan rasio Non-Performing Loan (NPL).
"""
    page1.insert_text((50, 60), p1_text, fontsize=10)

    # Page 2: Laporan Posisi Keuangan (Balance Sheet) Table
    page2 = doc.new_page(width=595, height=842)
    p2_header = """PT BANK MANDIRI (PERSERO) TBK
LAPORAN POSISI KEUANGAN KONSOLIDASIAN
Per 31 Desember 2024
(Dinyatakan dalam miliaran Rupiah, kecuali dinyatakan lain)
"""
    page2.insert_text((50, 50), p2_header, fontsize=10)

    # Draw table text
    table_lines = [
        ("ASET", "31 Des 2024", "31 Des 2023"),
        ("Kas dan setara kas", "55.420", "48.110"),
        ("Giro pada Bank Indonesia", "120.300", "110.250"),
        ("Kredit yang diberikan", "1.530.000", "1.398.000"),
        ("Cadangan kerugian penurunan nilai", "(45.200)", "(42.100)"),
        ("Total Aset", "2.174.200", "1.980.500"),
        ("", "", ""),
        ("LIABILITAS DAN EKUITAS", "", ""),
        ("Simpanan nasabah", "1.650.400", "1.520.100"),
        ("Giro", "620.100", "580.400"),
        ("Tabungan", "610.200", "560.300"),
        ("Deposito berjangka", "420.100", "379.400"),
        ("Total Liabilitas", "1.890.200", "1.730.000"),
        ("Total Ekuitas", "284.000", "250.500"),
    ]

    y = 120
    for row in table_lines:
        label, val1, val2 = row
        page2.insert_text((50, y), label, fontsize=9)
        if val1:
            page2.insert_text((350, y), val1, fontsize=9)
        if val2:
            page2.insert_text((450, y), val2, fontsize=9)
        y += 18

    # Page 3: Laporan Laba Rugi (Income Statement) Table
    page3 = doc.new_page(width=595, height=842)
    p3_header = """PT BANK MANDIRI (PERSERO) TBK
LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF LAIN
Untuk Tahun yang Berakhir pada Tanggal 31 Desember 2024
(Dinyatakan dalam miliaran Rupiah, kecuali dinyatakan lain)
"""
    page3.insert_text((50, 50), p3_header, fontsize=10)

    is_lines = [
        ("PENDAPATAN DAN BEBAN OPERASIONAL", "2024", "2023"),
        ("Pendapatan bunga", "110.500", "98.200"),
        ("Beban bunga", "(38.200)", "(32.400)"),
        ("Pendapatan bunga bersih", "72.300", "65.800"),
        ("Pendapatan operasional lainnya", "28.400", "24.100"),
        ("Beban operasional lainnya", "(32.100)", "(29.500)"),
        ("Laba sebelum beban pajak", "68.600", "60.400"),
        ("Beban pajak penghasilan", "(13.500)", "(12.100)"),
        ("Laba bersih tahun berjalan", "55.100", "48.300"),
        ("Laba diatribusikan ke pemilik entitas induk", "55.100", "48.300"),
    ]

    y = 120
    for row in is_lines:
        label, val1, val2 = row
        page3.insert_text((50, y), label, fontsize=9)
        if val1:
            page3.insert_text((350, y), val1, fontsize=9)
        if val2:
            page3.insert_text((450, y), val2, fontsize=9)
        y += 18

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def create_sample_xbrl() -> Path:
    """Generates sample_bmri.xbrl.xml instance document."""
    xbrl_path = FIXTURES_DIR / "sample_bmri.xbrl.xml"
    content = """<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl
  xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:idx-cor="http://www.idx.co.id/xbrl/idx-cor"
  xmlns:iso4217="http://www.xbrl.org/2003/iso4217">

  <xbrli:context id="CurrentYearDuration">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.idx.co.id/ticker">BMRI</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2024-01-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:period>
  </xbrli:context>

  <xbrli:context id="CurrentYearInstant">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.idx.co.id/ticker">BMRI</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:instant>2024-12-31</xbrli:instant>
    </xbrli:period>
  </xbrli:context>

  <xbrli:unit id="IDR">
    <xbrli:measure>iso4217:IDR</xbrli:measure>
  </xbrli:unit>

  <!-- Income Statement Facts -->
  <idx-cor:NetInterestIncome contextRef="CurrentYearDuration" unitRef="IDR">72300000000000</idx-cor:NetInterestIncome>
  <idx-cor:InterestIncome contextRef="CurrentYearDuration" unitRef="IDR">110500000000000</idx-cor:InterestIncome>
  <idx-cor:InterestExpense contextRef="CurrentYearDuration" unitRef="IDR">38200000000000</idx-cor:InterestExpense>
  <idx-cor:ProfitLoss contextRef="CurrentYearDuration" unitRef="IDR">55100000000000</idx-cor:ProfitLoss>
  <idx-cor:ProfitLossAttributableToOwnersOfParent contextRef="CurrentYearDuration" unitRef="IDR">55100000000000</idx-cor:ProfitLossAttributableToOwnersOfParent>

  <!-- Balance Sheet Facts -->
  <idx-cor:Assets contextRef="CurrentYearInstant" unitRef="IDR">2174200000000000</idx-cor:Assets>
  <idx-cor:Liabilities contextRef="CurrentYearInstant" unitRef="IDR">1890200000000000</idx-cor:Liabilities>
  <idx-cor:Equity contextRef="CurrentYearInstant" unitRef="IDR">284000000000000</idx-cor:Equity>
  <idx-cor:LoansAndAdvances contextRef="CurrentYearInstant" unitRef="IDR">1530000000000000</idx-cor:LoansAndAdvances>
  <idx-cor:CustomerDeposits contextRef="CurrentYearInstant" unitRef="IDR">1650400000000000</idx-cor:CustomerDeposits>
</xbrli:xbrl>
"""
    xbrl_path.write_text(content, encoding="utf-8")
    return xbrl_path


if __name__ == "__main__":
    p_pdf = create_sample_pdf()
    p_xbrl = create_sample_xbrl()
    print(f"Generated fixtures: {p_pdf.name}, {p_xbrl.name}")
