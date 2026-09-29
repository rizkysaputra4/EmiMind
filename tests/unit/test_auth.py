"""Unit tests for magic-link authentication user lookup (mocked connection, no DB).

The real-database round trip lives in ``tests/integration/test_auth_db.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.auth import get_or_create_user


class _FakeUsersConn:
    """Minimal in-memory stand-in for an AsyncConnection over the `users` table."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.commit = AsyncMock()
        self.statements: list[str] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> MagicMock:
        sql = str(stmt)
        self.statements.append(sql)
        params = params or {}
        result = MagicMock()
        if sql.lstrip().upper().startswith("SELECT"):
            result.mappings.return_value.first.return_value = self.rows.get(params["email"])
        elif sql.lstrip().upper().startswith("INSERT"):
            self.rows[params["email"]] = {
                "id": params["id"],
                "email": params["email"],
                "created_at": params["created_at"],
            }
        return result


@pytest.mark.asyncio
async def test_get_or_create_user_creates_then_reuses() -> None:
    conn = _FakeUsersConn()

    user1 = await get_or_create_user(conn, "  Analyst@Fund.co.id ")  # type: ignore[arg-type]
    assert user1.email == "analyst@fund.co.id"
    assert isinstance(user1.id, uuid.UUID)
    assert conn.commit.await_count == 1

    user2 = await get_or_create_user(conn, "analyst@fund.co.id")  # type: ignore[arg-type]
    assert user2.id == user1.id
    assert conn.commit.await_count == 1  # no second INSERT
    assert sum(s.lstrip().upper().startswith("INSERT") for s in conn.statements) == 1


@pytest.mark.asyncio
async def test_get_or_create_user_returns_existing_row() -> None:
    conn = _FakeUsersConn()
    existing_id = uuid.uuid4()
    created = datetime(2026, 1, 1, tzinfo=UTC)
    conn.rows["pm@fund.co.id"] = {"id": existing_id, "email": "pm@fund.co.id", "created_at": created}

    user = await get_or_create_user(conn, "PM@fund.co.id")  # type: ignore[arg-type]
    assert user.id == existing_id
    assert user.created_at == created
    conn.commit.assert_not_awaited()
