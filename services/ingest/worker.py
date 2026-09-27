"""arq worker settings and lifecycle handlers for EmiMind."""

from __future__ import annotations

from typing import Any, ClassVar

from services.ingest.tasks.chunk_narrative import chunk_narrative_task
from services.ingest.tasks.derive_metrics import derive_metrics_task
from services.ingest.tasks.embed_narrative import embed_narrative_task
from services.ingest.tasks.extract_tables import extract_tables_task
from services.ingest.tasks.index_pages import index_pages_task
from services.ingest.tasks.ingest_document import ingest_document
from services.ingest.tasks.link_causes import link_causes_task
from services.ingest.tasks.match_actuals import match_actuals_task
from services.ingest.tasks.mine_guidance import mine_guidance_task
from services.ingest.tasks.nightly_market import nightly_market_task
from services.ingest.tasks.nightly_technical import nightly_technical_task
from services.ingest.tasks.normalize_facts import normalize_facts_task
from services.ingest.tasks.parse_layout import parse_layout
from services.ingest.tasks.refresh_profile import refresh_profile_task
from services.ingest.tasks.xbrl_sidecar import xbrl_sidecar
from services.narrative.embedder import Embedder
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import configure_logging, get_logger
from services.shared.minio_client import get_minio
from services.shared.redis_client import parse_redis_settings


async def startup(ctx: dict[str, Any]) -> None:
    """Initializes DB pool, MinIO client, embedder, and structured logger for worker process."""
    configure_logging()
    settings = get_settings()
    log = get_logger("worker")
    log.info("Starting EmiMind ingestion worker...")

    engine = create_pool(settings.postgres_dsn)
    minio = get_minio(settings)
    embedder = Embedder()

    ctx["settings"] = settings
    ctx["log"] = log
    ctx["db_engine"] = engine
    ctx["db_pool"] = engine
    ctx["minio"] = minio
    ctx["minio_client"] = minio
    ctx["embedder"] = embedder


async def shutdown(ctx: dict[str, Any]) -> None:
    """Disposes database engine connections on worker shutdown."""
    log = ctx.get("log", get_logger("worker"))
    log.info("Shutting down EmiMind ingestion worker...")
    if ctx.get("db_engine"):
        await ctx["db_engine"].dispose()


class WorkerSettings:
    """Configuration class consumed by arq CLI."""

    functions: ClassVar[list[Any]] = [
        ingest_document,
        parse_layout,
        index_pages_task,
        extract_tables_task,
        xbrl_sidecar,
        normalize_facts_task,
        chunk_narrative_task,
        embed_narrative_task,
        derive_metrics_task,
        refresh_profile_task,
        mine_guidance_task,
        match_actuals_task,
        link_causes_task,
        nightly_market_task,
        nightly_technical_task,
    ]
    redis_settings = parse_redis_settings()
    job_timeout = 600
    max_jobs = 4
    on_startup = startup
    on_shutdown = shutdown
