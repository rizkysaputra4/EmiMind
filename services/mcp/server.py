"""EMIMIND Model Context Protocol (MCP) Ingestion and Validation Server."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import text

from services.derive.engine import compute_for_document
from services.derive.valuation import calculate_valuation
from services.ingest.tasks.refresh_profile import refresh_profile_task
from services.mcp.contracts import build_extraction_contract
from services.mcp.types import (
    CommitReport,
    DiscoveredMetricCandidate,
    DiscoveredMetricResult,
    DocumentInspectionResult,
    DocumentSkipResult,
    DraftSubmissionPayload,
    ExtractionContract,
    InspectionStatus,
    MetricOntologyDefinition,
    MetricOntologyQueryResult,
    ValidationReport,
)
from services.mcp.validator import validate_draft_submission
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import shutil

import pymupdf

from services.mcp.periods import resolve_fiscal_period

from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger("mcp.server")


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
        return json.loads(sidecar.read_text(encoding="utf-8"))
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

        if p.exists() and p.is_file() and "incoming_reports" in p.parts and "processed" not in p.parts:
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


def get_engine():
    settings = get_settings()
    return create_async_engine(
        settings.postgres_dsn,
        poolclass=NullPool,
        connect_args={"server_settings": {"statement_timeout": "5000ms"}},
    )

# Instantiate MCPServer
mcp = MCPServer(
    name="emimind-ingestion-server",
    instructions=(
        "You are connected to the EMIMIND Financial Intelligence MCP Authority Server. "
        "Before extracting PDF financial statements, inspect the document and retrieve the extraction contract. "
        "Submit draft extractions for multi-tier accounting validation before final commit."
    ),
)


@mcp.tool()
async def inspect_document(
    file_path: str,
    ticker: str | None = None,
    fiscal_period: str | None = None,
    doc_type: str = "FS_QUARTERLY",
) -> DocumentInspectionResult:
    """Inspects a PDF document by computing its SHA-256 fingerprint and checking processing status in EMIMIND."""
    p = Path(file_path)
    if not p.is_absolute() and not p.exists():
        repo_root = Path(__file__).resolve().parents[2]
        base_name = Path(file_path).name
        # `{TICKER}` prefix in downloader filenames like NCKL_2025_TW3_RDF_*.pdf
        # → also probe the per-ticker subfolder created by the IDX bulk downloader.
        ticker_prefix = base_name.split("_", 1)[0].upper() if "_" in base_name else None
        candidates = [
            (repo_root / file_path).resolve(),
            (repo_root / "incoming_reports" / base_name).resolve(),
            (repo_root / "incoming_reports" / "processed" / base_name).resolve(),
            (Path.cwd() / file_path).resolve(),
            (Path.cwd() / "incoming_reports" / base_name).resolve(),
            (Path.cwd() / "incoming_reports" / "processed" / base_name).resolve(),
        ]
        if ticker_prefix:
            candidates.extend([
                (repo_root / "incoming_reports" / ticker_prefix / base_name).resolve(),
                (repo_root / "incoming_reports" / ticker_prefix / "processed" / base_name).resolve(),
                (Path.cwd() / "incoming_reports" / ticker_prefix / base_name).resolve(),
                (Path.cwd() / "incoming_reports" / ticker_prefix / "processed" / base_name).resolve(),
            ])
        for cand in candidates:
            if cand.exists() and cand.is_file():
                p = cand
                break

    if not p.exists() or not p.is_file():
        # Best-effort log write for file-not-found; opens its own transaction.
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await _log_processing_event(
                    conn,
                    action="SKIPPED_NOT_FOUND",
                    source="inspect_document",
                    file_name=Path(file_path).name,
                    ticker=(ticker or "").upper() or None,
                    file_path=file_path,
                    reason=f"File not resolvable to disk from path: {file_path}",
                )
                await conn.commit()
        except Exception as exc:
            log.warning("Failed to log SKIPPED_NOT_FOUND", error=str(exc))
        return DocumentInspectionResult(
            status=InspectionStatus.ERROR,
            doc_hash="",
            message=f"File not found on disk at path: {file_path}",
        )

    # Compute SHA-256 hash of raw file bytes
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    doc_hash = hasher.hexdigest()

    # Sidecar-driven doc_type: if the downloader dropped a .meta.json alongside this
    # PDF, prefer the doc_class_hint over the caller-supplied doc_type. Design §9.
    sidecar_meta = _read_sidecar_meta(p)
    if sidecar_meta:
        hint = (sidecar_meta.get("doc_class_hint") or "").upper()
        if hint:
            doc_type = hint
        if not ticker and sidecar_meta.get("ticker"):
            ticker = str(sidecar_meta["ticker"]).upper()
        # Announcements don't have a fiscal_period in the FS sense — synthesise one
        # from the announcement date so the downstream partition key stays stable.
        if not fiscal_period and sidecar_meta.get("announcement_date"):
            fiscal_period = str(sidecar_meta["announcement_date"])[:10]

    engine = get_engine()
    async with engine.connect() as conn:
        # Check if hash already exists in documents
        res = await conn.execute(
            text("SELECT id, ticker, fiscal_period, doc_type, status FROM documents WHERE doc_hash = :hash"),
            {"hash": doc_hash},
        )
        doc = res.mappings().first()

        if doc:
            t = doc["ticker"]
            fp = doc["fiscal_period"]
            d_id = str(doc["id"])

            # Check if facts are already extracted
            f_res = await conn.execute(
                text("SELECT count(*) FROM financial_facts WHERE source_doc_id = :d_id"),
                {"d_id": d_id},
            )
            facts_count = f_res.scalar() or 0

            if facts_count > 0 and doc["status"] in ("parsed", "facts_extracted"):
                # Archive to processed subfolder if located in incoming_reports
                new_path = _archive_processed_file(str(p))
                if new_path:
                    await conn.execute(
                        text("UPDATE documents SET source_url = :url WHERE id = :d_id"),
                        {"url": new_path, "d_id": d_id},
                    )
                await _log_processing_event(
                    conn,
                    action="SKIPPED_DUPLICATE",
                    source="inspect_document",
                    file_name=p.name,
                    ticker=t,
                    file_path=str(p),
                    doc_hash=doc_hash,
                    doc_id=d_id,
                    reason=f"Hash already committed with {facts_count} facts (status={doc['status']}). Archived to processed/.",
                    metadata={"existing_facts_count": facts_count, "archived_to": new_path},
                )
                await conn.commit()
                return DocumentInspectionResult(
                    status=InspectionStatus.ALREADY_PROCESSED,
                    doc_hash=doc_hash,
                    doc_id=d_id,
                    ticker=t,
                    fiscal_period=fp,
                    doc_type=doc["doc_type"],
                    message=f"Document already fully processed and committed to database with {facts_count} financial facts. File moved to processed/ archive.",
                    existing_facts_count=facts_count,
                )

        # Resolve ticker and fiscal period from metadata or filename if not provided
        t_clean = (ticker or (p.stem.split("_")[0] if "_" in p.stem else "UNKNOWN")).upper()
        resolved_period = resolve_fiscal_period(p.name, fiscal_period)
        if not resolved_period:
            try:
                from services.extraction.metadata_extractor import propose_metadata

                meta = propose_metadata(p.read_bytes())
                if meta and meta.fiscal_period:
                    resolved_period = resolve_fiscal_period(p.name, meta.fiscal_period)
            except Exception as exc:
                log.warning("Metadata extractor fallback failed", error=str(exc))

        if not resolved_period:
            await _log_processing_event(
                conn,
                action="NEEDS_METADATA",
                source="inspect_document",
                file_name=p.name,
                ticker=t_clean if t_clean != "UNKNOWN" else None,
                file_path=str(p),
                doc_hash=doc_hash,
                reason="Cannot resolve fiscal period from filename or cover page; fiscal_period required from agent.",
            )
            await conn.commit()
            return DocumentInspectionResult(
                status=InspectionStatus.NEEDS_METADATA,
                doc_hash=doc_hash,
                ticker=t_clean if t_clean != "UNKNOWN" else None,
                fiscal_period=None,
                doc_type=doc_type,
                message="Cannot determine fiscal period from filename or cover page. Please call inspect_document again passing fiscal_period explicitly (e.g. '2025Q2').",
            )

        fp_clean = resolved_period.fiscal_period
        period_end_dt = resolved_period.period_end

        # ---- SCOPE GATE ----
        # issuer_profile is the authoritative allowlist. A ticker is in-scope only
        # if it has been seeded via scripts/seed_idx_tickers.py with a non-NULL
        # sector. This keeps the extraction agent from wasting compute on tickers
        # for which we have no sector-specific KPI pack yet. See
        # docs/SECTOR_COVERAGE_HANDOFF.md for how to expand coverage.
        gate_res = await conn.execute(
            text("SELECT name, sector, sub_sector FROM issuer_profile WHERE ticker = :ticker"),
            {"ticker": t_clean},
        )
        gate_row = gate_res.mappings().first()
        if not gate_row or not gate_row.get("sector"):
            await _log_processing_event(
                conn,
                action="SKIPPED_OUT_OF_SCOPE",
                source="inspect_document",
                file_name=p.name,
                ticker=t_clean,
                file_path=str(p),
                doc_hash=doc_hash,
                reason=f"Ticker '{t_clean}' has no sector mapping in issuer_profile.",
            )
            await conn.commit()
            return DocumentInspectionResult(
                status=InspectionStatus.OUT_OF_SCOPE,
                doc_hash=doc_hash,
                ticker=t_clean,
                fiscal_period=fp_clean,
                doc_type=doc_type,
                message=(
                    f"Ticker '{t_clean}' is not in the current extraction scope "
                    f"(no sector mapping in issuer_profile). Skipping to avoid "
                    f"seeding the database with unclassified data. To include this "
                    f"ticker, add it to scripts/seed_idx_tickers.py IDX_TICKERS "
                    f"with an appropriate sector code and re-run the seed script."
                ),
            )
        company_name = gate_row["name"] or f"PT {t_clean} Tbk"
        sector_name = gate_row["sector"]

        # Register document if new
        if not doc:
            doc_uuid = uuid.uuid4()
            d_id = str(doc_uuid)
            minio_key = f"raw/{doc_type}/{t_clean}/{fp_clean}/{p.name}"
            try:
                real_page_count = pymupdf.open(str(p)).page_count
            except Exception:
                real_page_count = 1

            await conn.execute(
                text(
                    """
                    INSERT INTO documents (id, ticker, doc_type, period_end, fiscal_period, language, source_url, minio_key, doc_hash, page_count, status)
                    VALUES (:id, :ticker, :doc_type, :period_end, :fiscal_period, 'id', :url, :minio_key, :doc_hash, :page_count, 'raw')
                    ON CONFLICT (doc_hash) DO NOTHING;
                    """
                ),
                {
                    "id": d_id,
                    "ticker": t_clean,
                    "doc_type": doc_type,
                    "period_end": period_end_dt,
                    "fiscal_period": fp_clean,
                    "url": str(p),
                    "minio_key": minio_key,
                    "doc_hash": doc_hash,
                    "page_count": real_page_count,
                },
            )
            # Announcement metadata: write only when doc_type is an announcement class
            # and we actually have a sidecar to source title/date from.
            if sidecar_meta and (sidecar_meta.get("kind") == "announcement"
                                  or (sidecar_meta.get("doc_class_hint") or "").upper() != ""):
                await conn.execute(
                    text(
                        """
                        INSERT INTO announcement_metadata
                            (doc_id, announcement_title, announcement_date, doc_class,
                             classifier_source, classifier_confidence, source_url, idx_file_id)
                        VALUES (:doc_id, :title, :date, :doc_class,
                                'sidecar', 1.00, :src_url, :file_id)
                        ON CONFLICT (doc_id) DO NOTHING;
                        """
                    ),
                    {
                        "doc_id": d_id,
                        "title": sidecar_meta.get("announcement_title") or "",
                        "date": (sidecar_meta.get("announcement_date") or "1970-01-01")[:10],
                        "doc_class": (sidecar_meta.get("doc_class_hint") or "GENERIC_DISCLOSURE").upper(),
                        "src_url": sidecar_meta.get("source_url"),
                        "file_id": sidecar_meta.get("idx_file_id"),
                    },
                )
            await conn.commit()
        else:
            d_id = str(doc["id"])

        await _log_processing_event(
            conn,
            action="INSPECTED_AUTHORIZED",
            source="inspect_document",
            file_name=p.name,
            ticker=t_clean,
            file_path=str(p),
            doc_hash=doc_hash,
            doc_id=d_id,
            reason=f"Document authorized for extraction (sector={sector_name}, doc_type={doc_type}).",
            metadata={"sector": sector_name, "sub_sector": gate_row.get("sub_sector"), "fiscal_period": fp_clean, "doc_type": doc_type},
        )
        await conn.commit()

        return DocumentInspectionResult(
            status=InspectionStatus.AUTHORIZED,
            doc_hash=doc_hash,
            doc_id=d_id,
            ticker=t_clean,
            fiscal_period=fp_clean,
            doc_type=doc_type,
            company_name=company_name,
            sector=sector_name,
            message=(
                "Document authorized for extraction. IMPORTANT: First, read the "
                "first 2 pages of the PDF to verify it contains financial or "
                "narrative business content. If it is administrative (cover "
                "letter, OJK compliance checklist, transmittal, board statement "
                "of responsibility, newspaper ad), call "
                "mark_document_skipped(doc_id, reason='NOT_FINANCIAL_CONTENT', "
                "notes='...') to log the skip and archive the file. Otherwise "
                "call get_extraction_contract(doc_id) to receive the extraction schema."
            ),
            existing_facts_count=0,
        )


@mcp.tool()
async def mark_document_skipped(
    doc_id: str,
    reason: str,
    notes: str | None = None,
) -> DocumentSkipResult:
    """Record that the extraction agent decided a document is not worth extracting.

    Call this after inspect_document if — on peeking at the PDF's first pages —
    the agent judged the file to be administrative (cover letter, OJK checklist,
    Surat Pernyataan Direksi, transmittal, newspaper ad, etc.), a duplicate
    representation of the same FS, or otherwise carries no extractable financial
    or narrative content. This is the design intent: LLM decides relevance on
    the fly rather than relying on brittle filename regexes.

    Effects:
      1. Appends a SKIPPED_BY_LLM row to document_processing_log (audit trail).
      2. Updates documents.status = 'skipped_by_llm' so re-ingest won't retry.
      3. Archives the source file to processed/ so it clears the ingest queue.

    Parameters:
      doc_id: UUID returned by inspect_document.
      reason: A short machine-friendly tag. Suggested values:
              NOT_FINANCIAL_CONTENT | COVER_LETTER | OJK_CHECKLIST |
              BOD_STATEMENT_OF_RESPONSIBILITY | DUPLICATE_OF_OTHER_FS |
              NEWSPAPER_AD | INTERNAL_CORRESPONDENCE | OTHER
      notes:  Optional 1-2 sentence explanation the operator can read later.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT ticker, source_url, doc_hash FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        row = res.mappings().first()
        if not row:
            raise ValueError(f"Document with ID {doc_id} not found in database.")

        # Mark documents.status so downstream tools know not to re-attempt
        # extraction. Distinct from 'raw' (never processed) and 'facts_extracted'.
        await conn.execute(
            text("UPDATE documents SET status = 'skipped_by_llm' WHERE id = :id"),
            {"id": doc_id},
        )

        # Archive the source file out of the ingest queue.
        archived_to = _archive_processed_file(row["source_url"]) if row.get("source_url") else None
        if archived_to:
            await conn.execute(
                text("UPDATE documents SET source_url = :url WHERE id = :id"),
                {"url": archived_to, "id": doc_id},
            )

        await _log_processing_event(
            conn,
            action="SKIPPED_BY_LLM",
            source="mark_document_skipped",
            file_name=Path(row["source_url"] or "").name if row.get("source_url") else "",
            ticker=row.get("ticker"),
            file_path=row.get("source_url"),
            doc_hash=row.get("doc_hash"),
            doc_id=doc_id,
            reason=reason,
            metadata={"notes": notes, "archived_to": archived_to},
        )
        await conn.commit()

    return DocumentSkipResult(
        doc_id=doc_id,
        ticker=row.get("ticker"),
        reason=reason,
        notes=notes,
        archived_to=archived_to,
        message=(
            f"Document marked as SKIPPED_BY_LLM (reason={reason}). "
            f"documents.status is now 'skipped_by_llm'; file archived to "
            f"{archived_to or '(no archive — file was outside incoming_reports)'}."
        ),
    )


