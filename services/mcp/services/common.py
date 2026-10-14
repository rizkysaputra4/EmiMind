"""Common database, storage, and auditing utilities for EMIMIND MCP services."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from services.shared.config import get_settings
from services.shared.logging import get_logger

# One id per server process. Each MCP client connection runs its own server process, so this
# is the extraction run: ROUTED and COMMITTED log rows carry it, and the acceptance gate counts
# the tokens of the run that made a document's latest commit.
SERVER_RUN_ID = uuid.uuid4().hex

log = get_logger("mcp.services.common")


def _read_sidecar_meta(pdf_path: Path) -> dict[str, Any] | None:
    """Read the .meta.json sidecar written by the downloader for announcement PDFs.

    Sidecar convention: {pdf_path}.meta.json — see design doc §9 and the downloader
    at ../EmiMind-Extraction/scripts/download_idx_reports.py::_write_sidecar.
    Returns None when the file is missing or malformed (never raises).
    """
    sidecar = pdf_path.with_suffix(pdf_path.suffix + ".meta.json")
    if not sidecar.exists():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _archive_processed_file(file_path_str: str) -> str | None:
    """Moves a processed file to a 'processed/' subfolder if located in incoming_reports/."""
    try:
        p = Path(file_path_str).resolve()
        if not p.exists():
            # Try finding it relative to project root or incoming_reports
            alt_candidates = [
                Path("incoming_reports") / p.name,
                Path(".") / p.name,
                Path("incoming_reports") / Path(file_path_str).name,
            ]
            for alt in alt_candidates:
                if alt.resolve().exists():
                    p = alt.resolve()
                    break

        if (
            p.exists()
            and p.is_file()
            and "incoming_reports" in p.parts
            and "processed" not in p.parts
        ):
            processed_dir = p.parent / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            target_path = processed_dir / p.name
            shutil.move(str(p), str(target_path))
            log.info("Archived file to processed directory", src=str(p), dest=str(target_path))
            return str(target_path)
    except Exception as e:
        log.warning("Failed to move processed file to archive", error=str(e))
    return None


async def _log_processing_event(
    conn: Any,
    *,
    action: str,
    source: str,
    file_name: str,
    ticker: str | None = None,
    file_path: str | None = None,
    doc_hash: str | None = None,
    doc_id: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one row to document_processing_log — a durable audit trail of every
    ingest decision (authorized, skipped, extracted, committed, errored).

    Never raises: logging failures must not break the ingest path. On any DB
    error we log locally and swallow. The connection is not committed here —
    the caller is expected to be inside a transaction that will commit as
    part of its normal work.
    """
    try:
        await conn.execute(
            text(
                """
                INSERT INTO document_processing_log
                    (ticker, file_name, file_path, doc_hash, doc_id, action, reason, source, metadata)
                VALUES
                    (:ticker, :file_name, :file_path, :doc_hash, :doc_id, :action, :reason, :source, CAST(:metadata AS jsonb))
                """
            ),
            {
                "ticker": (ticker or None),
                "file_name": file_name,
                "file_path": file_path,
                "doc_hash": doc_hash,
                "doc_id": doc_id,
                "action": action,
                "reason": reason,
                "source": source,
                "metadata": json.dumps(metadata or {}),
            },
        )
    except Exception as exc:
        # Never let logging failure break ingest — log locally and continue.
        log.warning(
            "Failed to write document_processing_log",
            action=action,
            source=source,
            file_name=file_name,
            error=str(exc),
        )


def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.postgres_dsn,
        poolclass=NullPool,
        connect_args={"server_settings": {"statement_timeout": "5000ms"}},
    )
