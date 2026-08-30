"""Unit tests for domain types and custom validators."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

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
