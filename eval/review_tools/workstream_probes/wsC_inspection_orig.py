"""Inspection and skip-management services for EMIMIND documents."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.mcp.periods import resolve_fiscal_period
from services.mcp.services.common import (
    _archive_processed_file,
    _log_processing_event,
    _read_sidecar_meta,
    get_engine,
)
from services.mcp.types import (
    DocumentInspectionResult,
    DocumentSkipResult,
    InspectionStatus,
)
from services.shared.logging import get_logger

log = get_logger("mcp.services.inspection")


async def inspect_document(
    file_path: str,
    ticker: str | None = None,
    fiscal_period: str | None = None,
    doc_type: str = "FS_QUARTERLY",
    *,
    engine: AsyncEngine | None = None,
    log_event_fn: Callable[..., Any] = _log_processing_event,
) -> DocumentInspectionResult:
    """Inspects a PDF document by computing its SHA-256 fingerprint and checking processing status in EMIMIND."""
    p = Path(file_path)
    if not p.is_absolute() and not p.exists():
        repo_root = Path(__file__).resolve().parents[3]
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
            candidates.extend(
                [
                    (repo_root / "incoming_reports" / ticker_prefix / base_name).resolve(),
                    (
                        repo_root / "incoming_reports" / ticker_prefix / "processed" / base_name
                    ).resolve(),
                    (Path.cwd() / "incoming_reports" / ticker_prefix / base_name).resolve(),
                    (
                        Path.cwd() / "incoming_reports" / ticker_prefix / "processed" / base_name
                    ).resolve(),
                ]
            )
        for cand in candidates:
            if cand.exists() and cand.is_file():
                p = cand
                break

    if not p.exists() or not p.is_file():
        # Best-effort log write for file-not-found; opens its own transaction.
        try:
            eng = engine or get_engine()
            async with eng.connect() as conn:
                await log_event_fn(
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

    eng = engine or get_engine()
    async with eng.connect() as conn:
        # Check if hash already exists in documents
        res = await conn.execute(
            text(
                "SELECT id, ticker, fiscal_period, doc_type, status FROM documents WHERE doc_hash = :hash"
            ),
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
                await log_event_fn(
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

                meta = await propose_metadata(p.read_bytes())
                if meta and meta.fiscal_period:
                    resolved_period = resolve_fiscal_period(p.name, meta.fiscal_period)
            except Exception as exc:
                log.warning("Metadata extractor fallback failed", error=str(exc))

        if not resolved_period:
            await log_event_fn(
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
        gate_res = await conn.execute(
            text("SELECT name, sector, sub_sector FROM issuer_profile WHERE ticker = :ticker"),
            {"ticker": t_clean},
        )
        gate_row = gate_res.mappings().first()
        if not gate_row or not gate_row.get("sector"):
            await log_event_fn(
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
                real_page_count = pymupdf.open(str(p)).page_count  # type: ignore[no-untyped-call]
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
            if sidecar_meta and (
                sidecar_meta.get("kind") == "announcement"
                or (sidecar_meta.get("doc_class_hint") or "").upper() != ""
            ):
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
                        "doc_class": (
                            sidecar_meta.get("doc_class_hint") or "GENERIC_DISCLOSURE"
                        ).upper(),
                        "src_url": sidecar_meta.get("source_url"),
                        "file_id": sidecar_meta.get("idx_file_id"),
                    },
                )
            await conn.commit()
        else:
            d_id = str(doc["id"])

        await log_event_fn(
            conn,
            action="INSPECTED_AUTHORIZED",
            source="inspect_document",
            file_name=p.name,
            ticker=t_clean,
            file_path=str(p),
            doc_hash=doc_hash,
            doc_id=d_id,
            reason=f"Document authorized for extraction (sector={sector_name}, doc_type={doc_type}).",
            metadata={
                "sector": sector_name,
                "sub_sector": gate_row.get("sub_sector"),
                "fiscal_period": fp_clean,
                "doc_type": doc_type,
            },
        )
        await conn.commit()

        # Enqueue page indexing worker for authorized document
        try:
            from services.shared.redis_client import enqueue_job, get_redis_pool

            r_pool = await get_redis_pool()
            try:
                await enqueue_job(r_pool, "index_pages_task", d_id)
            finally:
                await r_pool.aclose()
        except Exception as exc:
            log.warning("Failed to enqueue index_pages_task", doc_id=d_id, error=str(exc))

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


async def mark_document_skipped(
    doc_id: str,
    reason: str,
    notes: str | None = None,
    *,
    engine: AsyncEngine | None = None,
    log_event_fn: Callable[..., Any] = _log_processing_event,
) -> DocumentSkipResult:
    """Record that the extraction agent decided a document is not worth extracting."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        res = await conn.execute(
            text("SELECT ticker, source_url, doc_hash FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        row = res.mappings().first()
        if not row:
            raise ValueError(f"Document with ID {doc_id} not found in database.")

        await conn.execute(
            text("UPDATE documents SET status = 'skipped_by_llm' WHERE id = :id"),
            {"id": doc_id},
        )

        archived_to = _archive_processed_file(row["source_url"]) if row.get("source_url") else None
        if archived_to:
            await conn.execute(
                text("UPDATE documents SET source_url = :url WHERE id = :id"),
                {"url": archived_to, "id": doc_id},
            )

        await log_event_fn(
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
