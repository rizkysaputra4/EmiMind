"""Unit tests for domain types and custom validators."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from services.mcp.types import CellRef, DraftSubmissionPayload, ExtractedFactItem
from services.shared.types import (
    BBox,
    FiscalPeriod,
    Ticker,
    validate_fiscal_period,
    validate_ticker,
)


class SampleModel(BaseModel):
    ticker: Ticker
    fiscal_period: FiscalPeriod
    bbox: BBox | None = None


def test_valid_ticker() -> None:
    assert validate_ticker("BMRI") == "BMRI"
    assert validate_ticker("BBCA") == "BBCA"
    assert validate_ticker("ADRO") == "ADRO"


def test_invalid_ticker() -> None:
    with pytest.raises(ValueError):
        validate_ticker("bmri")
    with pytest.raises(ValueError):
        validate_ticker("BMR")
    with pytest.raises(ValueError):
        validate_ticker("BMRI1")


def test_valid_fiscal_period() -> None:
    assert validate_fiscal_period("2024Q1") == "2024Q1"
    assert validate_fiscal_period("2024Q4") == "2024Q4"
    assert validate_fiscal_period("2023FY") == "2023FY"
    assert validate_fiscal_period("2024H1") == "2024H1"


def test_invalid_fiscal_period() -> None:
    with pytest.raises(ValueError):
        validate_fiscal_period("2024")
    with pytest.raises(ValueError):
        validate_fiscal_period("2024Q5")
    with pytest.raises(ValueError):
        validate_fiscal_period("24Q1")


def test_bbox_valid() -> None:
    box = BBox(10.0, 20.0, 100.0, 200.0)
    assert box.x0 == 10.0
    assert box.y0 == 20.0
    assert box.x1 == 100.0
    assert box.y1 == 200.0


def test_bbox_invalid() -> None:
    with pytest.raises(ValueError):
        BBox(100.0, 20.0, 10.0, 200.0)  # x0 > x1
    with pytest.raises(ValueError):
        BBox(10.0, 200.0, 100.0, 20.0)  # y0 > y1


def test_pydantic_model_validation() -> None:
    m = SampleModel(
        ticker="BBRI",
        fiscal_period="2024Q3",
        bbox=BBox(0.0, 0.0, 50.0, 50.0),
    )
    assert m.ticker == "BBRI"
    assert m.fiscal_period == "2024Q3"

    with pytest.raises(ValidationError):
        SampleModel(ticker="invalid", fiscal_period="2024Q1")


def test_extracted_fact_item_cell_ref_optional_and_roundtrip() -> None:
    # Fact with cell_ref
    fact_with_cell = ExtractedFactItem(
        concept_id="ifrs:Assets",
        value_numeric=Decimal("1234567"),
        source_page=2,
        cell_ref=CellRef(table_index=0, row=5, col=2),
    )
    assert fact_with_cell.cell_ref is not None
    assert fact_with_cell.cell_ref.table_index == 0
    assert fact_with_cell.cell_ref.row == 5
    assert fact_with_cell.cell_ref.col == 2

    # Fact without cell_ref
    fact_without_cell = ExtractedFactItem(
        concept_id="ifrs:Revenue",
        value_numeric=Decimal("500000"),
        source_page=3,
    )
    assert fact_without_cell.cell_ref is None

    # DraftSubmissionPayload roundtrip with and without cell_ref
    payload_data = {
        "doc_id": "test-doc-123",
        "ticker": "BMRI",
        "fiscal_period": "2024Q4",
        "facts": [
            {
                "concept_id": "ifrs:Assets",
                "value_numeric": "1234567",
                "source_page": 2,
                "cell_ref": {"table_index": 0, "row": 5, "col": 2},
            },
            {
                "concept_id": "ifrs:Revenue",
                "value_numeric": "500000",
                "source_page": 3,
            },
        ],
    }

    parsed = DraftSubmissionPayload.model_validate(payload_data)
    assert len(parsed.facts) == 2
    assert parsed.facts[0].cell_ref == CellRef(table_index=0, row=5, col=2)
    assert parsed.facts[1].cell_ref is None

    # Serialize back and re-validate
    dumped = parsed.model_dump(mode="json")
    re_parsed = DraftSubmissionPayload.model_validate(dumped)
    assert re_parsed == parsed