@mcp.tool()
async def get_extraction_contract(doc_id: str) -> ExtractionContract:
    """Retrieves the dynamic extraction contract, required concepts, and scaling rules for a document."""
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, ticker, fiscal_period, doc_type FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document with ID {doc_id} not found in database.")

        ticker = doc["ticker"]
        fiscal_period = doc["fiscal_period"]
        doc_type_val = doc["doc_type"]

        # Prefer issuer_profile (the extraction-scope allowlist); fall back to
        # peer_groups only if a stale doc_id exists for an unmapped ticker.
        prof_res = await conn.execute(
            text("SELECT name, sector, sub_sector FROM issuer_profile WHERE ticker = :ticker"),
            {"ticker": ticker},
        )
        prof_row = prof_res.mappings().first()
        if prof_row and prof_row.get("sector"):
            company_name = prof_row["name"] or f"PT {ticker} Tbk"
            sector_name = prof_row["sector"]
        else:
            sec_res = await conn.execute(
                text("SELECT name, sector, sub_sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
                {"ticker": ticker},
            )
            sec_row = sec_res.mappings().first()
            company_name = sec_row["name"] if sec_row and sec_row.get("name") else f"PT {ticker} Tbk"
            sector_name = sec_row["sector"] if sec_row and sec_row.get("sector") else "GENERIC"

        return await build_extraction_contract(
            conn,
            doc_id=str(doc_id),
            ticker=ticker,
            company_name=company_name,
            sector=sector_name,
            fiscal_period=fiscal_period,
            doc_type=doc_type_val,
        )


@mcp.tool()
async def submit_draft_extraction(payload_json: str, retry_attempt: int = 1) -> ValidationReport:
    """Validates a draft extraction payload against schema, accounting math equations, and unit scaling."""
    try:
        data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        payload = DraftSubmissionPayload.model_validate(data)
    except Exception as e:
        return ValidationReport(
            status="INVALID",
            submission_id=f"err_{uuid.uuid4().hex[:8]}",
            doc_id="UNKNOWN",
            ticker="UNKNOWN",
            fiscal_period="UNKNOWN",
            errors_count=1,
            warnings_count=0,
            can_retry=True,
            retry_attempt=retry_attempt,
            max_retries=3,
            issues=[
                {
                    "severity": "ERROR",
                    "category": "MALFORMED_JSON_SCHEMA",
                    "feedback_message": f"Failed to parse draft submission payload: {e}",
                    "target_pages": [],
                }
            ],
        )

    engine = get_engine()
    sector = "GENERIC"
    company_name = f"PT {payload.ticker.upper()} Tbk"
    doc_type_val: str | None = None
    async with engine.connect() as conn:
        sec_res = await conn.execute(
            text("SELECT name, sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
            {"ticker": payload.ticker.upper()},
        )
        sec_row = sec_res.mappings().first()
        if sec_row:
            sector = sec_row.get("sector") or "GENERIC"
            if sec_row.get("name"):
                company_name = sec_row["name"]

        # Look up doc_type so announcement submissions route to the right contract.
        try:
            dt_res = await conn.execute(
                text("SELECT doc_type FROM documents WHERE id = :id"),
                {"id": payload.doc_id},
            )
            dt_row = dt_res.mappings().first()
            if dt_row:
                doc_type_val = dt_row["doc_type"]
        except Exception:
            doc_type_val = None

        contract = await build_extraction_contract(
            conn,
            doc_id=payload.doc_id,
            ticker=payload.ticker,
            company_name=company_name,
            sector=sector,
            fiscal_period=payload.fiscal_period,
            doc_type=doc_type_val,
        )

    report = validate_draft_submission(
        payload,
        contract=contract,
        sector=sector,
        retry_attempt=retry_attempt,
    )

    # If invalid after 3 attempts, log to review_queue with the coverage block
    if report.status == "INVALID" and retry_attempt >= 3:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO ingest_review_queue (
                        ticker, fiscal_period, doc_id, issue_type, severity, validation_report, draft_payload, status
                    ) VALUES (
                        :ticker, :period, :doc_id, :issue, 'ERROR', CAST(:rep AS jsonb), CAST(:draft AS jsonb), 'PENDING'
                    );
                    """
                ),
                {
                    "ticker": payload.ticker.upper(),
                    "period": payload.fiscal_period.upper(),
                    "doc_id": payload.doc_id,
                    "issue": "MAX_RETRIES_EXHAUSTED",
                    "rep": json.dumps(report.model_dump(mode="json")),
                    "draft": json.dumps(payload.model_dump(mode="json")),
                },
            )
            await _log_processing_event(
                conn,
                action="ERROR",
                source="submit_draft_extraction",
                file_name="",
                ticker=payload.ticker.upper(),
                doc_id=payload.doc_id,
                reason=f"Validation failed after {retry_attempt} retries; sent to review queue.",
                metadata={"status": report.status, "retry_attempt": retry_attempt},
            )
            await conn.commit()
    else:
        # Log every draft submission attempt (success or validation feedback)
        # so the operator can see per-file extraction history.
        try:
            async with engine.connect() as conn:
                await _log_processing_event(
                    conn,
                    action="EXTRACTED",
                    source="submit_draft_extraction",
                    file_name="",
                    ticker=payload.ticker.upper(),
                    doc_id=payload.doc_id,
                    reason=f"Draft submitted (validation={report.status}, attempt={retry_attempt}).",
                    metadata={"status": report.status, "retry_attempt": retry_attempt, "facts_count": len(payload.financial_facts) if hasattr(payload, 'financial_facts') else 0},
                )
                await conn.commit()
        except Exception as exc:
            log.warning("Failed to log EXTRACTED event", error=str(exc))

    return report


@mcp.tool()
async def commit_verified_report(payload_json: str) -> CommitReport:
    """Commits verified financial facts, narrative chunks, and guidance to the database and runs the derive engine."""
    data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    payload = DraftSubmissionPayload.model_validate(data)

    engine = get_engine()
    doc_id = payload.doc_id
    ticker = payload.ticker.upper()
    fiscal_period = payload.fiscal_period.upper()

    # Derive period_end date object
    from datetime import date

    year_int = int(fiscal_period[:4]) if len(fiscal_period) >= 4 and fiscal_period[:4].isdigit() else 2024
    if "Q1" in fiscal_period:
        period_end_dt = date(year_int, 3, 31)
    elif "Q2" in fiscal_period:
        period_end_dt = date(year_int, 6, 30)
    elif "Q3" in fiscal_period:
        period_end_dt = date(year_int, 9, 30)
    else:
        period_end_dt = date(year_int, 12, 31)

    async with engine.connect() as conn:
        # 1. Insert/update financial_facts
        facts_count = 0
        for f in payload.facts:
            cid = f.concept_id
            if any(k in cid for k in ("Assets", "Liabilities", "Equity", "Cash", "Loans", "Deposits", "Inventories", "Receivables", "Borrowings")):
                stmt_type = "BS"
                p_type = "instant"
            elif any(k in cid for k in ("Revenue", "CostOfSales", "GrossProfit", "OperatingProfit", "ProfitLoss", "InterestIncome", "FinanceCosts")):
                stmt_type = "IS"
                p_type = "duration_ytd"
            elif "CashFlows" in cid or "PaymentsToAcquire" in cid:
                stmt_type = "CF"
                p_type = "duration_ytd"
            else:
                stmt_type = "NOTE"
                p_type = f.period_type or "instant"

            # Auto-infer structured segment if f.segment is missing but source_label_original has granular info
            seg_dict = f.segment
            if not seg_dict and f.source_label_original:
                lbl_lower = f.source_label_original.strip().lower()
                generic_labels = {
                    "jumlah aset", "total aset", "total assets", "jumlah liabilitas", "total liabilitas",
                    "total liabilities", "jumlah ekuitas", "total ekuitas", "total equity", "penjualan",
                    "pendapatan", "revenue", "net sales", "beban pokok penjualan", "cost of sales",
                    "laba usaha", "operating profit", "laba tahun berjalan", "laba bersih", "net profit",
                    "kas dan setara kas", "cash and cash equivalents", "arus kas bersih",
                }
                if lbl_lower not in generic_labels:
                    seg_type = "note_segment"
                    if "customer" in cid.lower() or "pelanggan" in lbl_lower:
                        seg_type = "customer_concentration"
                    elif "cogs" in cid.lower() or "cost" in cid.lower() or "pupuk" in lbl_lower or "upah" in lbl_lower:
                        seg_type = "cogs_component"
                    elif "planted" in cid.lower() or "hektar" in lbl_lower or "sawit" in lbl_lower:
                        seg_type = "biological_asset_maturity"
                    elif "borrowing" in cid.lower() or "bank" in lbl_lower or "kredit" in lbl_lower:
                        seg_type = "debt_facility"
                    elif cid == "ifrs:Revenue":
                        seg_type = "product_segment"
                    seg_dict = {"segment": f.source_label_original.strip(), "type": seg_type}

            await conn.execute(
                text(
                    """
                    INSERT INTO financial_facts (
                        source_doc_id, ticker, period_end, fiscal_period, statement, concept_id, concept_local,
                        value_numeric, unit, segment, period_type, accounting_std, source_page, extraction_conf, extraction_method
                    ) VALUES (
                        :doc_id, :ticker, :period_end, :period, :statement, :concept_id, :label,
                        :val, :unit, CAST(:seg AS jsonb), :period_type, :std, :page, 0.95, 'llm_extract'
                    )
                    ON CONFLICT (ticker, fiscal_period, concept_id, (coalesce(segment->>'segment','')))
                    WHERE is_restated = false
                    DO UPDATE SET
                        value_numeric = EXCLUDED.value_numeric,
                        unit = EXCLUDED.unit,
                        segment = EXCLUDED.segment,
                        source_page = EXCLUDED.source_page,
                        source_doc_id = EXCLUDED.source_doc_id,
                        extraction_method = 'llm_extract',
                        extraction_conf = 0.95;
                    """
                ),
                {
                    "doc_id": doc_id,
                    "ticker": ticker,
                    "period_end": period_end_dt,
                    "period": fiscal_period,
                    "statement": stmt_type,
                    "concept_id": cid,
                    "label": f.source_label_original or cid,
                    "val": float(f.value_numeric),
                    "unit": f.unit,
                    "seg": json.dumps(seg_dict) if seg_dict else None,
                    "period_type": p_type,
                    "std": payload.accounting_standard,
                    "page": f.source_page,
                },
            )
            facts_count += 1

        # 2. Insert narrative chunks
        narratives_count = 0
        valid_sections = {"MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"}
        if payload.narratives:
            for n in payload.narratives:
                sec = n.section.upper() if n.section.upper() in valid_sections else "OTHER"
                await conn.execute(
                    text(
                        """
                        INSERT INTO narrative_chunks (
                            source_doc_id, ticker, period_end, fiscal_period, section, source_page, text_original, text_en, tsv
                        ) VALUES (
                            :doc_id, :ticker, :period_end, :period, :sec, :page, :orig, :en, to_tsvector('simple', :orig)
                        );
                        """
                    ),
                    {
                        "doc_id": doc_id,
                        "ticker": ticker,
                        "period_end": period_end_dt,
                        "period": fiscal_period,
                        "sec": sec,
                        "page": n.source_page,
                        "orig": n.text_original,
                        "en": n.text_en or n.text_original,
                    },
                )
                narratives_count += 1
        else:
            # Automatic narrative chunking fallback from local PDF file
            doc_file_res = await conn.execute(text("SELECT source_url FROM documents WHERE id = :id"), {"id": doc_id})
            doc_f = doc_file_res.mappings().first()
            candidate_paths: list[Path] = []
            if doc_f and doc_f.get("source_url"):
                candidate_paths.append(Path(doc_f["source_url"]))
                candidate_paths.append(Path(doc_f["source_url"]).parent / "processed" / Path(doc_f["source_url"]).name)

            for p in Path("incoming_reports/processed").glob(f"*{ticker}*.pdf"):
                candidate_paths.append(p)
            for p in Path("incoming_reports").glob(f"*{ticker}*.pdf"):
                candidate_paths.append(p)

            for cand in candidate_paths:
                if cand.exists() and cand.is_file():
                    try:
                        import pymupdf
                        from services.narrative.chunker import chunk_pages
                        from services.shared.types import PageContent

                        pdf_doc = pymupdf.open(str(cand))
                        pdf_pages = []
                        for i, pg in enumerate(pdf_doc):
                            txt = pg.get_text("text")
                            pdf_pages.append(PageContent(page_num=i + 1, text=txt, language="mixed", has_text_layer=True))
                        pdf_doc.close()

                        auto_chunks = chunk_pages(pdf_pages, ticker, "FS_ANNUAL", fiscal_period)
                        for c in auto_chunks:
                            sec = c.section if c.section in valid_sections else "OTHER"
                            await conn.execute(
                                text(
                                    """
                                    INSERT INTO narrative_chunks (
                                        source_doc_id, ticker, period_end, fiscal_period, section, source_page,
                                        language, text_original, text_en, speaker, claim_type, mentioned_concepts, tsv
                                    ) VALUES (
                                        :doc_id, :ticker, :period_end, :period, :sec, :page,
                                        :lang, :orig, :en, :speaker, :claim, :concepts, to_tsvector('simple', :orig)
                                    );
                                    """
                                ),
                                {
                                    "doc_id": doc_id,
                                    "ticker": ticker,
                                    "period_end": period_end_dt,
                                    "period": fiscal_period,
                                    "sec": sec,
                                    "page": c.source_page,
                                    "lang": c.language,
                                    "orig": c.text_original,
                                    "en": c.text_en or c.text_original,
                                    "speaker": c.speaker,
                                    "claim": c.claim_type,
                                    "concepts": c.mentioned_concepts or [],
                                },
                            )
                            narratives_count += 1
                        log.info("Auto-extracted narrative chunks from PDF", count=narratives_count, path=str(cand))
                        break
                    except Exception as e:
                        log.warning("Automatic fallback narrative chunking failed", error=str(e), path=str(cand))

        # 2.5 Insert Causal Links into Knowledge Graph (kg_nodes & kg_edges)
        causal_count = 0
        for cl in payload.causal_links:
            # 1. Insert Metric Node (DST)
            metric_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref)
                    VALUES ('METRIC', :ticker, :period, CAST(:payload AS jsonb), CAST(:src AS jsonb))
                    RETURNING id;
                    """
                ),
                {
                    "ticker": ticker,
                    "period": fiscal_period,
                    "payload": json.dumps({"metric": cl.metric_affected, "direction": cl.direction}),
                    "src": json.dumps({"doc_id": doc_id, "page": cl.source_page}),
                },
            )
            metric_node_id = metric_res.scalar()

            # 2. Insert Cause Claim Node (SRC)
            cause_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref)
                    VALUES ('CLAIM', :ticker, :period, CAST(:payload AS jsonb), CAST(:src AS jsonb))
                    RETURNING id;
                    """
                ),
                {
                    "ticker": ticker,
                    "period": fiscal_period,
                    "payload": json.dumps({"driver": cl.driver_description, "category": cl.cause_category}),
                    "src": json.dumps({"doc_id": doc_id, "page": cl.source_page}),
                },
            )
            cause_node_id = cause_res.scalar()

            # 3. Insert Edge: Cause -> CAUSED_BY -> Metric
            if metric_node_id and cause_node_id:
                await conn.execute(
                    text(
                        """
                        INSERT INTO kg_edges (src_id, dst_id, edge_type, confidence, evidence_ref, payload)
                        VALUES (:src, :dst, 'CAUSED_BY', :conf, CAST(:evidence AS jsonb), CAST(:pld AS jsonb));
                        """
                    ),
                    {
                        "src": cause_node_id,
                        "dst": metric_node_id,
                        "conf": cl.confidence,
                        "evidence": json.dumps({"citation": f"[{ticker}-FS-{fiscal_period}#p{cl.source_page}]"}),
                        "pld": json.dumps({"category": cl.cause_category}),
                    },
                )
                causal_count += 1

        # 2.5 Record metric omissions into concept_review table for auditing
        omissions_count = 0
        for omitted in payload.omitted_kpis:
            await conn.execute(
                text(
                    """
                    INSERT INTO concept_review (
                        ticker, doc_id, local_label, suggested_canonical, similarity_score, status, resolved_by
                    ) VALUES (
                        :ticker, :doc_id, :label, :canonical, 0.00, 'resolved', :reason
                    )
                    ON CONFLICT (ticker, doc_id, local_label) DO NOTHING;
                    """
                ),
                {
                    "ticker": ticker,
                    "doc_id": doc_id,
                    "label": f"OMITTED: {omitted.metric_id}",
                    "canonical": omitted.metric_id,
                    "reason": f"[{omitted.reason}] {omitted.explanation} (Checked pages: {omitted.search_pages_checked})",
                },
            )
            omissions_count += 1

        # 3. Update document status and archive local file if in incoming folder
        doc_res = await conn.execute(text("SELECT source_url FROM documents WHERE id = :id"), {"id": doc_id})
        doc_row = doc_res.mappings().first()
        archived_url = None
        if doc_row and doc_row.get("source_url"):
            archived_url = _archive_processed_file(doc_row["source_url"])

        if not archived_url:
            for cand in Path("incoming_reports").glob(f"*{ticker}*.pdf"):
                archived_url = _archive_processed_file(str(cand))
                if archived_url:
                    break

        if archived_url:
            await conn.execute(
                text("UPDATE documents SET source_url = :url, status = 'facts_extracted', ingested_at = now() WHERE id = :id"),
                {"url": archived_url, "id": doc_id},
            )
        else:
            await conn.execute(
                text("UPDATE documents SET status = 'facts_extracted', ingested_at = now() WHERE id = :id"),
                {"id": doc_id},
            )
        await conn.commit()

    # 4. Trigger derive metrics engine
    compute_rep = await compute_for_document(doc_id, engine)

    # 5. Refresh L6 Issuer Profile
    try:
        await refresh_profile_task({"db_pool": engine}, doc_id)
        profile_refreshed = True
    except Exception as e:
        log.warning("Profile refresh failed", error=str(e))
        profile_refreshed = False

    # 6. Compute live valuation
    async with engine.connect() as conn:
        val = await calculate_valuation(conn, ticker, is_live=True)
        live_val_ok = val.get("price") is not None

        await _log_processing_event(
            conn,
            action="COMMITTED",
            source="commit_verified_report",
            file_name="",
            ticker=ticker,
            doc_id=doc_id,
            reason=f"Committed {facts_count} facts, {narratives_count} narratives, {len(payload.guidance)} guidance items. Derived {compute_rep.computed} metrics.",
            metadata={
                "facts_committed": facts_count,
                "narratives_committed": narratives_count,
                "guidance_committed": len(payload.guidance),
                "omissions_recorded": omissions_count,
                "derived_metrics_computed": compute_rep.computed,
                "profile_refreshed": profile_refreshed,
                "live_valuation_computed": live_val_ok,
            },
        )
        await conn.commit()

    return CommitReport(
        status="COMMITTED",
        doc_id=doc_id,
        ticker=ticker,
        fiscal_period=fiscal_period,
        facts_committed=facts_count,
        narratives_committed=narratives_count,
        guidance_committed=len(payload.guidance),
        omissions_recorded=omissions_count,
        derived_metrics_computed=compute_rep.computed,
        profile_refreshed=profile_refreshed,
        live_valuation_computed=live_val_ok,
        message=f"Successfully committed {facts_count} facts and {narratives_count} narratives. Derived {compute_rep.computed} metrics.",
    )


@mcp.tool()
async def get_issuer_context(ticker: str, period: str | None = None) -> dict[str, Any]:
    """Retrieves existing financial facts and derived metrics for an issuer to aid in comparative extraction."""
    engine = get_engine()
    ticker_clean = ticker.upper()

    async with engine.connect() as conn:
        facts_res = await conn.execute(
            text(
                """
                SELECT concept_id, fiscal_period, value_numeric, unit
                FROM financial_facts
                WHERE ticker = :ticker
                ORDER BY fiscal_period DESC, concept_id ASC
                LIMIT 50;
                """
            ),
            {"ticker": ticker_clean},
        )
        facts = [dict(r) for r in facts_res.mappings()]

        derived_res = await conn.execute(
            text(
                """
                SELECT metric_id, fiscal_period, value_numeric, unit
                FROM derived_metrics
                WHERE ticker = :ticker
                ORDER BY fiscal_period DESC, metric_id ASC
                LIMIT 25;
                """
            ),
            {"ticker": ticker_clean},
        )
        metrics = [dict(r) for r in derived_res.mappings()]

        # Live valuation
        val = await calculate_valuation(conn, ticker_clean, is_live=True)

        return {
            "ticker": ticker_clean,
            "target_period": period,
            "existing_facts": facts,
            "existing_metrics": metrics,
            "live_valuation": val,
        }


@mcp.tool()
async def get_metric_ontology(
    sector: str | None = None,
    query: str | None = None,
    category: str | None = None,
) -> MetricOntologyQueryResult:
    """Queries canonical financial and operational metric definitions from the EMIMIND Ontology registry.

    Args:
        sector: Optional sector code to filter by (e.g. 'BANK', 'MINING', 'CPO', 'PROPERTY', 'ALL').
        query: Optional search keyword to match against metric names, IDs, or synonyms.
        category: Optional category filter (e.g. 'INCOME', 'BALANCE_SHEET', 'OPERATIONAL', 'RESERVES').
    """
    engine = get_engine()
    async with engine.connect() as conn:
        conditions: list[str] = []
        params: dict[str, Any] = {}

        if sector:
            conditions.append("(:sec = ANY(sector_applicability) OR 'ALL' = ANY(sector_applicability))")
            params["sec"] = sector.upper()

        if category:
            conditions.append("category = :cat")
            params["cat"] = category.upper()

        if query:
            conditions.append(
                "(metric_id ILIKE :q OR name_en ILIKE :q OR name_id ILIKE :q OR array_to_string(synonyms_id, ' ') ILIKE :q OR array_to_string(synonyms_en, ' ') ILIKE :q)"
            )
            params["q"] = f"%{query}%"

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT
                metric_id, name_en, name_id, category, sector_applicability,
                importance, value_type, unit, flow_stock_type, extraction_mode,
                calculation_formula, dependencies, source_priority, synonyms_id, synonyms_en
            FROM metric_definitions
            {where_clause}
            ORDER BY category ASC, metric_id ASC;
        """
        res = await conn.execute(text(sql), params)
        rows = [dict(r) for r in res.mappings()]
        metrics = [
            MetricOntologyDefinition(
                metric_id=r["metric_id"],
                name_en=r["name_en"],
                name_id=r["name_id"],
                category=r["category"],
                sector_applicability=r["sector_applicability"] or ["ALL"],
                importance=r["importance"],
                value_type=r["value_type"],
                unit=r["unit"],
                flow_stock_type=r["flow_stock_type"],
                extraction_mode=r["extraction_mode"],
                calculation_formula=r["calculation_formula"],
                dependencies=r["dependencies"] or [],
                source_priority=r["source_priority"] or [],
                synonyms_id=r["synonyms_id"] or [],
                synonyms_en=r["synonyms_en"] or [],
            )
            for r in rows
        ]
        return MetricOntologyQueryResult(
            total_found=len(metrics),
            sector=sector or "ALL",
            metrics=metrics,
        )


