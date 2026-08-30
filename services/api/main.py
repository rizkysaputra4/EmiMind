"""FastAPI application entrypoint for EmiMind."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq.connections import ArqRedis
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api import auth
from services.api.routers import admin, chat, citation, screener, sessions, upload
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import configure_logging, get_logger
from services.shared.metrics import METRICS
from services.shared.minio_client import ensure_bucket, get_minio
from services.shared.redis_client import get_redis_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan managing DB, MinIO, and Redis connections."""
    configure_logging()
    log = get_logger("api.main")
    settings = get_settings()

    log.info("Starting EmiMind API...", env=settings.log_format)

    # 1. Initialize DB pool
    engine: AsyncEngine = create_pool(settings.postgres_dsn)
    app.state.db_engine = engine

    # 2. Initialize MinIO client
    try:
        minio_client: Minio = get_minio(settings)
        ensure_bucket(minio_client, settings.minio_bucket_raw)
        app.state.minio_client = minio_client
    except Exception as e:
        log.warning("MinIO initialization deferred or failed", error=str(e))
        app.state.minio_client = get_minio(settings)

    # 3. Initialize Redis pool
    try:
        redis_pool: ArqRedis = await get_redis_pool(settings)
        app.state.redis_pool = redis_pool
    except Exception as e:
        log.warning("Redis initialization deferred or failed", error=str(e))
        app.state.redis_pool = None

    yield

    log.info("Shutting down EmiMind API...")
    if hasattr(app.state, "redis_pool") and app.state.redis_pool:
        await app.state.redis_pool.close()
    if hasattr(app.state, "db_engine") and app.state.db_engine:
        await app.state.db_engine.dispose()


app = FastAPI(
    title="EmiMind API",
    version="1.0.0",
    description="Context-aware AI research platform for the Indonesian Stock Exchange",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def health_check() -> dict[str, bool]:
    """Health check probe."""
    return {"ok": True}


@app.get("/metrics")
async def get_metrics() -> Response:
    """Prometheus exposition metrics endpoint."""
    return Response(content=METRICS.generate_prometheus_text(), media_type="text/plain")


# Include Routers
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(citation.router)
app.include_router(screener.router)
app.include_router(admin.router)
