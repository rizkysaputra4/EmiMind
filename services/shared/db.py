"""Database connection pool and async connection utilities."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from services.shared.config import get_settings


def create_pool(dsn: str | None = None) -> AsyncEngine:
    """Creates an async SQLAlchemy engine with connection pooling and statement timeout."""
    settings = get_settings()
    db_url = dsn or settings.postgres_dsn

    return create_async_engine(
        db_url,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "statement_timeout": "5000ms",
            }
        },
    )


@asynccontextmanager
async def tx(conn: AsyncConnection) -> AsyncIterator[AsyncConnection]:
    """Async context manager creating a transaction/savepoint for transactional isolation."""
    if conn.in_transaction():
        async with conn.begin_nested():
            yield conn
    else:
        async with conn.begin():
            yield conn


async def get_conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Yields an active async database connection."""
    async with engine.connect() as conn:
        yield conn


ACTIVE_FACTS_PREDICATE = (
    "needs_review = false AND (extraction_conf >= 0.7 OR extraction_method = 'xbrl')"
)


def active_facts_query(
    ticker: str | None = None,
    fiscal_period: str | None = None,
    concept_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Constructs parameterized SQL query for financial_facts enforcing the confidence gate.

    Rule: Only rows with needs_review = false and
    (extraction_conf >= 0.7 or extraction_method = 'xbrl') are returned to downstream services.
    """
    conditions = [
        "needs_review = false",
        "(extraction_conf >= 0.7 OR extraction_method = 'xbrl')",
    ]
    params: dict[str, Any] = {}

    if ticker:
        conditions.append("ticker = :ticker")
        params["ticker"] = ticker
    if fiscal_period:
        conditions.append("fiscal_period = :fiscal_period")
        params["fiscal_period"] = fiscal_period
    if concept_id:
        conditions.append("concept_id = :concept_id")
        params["concept_id"] = concept_id

    where_clause = " AND ".join(conditions)
    sql = f"""
    SELECT id, ticker, period_end, fiscal_period, statement, concept_id, concept_local,
           value_numeric, unit, scale, segment, period_type, accounting_std,
           source_doc_id, source_page, source_bbox, extraction_method, extraction_conf,
           needs_review, is_restated, created_at
    FROM financial_facts
    WHERE {where_clause}
    ORDER BY created_at DESC;
    """  # noqa: S608
    return sql.strip(), params