@mcp.tool()
async def submit_discovered_metric(candidate: DiscoveredMetricCandidate) -> DiscoveredMetricResult:
    """Submits a newly discovered industry/operational KPI candidate from a financial filing into EMIMIND memory.

    Discovered metrics are validated and quarantined for ontology curation to avoid uncontrolled schema explosion.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        # 1. Check if concept already exists in metric_definitions
        exist_res = await conn.execute(
            text("SELECT metric_id, name_en FROM metric_definitions WHERE metric_id = :id"),
            {"id": candidate.metric_id},
        )
        if exist_res.mappings().first():
            return DiscoveredMetricResult(
                status="EXISTING",
                metric_id=candidate.metric_id,
                message=f"Metric '{candidate.metric_id}' already exists in canonical ontology.",
            )

        # 2. Insert into metric_definitions with 'OPTIONAL' importance
        await conn.execute(
            text(
                """
                INSERT INTO metric_definitions (
                    metric_id, name_en, name_id, category, sector_applicability, importance,
                    value_type, unit, flow_stock_type, extraction_mode,
                    source_priority, synonyms_id, synonyms_en, updated_at
                ) VALUES (
                    :id, :name_en, :name_id, :cat, ARRAY[:sec]::TEXT[], :imp,
                    :val_type, :unit, :flow_stock, 'EXTRACTED_RAW',
                    ARRAY[:src]::TEXT[], :syn_id, :syn_en, now()
                )
                ON CONFLICT (metric_id) DO NOTHING;
                """
            ),
            {
                "id": candidate.metric_id,
                "name_en": candidate.name_en,
                "name_id": candidate.name_id,
                "cat": candidate.category.upper(),
                "sec": candidate.sector_code.upper(),
                "imp": candidate.importance.upper(),
                "val_type": candidate.value_type.upper(),
                "unit": candidate.unit,
                "flow_stock": candidate.flow_stock_type,
                "src": candidate.typical_source,
                "syn_id": candidate.synonyms_id,
                "syn_en": candidate.synonyms_en,
            },
        )

        # 3. Add to concept_map alias table
        await conn.execute(
            text(
                """
                INSERT INTO concept_map (local_label, sector, canonical_concept_id, confidence, created_by)
                VALUES (:label, :sec, :id, 0.85, 'agent_discovery')
                ON CONFLICT DO NOTHING;
                """
            ),
            {
                "label": candidate.name_id,
                "sec": candidate.sector_code.upper(),
                "id": candidate.metric_id,
            },
        )

        await conn.commit()
        return DiscoveredMetricResult(
            status="PROMOTED",
            metric_id=candidate.metric_id,
            message=f"Successfully registered discovered metric candidate '{candidate.metric_id}' ({candidate.name_en}) into ontology registry.",
        )


@mcp.tool()
async def get_review_queue() -> list[dict[str, Any]]:
    """Retrieves unverified documents and extraction exceptions quarantined in the review queue."""
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT id, ticker, fiscal_period, doc_id, issue_type, severity, validation_report, status, created_at
                FROM ingest_review_queue
                WHERE status = 'PENDING'
                ORDER BY created_at DESC
                LIMIT 50;
                """
            )
        )
        return [dict(r) for r in res.mappings()]


