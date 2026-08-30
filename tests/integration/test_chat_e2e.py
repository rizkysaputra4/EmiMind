"""Integration tests for end-to-end chat conversation turns, session state, and citations."""

from __future__ import annotations

from uuid import UUID

import pytest

from services.retrieval.chat import run_turn
from services.shared.config import get_settings
from services.shared.db import create_pool


@pytest.mark.integration
async def test_chat_turn_e2e() -> None:
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)

    async with pool.connect() as conn:
        # Turn 1: Initial query
        resp1 = await run_turn(
            conn=conn,
            session_id=None,
            message="Why did BMRI net profit increase in 2024?",
            focus_ticker="BMRI",
        )

        assert resp1.session_id is not None
        assert "BMRI" in resp1.answer
        assert len(resp1.citations) >= 1
        assert resp1.citations[0].ticker == "BMRI"
        assert resp1.citations[0].fiscal_period == "2024Q4"
        assert resp1.latency_ms is not None and resp1.latency_ms >= 0

        # Turn 2: Follow-up drill turn
        sid = UUID(resp1.session_id)
        resp2 = await run_turn(
            conn=conn,
            session_id=sid,
            message="Was asset quality stable as well?",
        )

        assert resp2.session_id == resp1.session_id
        assert len(resp2.citations) >= 1

    await pool.dispose()
