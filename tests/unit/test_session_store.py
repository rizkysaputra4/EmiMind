"""Unit tests for chat session store and sticky state models."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.retrieval.session_store import (
    StickyState,
    get_or_create_session,
)
from services.shared.types import FiscalPeriod, Ticker


def test_sticky_state_serialization() -> None:
    state = StickyState(
        focus_ticker=Ticker("BMRI"),
        focus_periods=[FiscalPeriod("2024Q4")],
        peer_set=[Ticker("BBRI"), Ticker("BBCA")],
        active_metrics=["bank.nim", "yoy.revenue"],
    )
    raw = state.model_dump()
    deserialized = StickyState.model_validate(raw)
    assert deserialized.focus_ticker == "BMRI"
    assert len(deserialized.peer_set) == 2


@pytest.mark.asyncio
async def test_get_or_create_session_mock() -> None:
    conn = AsyncMock()
    sid = uuid.uuid4()

    # Session exists query mock
    res = MagicMock()
    res.mappings.return_value.first.return_value = {
        "id": sid,
        "user_id": "test_user",
        "title": "BMRI Analysis",
        "sticky_state": {"focus_ticker": "BMRI", "focus_periods": ["2024Q4"]},
        "rolling_summary": "Prior summary",
        "created_at": "2026-08-27 10:00:00",
        "last_activity_at": "2026-08-27 10:05:00",
    }
    conn.execute.return_value = res

    session = await get_or_create_session(conn, session_id=sid)
    assert session.id == sid
    assert session.sticky_state.focus_ticker == "BMRI"
    assert session.rolling_summary == "Prior summary"
