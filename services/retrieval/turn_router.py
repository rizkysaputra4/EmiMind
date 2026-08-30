"""Turn routing and conversational transition classifier (drill, pivot, topic_change)."""

from __future__ import annotations

from typing import Literal

from services.retrieval.session_store import StickyState
from services.shared.types import Intent, QueryClassification


def classify_turn_kind(
    prev: StickyState,
    cls: QueryClassification,
) -> Literal["drill", "pivot", "topic_change"]:
    """Classifies the conversational transition between turns based on sticky state and intent."""
    # 1. Meta queries or empty parameters indicate topic change
    if cls.intent == Intent.META:
        return "topic_change"

    # 2. If no previous focus ticker existed, initialize focus (drill/first turn)
    if not prev.focus_ticker:
        return "drill"

    # 3. If explicit new tickers are present
    if cls.tickers:
        primary_ticker = cls.tickers[0]
        if primary_ticker != prev.focus_ticker:
            # New ticker -> pivot
            return "pivot"
        else:
            # Same ticker -> drill
            return "drill"

    # 4. If query is marked as drill or references prior claims
    if cls.is_drill or cls.references_prior_claim:
        return "drill"

    # 5. Default: If intent is peer comparison or screen without matching ticker -> pivot or drill
    if cls.intent in (Intent.COMPARE_PEERS, Intent.SCREEN):
        return "pivot"

    return "drill"
