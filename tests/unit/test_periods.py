"""Unit tests for fiscal period resolution."""

from __future__ import annotations

from datetime import date

import pytest

from services.mcp.periods import period_end_for, resolve_fiscal_period

TABLE_CASES = [
    (
        "BMRI_2020_TW1_RDF_FinancialStatement-2020-I-BMRI.pdf",
        "2020Q1",
        date(2020, 3, 31),
        "downloader_prefix",
    ),
    (
        "BMRI_2021_TW2_RDF_PT Bank Mandiri Tbk_Ind_30 Juni_2021.pdf",
        "2021Q2",
        date(2021, 6, 30),
        "downloader_prefix",
    ),
    (
        "BMRI_2025_TW3_RDF_LKFS Bank Mandiri 30 Sept 2025 FINAL.pdf",
        "2025Q3",
        date(2025, 9, 30),
        "downloader_prefix",
    ),
    (
        "BMRI_2024_AUDIT_RDF_FinancialStatement-2024-Tahunan-BMRI.pdf",
        "2024Q4",
        date(2024, 12, 31),
        "downloader_prefix",
    ),
    (
        "LSIP_2025_ANNUAL_AAR_AnnualReport2025-LSIP-att1.pdf",
        "2025Q4",
        date(2025, 12, 31),
        "downloader_prefix",
    ),
    (
        "202603_ULTJ_Group_Q1_FR.pdf",
        "2026Q1",
        date(2026, 3, 31),
        "filename_tokens",
    ),
    (
        "LSIP_bilingual_30_Jun_2026_Released.pdf",
        "2026Q2",
        date(2026, 6, 30),
        "filename_tokens",
    ),
    (
        "Financial Statements 1H26.pdf",
        "2026Q2",
        date(2026, 6, 30),
        "filename_tokens",
    ),
    (
        "Laporan Keuangan TBP 30 Juni 2026.pdf",
        "2026Q2",
        date(2026, 6, 30),
        "filename_tokens",
    ),
    (
        "LSIP_bilingual_31 des_2025_released.pdf",
        "2025Q4",
        date(2025, 12, 31),
        "filename_tokens",
    ),
    (
        "FinancialStatement-2022-III-XXXX.pdf",
        "2022Q3",
        date(2022, 9, 30),
        "filename_tokens",
    ),
    (
        "Annual Report 2025.pdf",
        "2025Q4",
        date(2025, 12, 31),
        "filename_tokens",
    ),
]


@pytest.mark.parametrize("filename,expected_fp,expected_date,expected_source", TABLE_CASES)
def test_resolve_fiscal_period_table_cases(
    filename: str,
    expected_fp: str,
    expected_date: date,
    expected_source: str,
) -> None:
    res = resolve_fiscal_period(filename)
    assert res is not None, f"Expected resolution for {filename}, got None"
    assert res.fiscal_period == expected_fp
    assert res.period_end == expected_date
    assert res.source == expected_source


def test_resolve_unparseable_filename_returns_none() -> None:
    assert resolve_fiscal_period("random_scan.pdf") is None


def test_hint_precedence_and_normalization() -> None:
    res = resolve_fiscal_period("any_filename.pdf", hint="2023FY")
    assert res is not None
    assert res.fiscal_period == "2023Q4"
    assert res.period_end == date(2023, 12, 31)
    assert res.source == "hint"


def test_invalid_hint_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Invalid fiscal period hint"):
        resolve_fiscal_period("any_filename.pdf", hint="2023Q5")


def test_period_end_for_all_quarters() -> None:
    assert period_end_for("2025Q1") == date(2025, 3, 31)
    assert period_end_for("2025Q2") == date(2025, 6, 30)
    assert period_end_for("2025Q3") == date(2025, 9, 30)
    assert period_end_for("2025Q4") == date(2025, 12, 31)


def test_period_end_for_invalid_format() -> None:
    with pytest.raises(ValueError):
        period_end_for("invalid")
