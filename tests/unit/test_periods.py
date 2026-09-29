"""Unit tests for fiscal period resolution."""

from __future__ import annotations

from datetime import date

import pytest

from services.mcp.periods import (
    period_end_for,
    resolve_fiscal_period,
    resolve_period_from_text,
)

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


FREE_TOKEN_CASES = [
    ("Pengantar Lap Keu Q1 31 Maret 2026.pdf", "2026Q1"),
    ("013-BWPT-Corsec-III-2021 LK 31 Desember 2020.pdf", "2020Q4"),
    ("001-DIR-I-2025 Laporan Juni 2025.pdf", "2025Q2"),
    ("LK Triwulan II 2025.pdf", "2025Q2"),
    ("Semester I 2024.pdf", "2024Q2"),
    ("Semester 2 2023.pdf", "2023Q4"),
    ("LK Kuartal 1 2024.pdf", "2024Q1"),
    ("FS_2024-06-30.pdf", "2024Q2"),
    ("report_20240630.pdf", "2024Q2"),
    ("LKT 2023.pdf", "2023Q4"),
    ("Laporan Tahunan 2024.pdf", "2024Q4"),
    ("FinancialStatement-2022-IV-XXXX.pdf", "2022Q4"),
    ("June 30, 2024 FS.pdf", "2024Q2"),
    ("H1 2024 results.pdf", "2024Q2"),
    ("LK Q3 2025.pdf", "2025Q3"),
    ("FS 31 Mar 2023 (Unaudited).pdf", "2023Q1"),
    ("LK Triwulan III 2024.pdf", "2024Q3"),
    ("Kuartal II 2023.pdf", "2023Q2"),
    ("LK TW-II 2025.pdf", "2025Q2"),
    ("Laporan Semester I Tahun 2024.pdf", "2024Q2"),
    ("LK 2024-09-30.pdf", "2024Q3"),
    ("FS 30.06.2024.pdf", "2024Q2"),
    ("No. 123/DIR/IV/2024 LK Juni 2024.pdf", "2024Q2"),
]


@pytest.mark.parametrize("filename,expected_fp", FREE_TOKEN_CASES)
def test_free_token_cases(filename: str, expected_fp: str) -> None:
    res = resolve_fiscal_period(filename)
    assert res is not None
    assert res.fiscal_period == expected_fp
    assert res.source == "filename_tokens"
    assert res.conflict is False


def test_roman_letter_number_does_not_become_quarter() -> None:
    # no explicit quarter: roman numerals inside letter reference numbers are ignored
    assert resolve_fiscal_period("013-BWPT-Corsec-III-2021.pdf") is None
    assert resolve_fiscal_period("Surat 045/CORSEC/III/2025.pdf") is None


def test_composite_code_never_reads_a_day_as_a_year() -> None:
    res = resolve_fiscal_period("Pengantar Lap Keu Q1 31 Maret 2026.pdf")
    assert res is not None and res.fiscal_period == "2026Q1"  # was 2031Q1
    res = resolve_fiscal_period("BMRI_2025_TW1_RDF_Pengantar Lap Keu Q1 31 Maret 2026.pdf")
    assert res is not None and res.fiscal_period == "2025Q1"
    assert res.conflict is True and res.conflicting_period == "2026Q1"


@pytest.mark.parametrize(
    "filename,prefix_fp,conflicting",
    [
        ("FOOD_2023_TW1_RDF_LK PT SFI TW 3_2022.pdf", "2023Q1", "2022Q3"),
        ("ASMI_2024_TW1_RDF_Laporan Keuangan ASMI 31 Desember 2023 (audited).pdf", "2024Q1", "2023Q4"),
        ("RIGS_2023_TW2_RDF_RIGS - Laporan Keuangan 31 Desember 2023.pdf", "2023Q2", "2023Q4"),
    ],
)
def test_prefix_disagreement_is_flagged(filename: str, prefix_fp: str, conflicting: str) -> None:
    res = resolve_fiscal_period(filename)
    assert res is not None
    assert res.source == "downloader_prefix"
    assert res.fiscal_period == prefix_fp
    assert res.conflict is True
    assert res.conflicting_period == conflicting


@pytest.mark.parametrize(
    "filename",
    [
        "BWPT_2021_TW3_RDF_013-BWPT-Corsec-III-2021.pdf",
        "AMAG_2021_AUDIT_RDF_Investor Daily 29 Maret 2022.pdf",
        "INDX_2020_TW2_RDF_Q2_FY2020_Checklist Pengungkapan Laporan Keuangan.pdf",
        "BMRI_2025_TW3_RDF_LKFS Bank Mandiri 30 Sept 2025 FINAL.pdf",
        "IATA_2020_AUDIT_RDF_039-20210531-BEI-Perubahan Liabilitas-SIGNED.pdf",
    ],
)
def test_prefix_agreement_or_letter_dates_not_flagged(filename: str) -> None:
    res = resolve_fiscal_period(filename)
    assert res is not None
    assert res.conflict is False


@pytest.mark.parametrize(
    "hint,expected",
    [("2025H1", "2025Q2"), ("2025H2", "2025Q4"), ("2025q2", "2025Q2"), (" 2024FY ", "2024Q4")],
)
def test_hint_normalization(hint: str, expected: str) -> None:
    res = resolve_fiscal_period("x.pdf", hint=hint)
    assert res is not None
    assert res.fiscal_period == expected


def test_cover_page_text_resolution() -> None:
    interim = (
        "LAPORAN KEUANGAN KONSOLIDASIAN INTERIM 30 JUNI 2025 DAN 31 DESEMBER 2024 SERTA "
        "UNTUK PERIODE ENAM BULAN YANG BERAKHIR 30 JUNI 2025 DAN 2024"
    )
    res = resolve_period_from_text(interim)
    assert res is not None
    assert res.fiscal_period == "2025Q2"
    assert res.source == "cover_page"

    annual = (
        "Consolidated financial statements as of 31 December 2025 and for the year then "
        "ended. Jakarta, 30 Maret 2026"
    )
    res = resolve_period_from_text(annual)
    assert res is not None
    assert res.fiscal_period == "2025Q4"

    assert resolve_period_from_text("Surat pengantar tanpa tanggal periode") is None
    assert resolve_period_from_text("") is None


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
