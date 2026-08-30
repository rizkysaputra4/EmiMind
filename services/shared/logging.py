"""Structured logging configuration using structlog."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from services.shared.config import get_settings


def configure_logging() -> None:
    """Configures stdlib logging and structlog processors."""
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    processors: list[structlog.types.Processor]
    if settings.log_format == "json":
        processors = [*shared_processors, structlog.processors.JSONRenderer()]
    else:
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Returns a structlog BoundLogger with optional initial bound context."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger
