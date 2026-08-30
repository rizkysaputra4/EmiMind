"""Unit tests for conversational transition classifier (drill, pivot, topic_change)."""

from __future__ import annotations

from services.retrieval.session_store import StickyState
from services.retrieval.turn_router import classify_turn_kind
from services.shared.types import Intent, QueryClassification, Ticker


def test_classify_turn_drill() -> None:
    prev = StickyState(focus_ticker=Ticker("BMRI"))
    cls = QueryClassification(
        intent=Intent.FACT_LOOKUP,
        tickers=[Ticker("BMRI")],
        is_drill=True,
    )
    assert classify_turn_kind(prev, cls) == "drill"


def test_classify_turn_pivot() -> None:
    prev = StickyState(focus_ticker=Ticker("BMRI"))
    cls = QueryClassification(
        intent=Intent.EXPLANATION,
        tickers=[Ticker("BBCA")],
    )
    assert classify_turn_kind(prev, cls) == "pivot"


def test_classify_turn_topic_change() -> None:
    prev = StickyState(focus_ticker=Ticker("BMRI"))
    cls = QueryClassification(
        intent=Intent.META,
    )
    assert classify_turn_kind(prev, cls) == "topic_change"