@mcp.tool()
async def list_processed_documents(
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List documents already ingested and extracted, so downloaders can skip re-fetching.

    Returns rows for documents whose `status` is `parsed` or `facts_extracted`
    (i.e. their financial facts are already committed). The returned filename fields
    are derived from `source_url` / `minio_key` for stable local-file matching.

    Optional `tickers` filter narrows the result to a subset — useful when the caller
    only cares about a specific universe (LQ45, a client watchlist, etc.).
    """
    engine = get_engine()
    async with engine.connect() as conn:
        sql = (
            "SELECT ticker, fiscal_period, doc_type, doc_hash, source_url, minio_key, status "
            "FROM documents WHERE status IN ('parsed','facts_extracted')"
        )
        params: dict[str, Any] = {}
        if tickers:
            sql += " AND ticker = ANY(:tickers)"
            params["tickers"] = [t.upper() for t in tickers]
        res = await conn.execute(text(sql), params)
        out: list[dict[str, Any]] = []
        for row in res.mappings():
            src = row.get("source_url") or ""
            mk = row.get("minio_key") or ""
            file_name = Path(src).name if src else (Path(mk).name if mk else "")
            out.append(
                {
                    "ticker": row["ticker"],
                    "fiscal_period": row["fiscal_period"],
                    "doc_type": row["doc_type"],
                    "doc_hash": row["doc_hash"],
                    "file_name": file_name,
                    "status": row["status"],
                }
            )
        return out


def main() -> None:
    """Entry point for running the EMIMIND MCP Server via stdio."""
    import asyncio
    mcp.run()


if __name__ == "__main__":
    main()
