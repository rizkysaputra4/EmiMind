"""Sliding-window rate limiter enforcing usage limits across free tiers."""

from __future__ import annotations

import time

from fastapi import HTTPException, status

from services.shared.config import get_settings
from services.shared.logging import get_logger
from services.shared.redis_client import get_redis_pool

log = get_logger("api.rate_limit")

# Default daily limits
LIMITS: dict[str, int] = {
    "chat": 20,
    "upload": 20,
    "screener": 30,
}


async def enforce_rate_limit(
    user_id: str,
    action: str,
    limit: int | None = None,
    window_seconds: int = 86400,
) -> None:
    """Enforces Redis-backed sliding-window rate limit for a user and action."""
    settings = get_settings()
    if settings.environment == "dev":
        return  # Bypass in local development mode

    max_allowed = limit or LIMITS.get(action, 20)
    key = f"ratelimit:{action}:{user_id}"
    now = time.time()
    cutoff = now - window_seconds

    try:
        redis = await get_redis_pool(settings)
        # Remove timestamps older than window
        await redis.zremrangebyscore(key, 0, cutoff)
        # Count requests in window
        count = await redis.zcard(key)

        if count >= max_allowed:
            log.warning(
                "Rate limit exceeded",
                user_id=user_id,
                action=action,
                count=count,
                limit=max_allowed,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Daily {action} limit of {max_allowed} requests reached. "
                    f"Please upgrade your tier or wait 24 hours."
                ),
            )

        # Add current timestamp
        await redis.zadd(key, {str(now): now})
        # Set TTL on key
        await redis.expire(key, window_seconds)
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Rate limiter Redis connection error, permitting request", error=str(e))
