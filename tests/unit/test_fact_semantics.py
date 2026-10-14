"""Concept <-> printed label checks (services.mcp.fact_semantics)."""

from __future__ import annotations

import pytest

from services.mcp.fact_semantics import check_concept_label
from services.mcp.types import ConceptDefinition

NII = ConceptDefinition(
    metric_id="idx:NetInterestIncome",
    name_id="Pendapatan Bunga Bersih",
    name_en="Net Interest Income",
    synonyms_id=["Pendapatan Bunga - Neto", "Pendapatan Bunga dan Syariah - Neto"],
    synonyms_en=["Net Interest Income", "Net Interest and Sharia Income"],
    flow_stock_type="FLOW_PERIOD",
)
PROFIT = ConceptDefinition(
    metric_id="ifrs:ProfitLoss",
    name_id="Laba Bersih Tahun Berjalan",
    name_en="Net Profit for the Year",
    flow_stock_type="FLOW_PERIOD",
)


@pytest.mark.parametrize(
    "label",
    ["PENDAPATAN BUNGA DAN SYARIAH - NETO", "PENDAPATAN BUNGA - NETO", "NET INTEREST AND SHARIA INCOME"],
)
def test_net_interest_income_accepts_printed_bmri_labels(label: str) -> None:
    assert check_concept_label(label, NII).ok


@pytest.mark.parametrize("label", ["Pendapatan bunga", "Pendapatan bunga dan syariah", "Beban bunga"])
def test_net_interest_income_rejects_gross_interest_lines(label: str) -> None:
    assert not check_concept_label(label, NII).ok


def test_net_word_stays_optional_for_other_concepts() -> None:
    assert check_concept_label("Laba tahun berjalan", PROFIT).ok


PPE = ConceptDefinition(
    metric_id="ifrs:PropertyPlantAndEquipment",
    name_id="Aset Tetap",
    name_en="Property, Plant and Equipment",
    flow_stock_type="STOCK_POINT_IN_TIME",
)
CAPEX = ConceptDefinition(
    metric_id="idx:Capex",
    name_id="Belanja Modal / Perolehan Aset Tetap",
    name_en="Capital Expenditures (Capex)",
    flow_stock_type="FLOW_PERIOD",
)


@pytest.mark.parametrize(
    "label",
    [
        "Aset tetap - setelah dikurangi akumulasi penyusutan",
        "Property, plant and equipment - net of accumulated depreciation",
        "Aset tetap - setelah dikurangi akumulasi penyusutan dan cadangan penurunan nilai",
    ],
)
def test_ppe_accepts_net_of_depreciation_caption(label: str) -> None:
    assert check_concept_label(label, PPE).ok


def test_ppe_still_rejects_construction_in_progress() -> None:
    assert not check_concept_label("Aset tetap dalam penyelesaian", PPE).ok


def test_capex_accepts_fixed_assets_and_bearer_plants() -> None:
    assert check_concept_label("Perolehan aset tetap dan tanaman produktif", CAPEX).ok


def test_capex_still_rejects_intangible_assets() -> None:
    assert not check_concept_label("Perolehan aset takberwujud", CAPEX).ok


LTB = ConceptDefinition(
    metric_id="ifrs:LongTermBorrowings",
    name_id="Utang Bank Jangka Panjang",
    name_en="Long-Term Borrowings",
    synonyms_id=["Utang Bank Jangka Panjang", "Pinjaman Jangka Panjang", "Obligasi"],
    synonyms_en=["Long-term Borrowings", "Long-term Debt", "Non-current Borrowings"],
    flow_stock_type="STOCK_POINT_IN_TIME",
)


@pytest.mark.parametrize(
    "label",
    [
        "Liabilitas jangka panjang setelah bagian lancar - Pinjaman bank",
        "Liabilitas jangka panjang setelah dikurangi bagian yang jatuh tempo dalam satu tahun - Utang bank",
        "Long-term liabilities net of current portion - Bank borrowings",
        "Pinjaman bank - Bagian jangka panjang",
        "Bank borrowings - Non-current portion",
    ],
)
def test_long_term_borrowings_accepts_section_and_portion_captions(label: str) -> None:
    assert check_concept_label(label, LTB).ok, label


@pytest.mark.parametrize(
    "label",
    [
        "Pinjaman bank",  # no term: ambiguous
        "Pinjaman jangka panjang - Bagian lancar",  # the current portion is a different figure
        "Liabilitas jangka pendek - Pinjaman bank",
        "Liabilitas jangka panjang - Liabilitas sewa",
    ],
)
def test_long_term_borrowings_rejects_other_lines(label: str) -> None:
    assert not check_concept_label(label, LTB).ok, label
