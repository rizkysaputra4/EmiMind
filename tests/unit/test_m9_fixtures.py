"""Unit tests for M9 synthetic PDF fixture builder."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pymupdf

from tests.fixtures.m9.build_fixtures import (
    GROUND_TRUTH,
    build_bilingual,
    build_fs_small,
    build_scanned,
)


def test_fs_small_pdf_generation(tmp_path: Path) -> None:
    pdf_path = build_fs_small(tmp_path / "fs_small.pdf")
    doc = pymupdf.open(str(pdf_path))

    # Assert 8 pages
    assert len(doc) == 8, f"Expected 8 pages, got {len(doc)}"

    # Assert p2 text contains "Jumlah aset" (page 2 is 0-indexed index 1)
    p2_text = doc[1].get_text()
    assert "Jumlah aset" in p2_text, "Expected 'Jumlah aset' on page 2"
    assert "(Dalam jutaan Rupiah)" in p2_text

    # Check cover
    assert "PT Contoh Tbk" in doc[0].get_text()

    # Check note continuation on p5 and p6
    p5_text = doc[4].get_text()
    p6_text = doc[5].get_text()
    assert "12. KREDIT YANG DIBERIKAN" in p5_text
    assert "12. KREDIT YANG DIBERIKAN (lanjutan)" in p6_text

    # Check borderless table on p8
    p8_text = doc[7].get_text()
    assert "13. KAS DAN SETARA KAS" in p8_text
    assert "PT Bank Mandiri (Persero) Tbk" in p8_text

    doc.close()


def test_scanned_pdf_generation(tmp_path: Path) -> None:
    pdf_path = build_scanned(tmp_path / "scanned.pdf")
    doc = pymupdf.open(str(pdf_path))

    assert len(doc) == 2, f"Expected 2 pages, got {len(doc)}"

    # Assert every page returns fewer than 50 non-whitespace chars
    for i, page in enumerate(doc):
        text = page.get_text()
        non_ws_chars = len(re.sub(r"\s+", "", text))
        assert (
            non_ws_chars < 50
        ), f"Page {i + 1} has {non_ws_chars} non-whitespace chars, expected < 50"

    doc.close()


def test_bilingual_pdf_generation(tmp_path: Path) -> None:
    pdf_path = build_bilingual(tmp_path / "bilingual.pdf")
    doc = pymupdf.open(str(pdf_path))

    assert len(doc) == 1
    p_text = doc[0].get_text()
    assert "LAPORAN POSISI KEUANGAN KONSOLIDASIAN" in p_text
    assert "CONSOLIDATED STATEMENT OF FINANCIAL POSITION" in p_text
    assert "Kas dan setara kas" in p_text
    assert "Cash and cash equivalents" in p_text

    doc.close()


def test_ground_truth_accounting_equation() -> None:
    concepts: dict[str, dict[int, float]] = GROUND_TRUTH["concepts"]

    for yr in (2025, 2024):
        assets = concepts["ifrs:Assets"][yr]
        liabilities = concepts["ifrs:Liabilities"][yr]
        equity = concepts["ifrs:Equity"][yr]

        assert (
            assets == liabilities + equity
        ), f"A = L + E failed for year {yr}: {assets} != {liabilities} + {equity}"

    # Also verify revenue - COGS = gross profit
    for yr in (2025, 2024):
        rev = concepts["ifrs:Revenue"][yr]
        cogs = concepts["ifrs:CostOfSales"][yr]
        gp = concepts["ifrs:GrossProfit"][yr]
        assert rev - cogs == gp, f"Gross profit failed for year {yr}"


def test_pytest_fixtures(
    fs_small_pdf_path: Path,
    scanned_pdf_path: Path,
    bilingual_pdf_path: Path,
    m9_ground_truth: dict[str, Any],
) -> None:
    assert fs_small_pdf_path.exists()
    assert scanned_pdf_path.exists()
    assert bilingual_pdf_path.exists()
    assert m9_ground_truth["scale"] == 1_000_000
