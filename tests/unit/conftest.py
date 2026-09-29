"""Unit-test guard: unit tests must never open a real database connection.

Any attempt (asyncpg directly, SQLAlchemy's asyncpg dialect, or psycopg) raises
``RealDatabaseAccessError`` so the offending test fails loudly instead of silently writing
into the dev database. Mock the engine/connection instead, or move the test to
``tests/integration`` (which runs against ``emimind_test``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NoReturn

import asyncpg
import psycopg
import pytest

from services.shared.config import get_settings


class RealDatabaseAccessError(RuntimeError):
    """Raised when a unit test tries to reach a real Postgres server."""


def _refuse(target: str) -> Any:
    def _blocked(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise RealDatabaseAccessError(
            f"Unit tests must not connect to a real database ({target} was called). "
            "Mock the engine/connection or move this test to tests/integration."
        )

    return _blocked


@pytest.fixture(autouse=True)
def _block_real_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # SQLAlchemy's asyncpg dialect resolves `asyncpg.connect` at connect time, so patching
    # the module attribute also covers create_async_engine(...).connect().
    monkeypatch.setattr(asyncpg, "connect", _refuse("asyncpg.connect"))
    monkeypatch.setattr(asyncpg, "create_pool", _refuse("asyncpg.create_pool"))
    monkeypatch.setattr(psycopg, "connect", _refuse("psycopg.connect"))
    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(_refuse("psycopg.Connection.connect")))
    monkeypatch.setattr(
        psycopg.AsyncConnection, "connect", classmethod(_refuse("psycopg.AsyncConnection.connect"))
    )
    yield


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Unit tests must not load bge-m3 onto the GPU; tests that exercise the real path pass
    # `mode="real"` to the Embedder explicitly.
    monkeypatch.setenv("EMI_EMBEDDING_MODE", "fake")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
