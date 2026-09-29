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
