"""FastAPI dependencies accessing state-managed singletons."""

from __future__ import annotations

from collections.abc import AsyncIterator

from arq.connections import ArqRedis
from fastapi import Request
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.shared.config import Settings, get_settings
from services.shared.db import create_pool
from services.shared.minio_client import get_minio


def get_settings_dep() -> Settings:
    """Returns application settings."""
    return get_settings()


async def get_db_conn(request: Request) -> AsyncIterator[AsyncConnection]:
    """Yields a database connection from the application engine pool."""
    if hasattr(request.app.state, "db_engine") and request.app.state.db_engine:
        engine: AsyncEngine = request.app.state.db_engine
    else:
        engine = create_pool(get_settings().postgres_dsn)
        request.app.state.db_engine = engine

    async with engine.connect() as conn:
        yield conn


get_db = get_db_conn


def get_minio_client(request: Request) -> Minio:
    """Retrieves the MinIO client from app state with lazy fallback."""
    if hasattr(request.app.state, "minio_client") and request.app.state.minio_client:
        return request.app.state.minio_client  # type: ignore[no-any-return]
    minio = get_minio(get_settings())
    request.app.state.minio_client = minio
    return minio


def get_redis(request: Request) -> ArqRedis | None:
    """Retrieves the ArqRedis pool from app state."""
    if hasattr(request.app.state, "redis_pool"):
        return request.app.state.redis_pool  # type: ignore[no-any-return]
    return None
