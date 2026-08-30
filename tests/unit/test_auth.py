"""Unit tests for magic-link authentication and token verification."""

from __future__ import annotations

import pytest

from services.api.auth import get_or_create_user
from services.shared.config import get_settings
from services.shared.db import create_pool


@pytest.mark.asyncio
async def test_get_or_create_user() -> None:
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)

    async with pool.connect() as conn:
        user1 = await get_or_create_user(conn, "analyst@fund.co.id")
        assert user1.email == "analyst@fund.co.id"
        assert user1.id is not None

        # Fetch again to verify idempotency
        user2 = await get_or_create_user(conn, "analyst@fund.co.id")
        assert user1.id == user2.id

    await pool.dispose()
