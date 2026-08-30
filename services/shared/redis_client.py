"""Redis and arq queue connection utilities."""

from __future__ import annotations

from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from services.shared.config import Settings, get_settings


def parse_redis_settings(settings: Settings | None = None) -> RedisSettings:
    """Parses RedisSettings from application config URL."""
    cfg = settings or get_settings()
    return RedisSettings.from_dsn(cfg.redis_url)


async def get_redis_pool(settings: Settings | None = None, retry: int = 0) -> ArqRedis:
    """Creates an ArqRedis client pool."""
    redis_settings = parse_redis_settings(settings)
    return await create_pool(redis_settings, retry=retry)


async def enqueue_job(
    pool: ArqRedis,
    function_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Enqueues an asynchronous background job into the arq queue."""
    return await pool.enqueue_job(function_name, *args, **kwargs)
