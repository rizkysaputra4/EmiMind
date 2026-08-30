"""Unit tests for regex and fallback guidance extraction."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.kg.guidance_miner import (
    mine_guidance,
    mine_guidance_regex,
)
from services.shared.types import FiscalPeriod


def test_mine_guidance_loan_growth() -> None:
    text = "We target loan growth of 10-12% for 2025 to support business expansion."
    payloads = mine_guidance_regex(text, source_period="2024Q4")
    assert len(payloads) == 1
    p = payloads[0]
    assert p.metric == "idx:LoansAndAdvances"
    assert p.low == Decimal("0.1")
    assert p.high == Decimal("0.12")
    assert p.period_target == FiscalPeriod("2025FY")
    assert p.qualifier == "range"


def test_mine_guidance_nim_and_npl() -> None:
    text = "Manajemen menargetkan NIM sebesar 5.0 - 5.3% dan NPL di bawah 2.0% pada 2025."
    payloads = mine_guidance_regex(text, source_period="2024Q4")
    assert len(payloads) == 2

    nim = next(p for p in payloads if p.metric == "bank.nim")
    assert nim.low == Decimal("0.05")
    assert nim.high == Decimal("0.053")
    assert nim.period_target == FiscalPeriod("2025FY")

    npl = next(p for p in payloads if p.metric == "bank.npl")
    assert npl.high == Decimal("0.02")
    assert npl.qualifier == "at_most"


def test_mine_guidance_casa_floor() -> None:
    text = "Bank Mandiri maintains CASA ratio above 70% for 2025."
    payloads = mine_guidance_regex(text, source_period="2024Q4")
    assert len(payloads) == 1
    p = payloads[0]
    assert p.metric == "bank.casa"
    assert p.low == Decimal("0.7")
    assert p.qualifier == "at_least"


def test_mine_guidance_coal_production() -> None:
    text = "PT Bukit Asam menargetkan produksi batubara 60 - 65 juta ton pada tahun 2025."
    payloads = mine_guidance_regex(text, source_period="2024Q4")
    assert len(payloads) == 1
    p = payloads[0]
    assert p.metric == "mining.production"
    assert p.low == Decimal("60000000")
    assert p.high == Decimal("65000000")
    assert p.unit == "TONS"


@pytest.mark.asyncio
async def test_mine_guidance_unified() -> None:
    text = "Target Cost of Credit (CoC) di kisaran 1.0 - 1.2% for 2025."
    payloads = await mine_guidance(text, source_period="2024Q4")
    assert len(payloads) == 1
    assert payloads[0].metric == "bank.coc"
