"""Unit tests for deterministic retrieval planning across user intents."""

from __future__ import annotations

from services.retrieval.planner import plan_retrieval
from services.retrieval.session_store import StickyState
from services.shared.types import FiscalPeriod, Intent, QueryClassification, Ticker


def test_plan_fact_lookup() -> None:
    cls = QueryClassification(
        intent=Intent.FACT_LOOKUP,
        tickers=[Ticker("BMRI")],
        periods=[FiscalPeriod("2024Q4")],
        concepts=["net_profit"],
    )
    sticky = StickyState()
    plan = plan_retrieval(cls, sticky)

    assert len(plan.l2_steps) == 1
    assert plan.l2_steps[0].ticker == "BMRI"
    assert len(plan.l3_steps) == 1
    assert len(plan.l6_steps) == 1
    assert len(plan.l4_steps) == 0


def test_plan_explanation() -> None:
    cls = QueryClassification(
        intent=Intent.EXPLANATION,
        tickers=[Ticker("BMRI")],
        periods=[FiscalPeriod("2024Q4")],
    )
    sticky = StickyState()
    plan = plan_retrieval(cls, sticky, original_query="Why did net profit grow?")

    assert len(plan.l2_steps) == 1
    assert len(plan.l3_steps) == 1
    assert len(plan.l4_steps) == 1
    assert plan.l4_steps[0].query == "Why did net profit grow?"
    assert len(plan.l6_steps) == 1


def test_plan_compare_peers() -> None:
    cls = QueryClassification(
        intent=Intent.COMPARE_PEERS,
        tickers=[Ticker("BMRI"), Ticker("BBCA")],
        periods=[FiscalPeriod("2024Q4")],
    )
    sticky = StickyState(peer_set=[Ticker("BBRI")])
    plan = plan_retrieval(cls, sticky)

    # 3 tickers: BMRI, BBCA, BBRI
    assert len(plan.l2_steps) == 3
    assert len(plan.l3_steps) == 3
