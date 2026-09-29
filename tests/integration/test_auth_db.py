"""Integration test: get_or_create_user against the isolated ``emimind_test`` database."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.api.auth import get_or_create_user
from services.shared.config import get_settings
from services.shared.db import create_pool

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_or_create_user_real_db() -> None:
    settings = get_settings()
    assert settings.postgres_dsn.rpartition("/")[2] != "emimind", "must run on the test DB"
    email = f"it-{uuid.uuid4().hex[:8]}@fund.co.id"
    pool = create_pool(settings.postgres_dsn)
    try:
        async with pool.connect() as conn:
            user1 = await get_or_create_user(conn, email)
            user2 = await get_or_create_user(conn, email)
            assert user1.id == user2.id
            await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
            await conn.commit()
    finally:
        await pool.dispose()
