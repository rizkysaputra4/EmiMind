"""Proves the unit-test DB guard in tests/unit/conftest.py blocks real connections."""

from __future__ import annotations

import psycopg
import pytest
from sqlalchemy import text

from services.shared.db import create_pool
from tests.unit.conftest import RealDatabaseAccessError


async def test_sqlalchemy_async_engine_connect_is_blocked() -> None:
    engine = create_pool("postgresql+asyncpg://emimind:emimind@localhost:5432/emimind")
    with pytest.raises(RealDatabaseAccessError):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    await engine.dispose()


def test_psycopg_connect_is_blocked() -> None:
    with pytest.raises(RealDatabaseAccessError):
        psycopg.connect("postgresql://emimind:emimind@localhost:5432/emimind")
    with pytest.raises(RealDatabaseAccessError):
        psycopg.Connection.connect("postgresql://emimind:emimind@localhost:5432/emimind")
