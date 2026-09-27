"""Deterministic retrieval planner translating query classifications into structured retrieval steps."""

from __future__ import annotations

from pydantic import BaseModel, Field

from services.derive.recipes.generic import offset_fiscal_period
from services.retrieval.narrative_retriever import NarrativeFilters
from services.retrieval.session_store import StickyState
from services.shared.types import FiscalPeriod, Intent, QueryClassification, Ticker


class L2Step(BaseModel):
    """L2 Fact retrieval step."""

    ticker: Ticker
    periods: list[FiscalPeriod]
    concepts: list[str] = Field(default_factory=list)


class L3Step(BaseModel):
    """L3 Derived metrics retrieval step."""

    ticker: Ticker
    periods: list[FiscalPeriod]
    metric_prefixes: list[str] = Field(default_factory=list)


class L4Step(BaseModel):
    """L4 Hybrid narrative retrieval step."""

    query: str
    filters: NarrativeFilters
    top_k: int = 6


class L5Step(BaseModel):
    """L5 Knowledge graph retrieval step."""

    ticker: Ticker
    period: FiscalPeriod
    intent: str = "EXPLANATION"
    root_node_id: int | None = None
    hops: int = 2


class L6Step(BaseModel):
    """L6 Issuer profile card retrieval step."""

    ticker: Ticker


class L7Step(BaseModel):
    """L7 Market technical regime step."""

    ticker: Ticker


class RetrievalPlan(BaseModel):
    """Collection of retrieval steps to execute for a query turn."""

    l2_steps: list[L2Step] = Field(default_factory=list)
    l3_steps: list[L3Step] = Field(default_factory=list)
    l4_steps: list[L4Step] = Field(default_factory=list)
    l5_steps: list[L5Step] = Field(default_factory=list)
    l6_steps: list[L6Step] = Field(default_factory=list)
    l7_steps: list[L7Step] = Field(default_factory=list)


def _resolve_tickers(cls: QueryClassification, sticky: StickyState) -> list[Ticker]:
    if cls.tickers:
        return cls.tickers
    if sticky.focus_ticker:
        return [sticky.focus_ticker]
    return [Ticker("BMRI")]


def _resolve_periods(cls: QueryClassification, sticky: StickyState) -> list[FiscalPeriod]:
    if cls.periods:
        return cls.periods
    if sticky.focus_periods:
        return sticky.focus_periods
    return [FiscalPeriod('2024Q4')]


def plan_retrieval(
    cls: QueryClassification,
    sticky: StickyState,
    original_query: str = "",
) -> RetrievalPlan:
    """Plans deterministic retrieval steps according to BLUEPRINT §8.3 intent matrix."""
    tickers = _resolve_tickers(cls, sticky)
    periods = _resolve_periods(cls, sticky)
    primary_ticker = tickers[0]
    primary_period = periods[0]

    plan = RetrievalPlan()

    if cls.intent == Intent.META:
        return plan

    # 1. Always fetch L6 Issuer Profile for primary ticker
    plan.l6_steps.append(L6Step(ticker=primary_ticker))

    # 2. FACT_LOOKUP
    if cls.intent == Intent.FACT_LOOKUP:
        plan.l2_steps.append(L2Step(ticker=primary_ticker, periods=periods, concepts=cls.concepts))
        plan.l3_steps.append(
            L3Step(
                ticker=primary_ticker,
                periods=periods,
                metric_prefixes=["yoy.", "qoq.", "margin.", "bank.", "mining."],
            )
        )

    # 3. EXPLANATION
    elif cls.intent == Intent.EXPLANATION:
        prev_period = offset_fiscal_period(primary_period, -1)
        plan.l2_steps.append(
            L2Step(
                ticker=primary_ticker, periods=[primary_period, prev_period], concepts=cls.concepts
            )
        )
        plan.l3_steps.append(
            L3Step(
                ticker=primary_ticker,
                periods=[primary_period],
                metric_prefixes=["yoy.", "qoq.", "margin.", "bank.", "mining."],
            )
        )
        plan.l4_steps.append(
            L4Step(
                query=original_query,
                filters=NarrativeFilters(
                    tickers=[primary_ticker],
                    periods=[primary_period, prev_period],
                    sections=["MDA", "GUIDANCE", "RISK"],
                ),
                top_k=6,
            )
        )
        root_id = sticky.last_claim_node_id if cls.is_drill else None
        plan.l5_steps.append(
            L5Step(
                ticker=primary_ticker,
                period=primary_period,
                intent="EXPLANATION",
                root_node_id=root_id,
                hops=2,
            )
        )

    # 4. TREND
    elif cls.intent == Intent.TREND:
        # Include last 4 quarters
        historical_periods = [
            primary_period,
            offset_fiscal_period(primary_period, -1),
            offset_fiscal_period(primary_period, -2),
            offset_fiscal_period(primary_period, -3),
            offset_fiscal_period(primary_period, -4),
        ]
        plan.l2_steps.append(
            L2Step(ticker=primary_ticker, periods=historical_periods, concepts=cls.concepts)
        )
        plan.l3_steps.append(
            L3Step(
                ticker=primary_ticker,
                periods=historical_periods,
                metric_prefixes=["yoy.", "cagr_3y.", "margin."],
            )
        )

    # 5. COMPARE_PEERS
    elif cls.intent == Intent.COMPARE_PEERS:
        all_tickers = list(set(tickers + sticky.peer_set))
        for t in all_tickers:
            plan.l2_steps.append(L2Step(ticker=t, periods=[primary_period], concepts=cls.concepts))
            plan.l3_steps.append(
                L3Step(
                    ticker=t,
                    periods=[primary_period],
                    metric_prefixes=["bank.", "mining.", "margin.", "peer_pct."],
                )
            )
            if t != primary_ticker:
                plan.l6_steps.append(L6Step(ticker=t))

    # 6. GUIDANCE_CHECK
    elif cls.intent == Intent.GUIDANCE_CHECK:
        plan.l5_steps.append(
            L5Step(
                ticker=primary_ticker,
                period=primary_period,
                intent="GUIDANCE_CHECK",
                hops=1,
            )
        )
        plan.l4_steps.append(
            L4Step(
                query=original_query,
                filters=NarrativeFilters(
                    tickers=[primary_ticker],
                    periods=periods,
                    sections=["GUIDANCE", "MDA", "MGMT_STMT"],
                ),
                top_k=6,
            )
        )
        plan.l2_steps.append(L2Step(ticker=primary_ticker, periods=periods, concepts=cls.concepts))

    # 7. SCREEN
    elif cls.intent == Intent.SCREEN:
        plan.l3_steps.append(
            L3Step(
                ticker=primary_ticker,
                periods=[primary_period],
                metric_prefixes=["margin.", "roe", "bank.", "mining."],
            )
        )

    # 8. TECHNICAL
    elif cls.intent == Intent.TECHNICAL:
        plan.l7_steps.append(L7Step(ticker=primary_ticker))

    return plan
