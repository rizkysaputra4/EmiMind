"""Minimal in-memory stand-in for an SQLAlchemy AsyncEngine/AsyncConnection (unit tests only).

A handler maps each executed SQL string (and its params) to the rows it should return, so
worker tasks can be exercised without Postgres. Every call is recorded for assertions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any

Rows = list[dict[str, Any]]
Handler = Callable[[str, dict[str, Any]], Rows | int | None]


class FakeMappings:
    def __init__(self, rows: Rows) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> Rows:
        return list(self._rows)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._rows)


class FakeResult:
    def __init__(self, rows: Rows, rowcount: int) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def mappings(self) -> FakeMappings:
        return FakeMappings(self._rows)

    def scalar(self) -> Any:
        if not self._rows:
            return None
        return next(iter(self._rows[0].values()))

    def first(self) -> tuple[Any, ...] | None:
        return tuple(self._rows[0].values()) if self._rows else None


class FakeConn:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(stmt).split())
        p = dict(params or {})
        self.calls.append((sql, p))
        out = self.handler(sql, p)
        if isinstance(out, int):
            return FakeResult([], out)
        rows = out or []
        return FakeResult(rows, len(rows) or 1)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    def sql_matching(self, needle: str) -> list[tuple[str, dict[str, Any]]]:
        return [(s, p) for s, p in self.calls if needle in s]


class FakeEngine:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    @asynccontextmanager
    async def connect(self) -> Any:
        yield self.conn
