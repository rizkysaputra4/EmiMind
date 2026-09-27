"""EMIMIND Model Context Protocol (MCP) Ingestion and Validation Server."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pymupdf
from mcp.server.mcpserver import MCPServer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from services.derive.engine import compute_for_document
from services.derive.valuation import calculate_valuation
from services.ingest.tasks.refresh_profile import refresh_profile_task
from services.mcp.contracts import (
    build_extraction_contract,
    get_route_query,
    load_page_router_queries,
)
from services.mcp.grounding import check_cell_grounding, resolve_scale
from services.mcp.periods import period_end_for, resolve_fiscal_period
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
    PageEvidence,
    PageTable,
    PageTableCell,
    RoutedPage,
    RoutedPages,
    ValidationReport,
)
from services.mcp.validator import CONCEPT_ALIASES, narrative_md5, validate_draft_submission
from services.retrieval.page_router import route_pages
from services.shared.config import get_settings
from services.shared.logging import get_logger
from services.shared.minio_client import get_minio

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


def get_engine() -> AsyncEngine:
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

                meta = await propose_metadata(p.read_bytes())
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
async def get_routed_pages(doc_id: str, module: str, top_k: int = 3) -> RoutedPages:
    """Return ranked page_index hits (+ expanded neighbours, text, image URL, and tables) for a contract module.

    Parameters:
      doc_id: UUID of the document returned by inspect_document.
      module: Module name from the contract (e.g. 'BALANCE_SHEET', 'INCOME_STATEMENT',
              'CASH_FLOW', 'MDA', 'BANK_LOANS_NPL', 'PLANTATION_AREA', 'CASH_BANKS',
              'REVENUE_CUSTOMERS', 'COGS_BREAKDOWN', 'DEBT_FACILITIES').
      top_k:  Number of seed pages to rank and expand (default: 3).
    """
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, ticker, fiscal_period, doc_type, minio_key, doc_hash FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document with ID {doc_id} not found in database.")

        ticker = doc["ticker"]
        prof_res = await conn.execute(
            text("SELECT sector FROM issuer_profile WHERE ticker = :ticker"),
            {"ticker": ticker},
        )
        prof_row = prof_res.mappings().first()
        sector = prof_row["sector"] if prof_row and prof_row.get("sector") else "GENERIC"

        route_query = get_route_query(module.upper(), sector)
        if not route_query:
            valid_modules = sorted(load_page_router_queries().keys())
            raise ValueError(
                f"Unknown module '{module}'. Valid modules are: {', '.join(valid_modules)}"
            )

        routed_spans = await route_pages(conn, str(doc_id), route_query, top_k=top_k)

        # Unique page numbers across all spans
        page_score_map: dict[int, float] = {}
        for s in routed_spans:
            for p in s.pages:
                if p not in page_score_map or s.score > page_score_map[p]:
                    page_score_map[p] = s.score

        unique_pages = sorted(page_score_map.keys())

        if not unique_pages:
            return RoutedPages(
                doc_id=str(doc_id),
                module=module.upper(),
                total_pages_returned=0,
                pages=[],
                spans=[s.pages for s in routed_spans],
            )

        # Fetch page text and metadata
        pages_res = await conn.execute(
            text(
                """
                SELECT page_index, page_label, text_source, page_text, image_key
                FROM document_pages
                WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                ORDER BY page_index ASC
                """
            ),
            {"doc_id": doc_id, "pages": unique_pages},
        )
        page_records = {int(r["page_index"]): dict(r) for r in pages_res.mappings().all()}

        # Fetch page table grids
        tables_res = await conn.execute(
            text(
                """
                SELECT page_index, table_index, extraction_method, confidence, unit_hint, cells
                FROM document_page_tables
                WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                ORDER BY page_index ASC, table_index ASC
                """
            ),
            {"doc_id": doc_id, "pages": unique_pages},
        )
        tables_by_page: dict[int, list[PageTable]] = {}
        for tr in tables_res.mappings().all():
            p_idx = int(tr["page_index"])
            raw_cells = tr["cells"] if isinstance(tr["cells"], list) else json.loads(tr["cells"])
            cells_objs = [
                PageTableCell(
                    row=int(c.get("row", 0)),
                    col=int(c.get("col", 0)),
                    text=str(c.get("text", "")),
                    value=float(c["value"]) if c.get("value") is not None else None,
                    bbox=c.get("bbox"),
                    confidence=float(c["confidence"]) if c.get("confidence") is not None else None,
                )
                for c in raw_cells
            ]
            tbl = PageTable(
                table_index=int(tr["table_index"]),
                extraction_method=str(tr["extraction_method"]),
                confidence=float(tr["confidence"]),
                unit_hint=tr.get("unit_hint"),
                cells=cells_objs,
            )
            tables_by_page.setdefault(p_idx, []).append(tbl)

        # MinIO Presigned URLs for thumbnails
        settings = get_settings()
        page_image_urls: dict[int, str | None] = {}
        try:
            minio_client = get_minio(settings)
            for p_idx in unique_pages:
                prec = page_records.get(p_idx, {})
                img_key = prec.get("image_key")
                if img_key:
                    try:
                        url = minio_client.presigned_get_object(
                            settings.minio_bucket_raw, img_key, expires=timedelta(hours=1)
                        )
                        page_image_urls[p_idx] = url
                    except Exception:
                        page_image_urls[p_idx] = None
        except Exception:
            pass

        # Log event
        file_name = Path(doc.get("minio_key") or "").name or f"{ticker}_{doc_id}.pdf"
        await _log_processing_event(
            conn,
            action="ROUTED",
            source="get_routed_pages",
            file_name=file_name,
            ticker=ticker,
            doc_id=str(doc_id),
            doc_hash=doc.get("doc_hash"),
            metadata={
                "module": module.upper(),
                "pages": unique_pages,
                "span_count": len(routed_spans),
            },
        )
        await conn.commit()

        routed_pages_list: list[RoutedPage] = []
        for p_idx in unique_pages:
            prec = page_records.get(p_idx, {})
            routed_pages_list.append(
                RoutedPage(
                    page_index=p_idx,
                    page_label=prec.get("page_label"),
                    text_source=prec.get("text_source", "pdf_text"),
                    score=page_score_map.get(p_idx, 0.0),
                    page_text=prec.get("page_text", ""),
                    image_url=page_image_urls.get(p_idx),
                    tables=tables_by_page.get(p_idx, []),
                )
            )

        return RoutedPages(
            doc_id=str(doc_id),
            module=module.upper(),
            total_pages_returned=len(routed_pages_list),
            pages=routed_pages_list,
            spans=[s.pages for s in routed_spans],
        )


async def _load_cross_issuer_narrative_hashes(conn: Any, ticker: str) -> dict[str, str]:
    """Loads MD5 hashes of committed narrative chunks for issuers other than ticker."""
    cross_hashes: dict[str, str] = {}
    try:
        narr_res = await conn.execute(
            text("SELECT ticker, text_original FROM narrative_chunks WHERE ticker != :ticker LIMIT 5000"),
            {"ticker": ticker.upper()},
        )
        for nr in narr_res.mappings().all():
            nh = narrative_md5(nr["text_original"])
            cross_hashes[nh] = nr["ticker"]
    except Exception as e:
        log.warning("Failed to load cross-issuer narrative hashes: %s", e)
    return cross_hashes


@mcp.tool()
async def submit_draft_extraction(
    payload_json: str,
    retry_attempt: int = 1,
    usage: dict[str, Any] | None = None,
) -> ValidationReport:
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

    effective_usage: dict[str, Any] | None = usage
    if effective_usage is None and payload.usage is not None:
        effective_usage = (
            payload.usage.model_dump(exclude_none=True)
            if hasattr(payload.usage, "model_dump")
            else dict(payload.usage)
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

        doc_page_count: int | None = None
        try:
            dt_res = await conn.execute(
                text("SELECT doc_type, page_count FROM documents WHERE id = :id"),
                {"id": payload.doc_id},
            )
            dt_row = dt_res.mappings().first()
            if dt_row:
                doc_type_val = dt_row["doc_type"]
                doc_page_count = dt_row.get("page_count")
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

        # Load evidence for every cited source_page
        cited_pages: set[int] = set()
        for f in payload.facts:
            if f.source_page is not None:
                cited_pages.add(f.source_page)
        for n in payload.narratives:
            cited_pages.add(n.source_page)
        for c in payload.causal_links:
            cited_pages.add(c.source_page)
        for g in payload.guidance:
            cited_pages.add(g.source_page)

        evidence: dict[int, PageEvidence] | None = None
        try:
            has_pages_res = await conn.execute(
                text("SELECT 1 FROM document_pages WHERE doc_id = :doc_id LIMIT 1"),
                {"doc_id": payload.doc_id},
            )
            if has_pages_res.first():
                evidence = {}
                if cited_pages:
                    pages_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, text_source, page_text
                            FROM document_pages
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            """
                        ),
                        {"doc_id": payload.doc_id, "pages": list(cited_pages)},
                    )
                    tables_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, table_index, extraction_method, confidence, unit_hint, cells
                            FROM document_page_tables
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            ORDER BY page_index, table_index
                            """
                        ),
                        {"doc_id": payload.doc_id, "pages": list(cited_pages)},
                    )
                    tables_by_page: dict[int, list[PageTable]] = {}
                    for tr in tables_res.mappings().all():
                        p_idx = tr["page_index"]
                        raw_cells = tr["cells"]
                        if isinstance(raw_cells, str):
                            raw_cells = json.loads(raw_cells)
                        cell_objs = [PageTableCell.model_validate(c) for c in (raw_cells or [])]
                        pt = PageTable(
                            table_index=tr["table_index"],
                            extraction_method=tr.get("extraction_method") or "pdfplumber",
                            confidence=float(tr.get("confidence") or 1.0),
                            unit_hint=tr.get("unit_hint"),
                            cells=cell_objs,
                        )
                        tables_by_page.setdefault(p_idx, []).append(pt)

                    for pr in pages_res.mappings().all():
                        p_idx = pr["page_index"]
                        evidence[p_idx] = PageEvidence(
                            page_index=p_idx,
                            text_source=pr["text_source"] or "pdf_text",
                            page_text=pr["page_text"] or "",
                            tables=tables_by_page.get(p_idx, []),
                        )
        except Exception as e:
            log.warning("Failed to load page evidence for doc %s: %s", payload.doc_id, e)
            evidence = None

        cross_issuer_hashes: dict[str, str] | None = None
        if payload.narratives:
            cross_issuer_hashes = await _load_cross_issuer_narrative_hashes(conn, payload.ticker)

    report = validate_draft_submission(
        payload,
        contract=contract,
        sector=sector,
        evidence=evidence,
        page_count=doc_page_count,
        cross_issuer_narrative_hashes=cross_issuer_hashes,
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
            err_meta = {"status": report.status, "retry_attempt": retry_attempt}
            if effective_usage:
                err_meta.update(effective_usage)
            await _log_processing_event(
                conn,
                action="ERROR",
                source="submit_draft_extraction",
                file_name="",
                ticker=payload.ticker.upper(),
                doc_id=payload.doc_id,
                reason=f"Validation failed after {retry_attempt} retries; sent to review queue.",
                metadata=err_meta,
            )
            await conn.commit()
    else:
        # Log every draft submission attempt (success or validation feedback)
        # so the operator can see per-file extraction history.
        try:
            extracted_meta = {
                "status": report.status,
                "retry_attempt": retry_attempt,
                "facts_count": len(payload.facts),
            }
            if effective_usage:
                extracted_meta.update(effective_usage)
            async with engine.connect() as conn:
                await _log_processing_event(
                    conn,
                    action="EXTRACTED",
                    source="submit_draft_extraction",
                    file_name="",
                    ticker=payload.ticker.upper(),
                    doc_id=payload.doc_id,
                    reason=f"Draft submitted (validation={report.status}, attempt={retry_attempt}).",
                    metadata=extracted_meta,
                )
                await conn.commit()
        except Exception as exc:
            log.warning("Failed to log EXTRACTED event", error=str(exc))

    return report


@mcp.tool()
async def commit_verified_report(
    payload_json: str,
    usage: dict[str, Any] | None = None,
) -> CommitReport:
    """Commits verified financial facts, narrative chunks, and guidance to the database and runs the derive engine."""
    data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    payload = DraftSubmissionPayload.model_validate(data)

    effective_usage: dict[str, Any] | None = usage
    if effective_usage is None and payload.usage is not None:
        effective_usage = (
            payload.usage.model_dump(exclude_none=True)
            if hasattr(payload.usage, "model_dump")
            else dict(payload.usage)
        )

    engine = get_engine()
    doc_id = payload.doc_id
    ticker = payload.ticker.upper()
    fiscal_period = payload.fiscal_period.upper()

    try:
        period_end_dt = period_end_for(fiscal_period)
        _ = int(fiscal_period[:4])
    except ValueError as err:
        return CommitReport(
            status="ERROR",
            doc_id=doc_id,
            ticker=ticker,
            fiscal_period=fiscal_period,
            facts_committed=0,
            narratives_committed=0,
            guidance_committed=0,
            omissions_recorded=0,
            derived_metrics_computed=0,
            profile_refreshed=False,
            live_valuation_computed=False,
            message=f"Invalid fiscal period '{fiscal_period}': {err}",
        )

    async with engine.connect() as conn:
        # Resolve company context and document metadata
        sector = "GENERIC"
        company_name = f"PT {ticker} Tbk"
        sec_res = await conn.execute(
            text("SELECT name, sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
            {"ticker": ticker},
        )
        sec_row = sec_res.mappings().first()
        if sec_row:
            sector = sec_row.get("sector") or "GENERIC"
            if sec_row.get("name"):
                company_name = sec_row["name"]

        doc_type_val = None
        doc_page_count = None
        try:
            dt_res = await conn.execute(
                text("SELECT doc_type, page_count FROM documents WHERE id = :id"),
                {"id": doc_id},
            )
            dt_row = dt_res.mappings().first()
            if dt_row:
                doc_type_val = dt_row.get("doc_type")
                doc_page_count = dt_row.get("page_count")
        except Exception:
            pass

        contract = await build_extraction_contract(
            conn,
            doc_id=doc_id,
            ticker=ticker,
            company_name=company_name,
            sector=sector,
            fiscal_period=fiscal_period,
            doc_type=doc_type_val,
        )

        # Load evidence for every cited source_page
        cited_pages: set[int] = set()
        for f in payload.facts:
            if f.source_page is not None:
                cited_pages.add(f.source_page)
        for n in payload.narratives:
            cited_pages.add(n.source_page)
        for c in payload.causal_links:
            cited_pages.add(c.source_page)
        for g in payload.guidance:
            cited_pages.add(g.source_page)

        evidence: dict[int, PageEvidence] | None = None
        try:
            has_pages_res = await conn.execute(
                text("SELECT 1 FROM document_pages WHERE doc_id = :doc_id LIMIT 1"),
                {"doc_id": doc_id},
            )
            if has_pages_res.first():
                evidence = {}
                if cited_pages:
                    pages_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, text_source, page_text
                            FROM document_pages
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            """
                        ),
                        {"doc_id": doc_id, "pages": list(cited_pages)},
                    )
                    tables_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, table_index, extraction_method, confidence, unit_hint, cells
                            FROM document_page_tables
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            ORDER BY page_index, table_index
                            """
                        ),
                        {"doc_id": doc_id, "pages": list(cited_pages)},
                    )
                    tables_by_page: dict[int, list[PageTable]] = {}
                    for tr in tables_res.mappings().all():
                        p_idx = tr["page_index"]
                        raw_cells = tr["cells"]
                        if isinstance(raw_cells, str):
                            raw_cells = json.loads(raw_cells)
                        cell_objs = [PageTableCell.model_validate(c) for c in (raw_cells or [])]
                        pt = PageTable(
                            table_index=tr["table_index"],
                            extraction_method=tr.get("extraction_method") or "pdfplumber",
                            confidence=float(tr.get("confidence") or 1.0),
                            unit_hint=tr.get("unit_hint"),
                            cells=cell_objs,
                        )
                        tables_by_page.setdefault(p_idx, []).append(pt)

                    for pr in pages_res.mappings().all():
                        p_idx = pr["page_index"]
                        evidence[p_idx] = PageEvidence(
                            page_index=p_idx,
                            text_source=pr["text_source"] or "pdf_text",
                            page_text=pr["page_text"] or "",
                            tables=tables_by_page.get(p_idx, []),
                        )
        except Exception as e:
            log.warning("Failed to load page evidence for doc %s in commit: %s", doc_id, e)
            evidence = None

        cross_issuer_hashes: dict[str, str] | None = None
        if payload.narratives:
            cross_issuer_hashes = await _load_cross_issuer_narrative_hashes(conn, ticker)

        # Re-run validation with evidence at commit time; never trust the draft blindly
        val_rep = validate_draft_submission(
            payload,
            contract=contract,
            sector=sector,
            evidence=evidence,
            page_count=doc_page_count,
            cross_issuer_narrative_hashes=cross_issuer_hashes,
        )
        if val_rep.status != "VALID":
            err_msg = val_rep.issues[0].feedback_message if val_rep.issues else "Validation failed"
            return CommitReport(
                status="REJECTED_VALIDATION_FAILED",
                doc_id=doc_id,
                ticker=ticker,
                fiscal_period=fiscal_period,
                facts_committed=0,
                narratives_committed=0,
                guidance_committed=0,
                omissions_recorded=0,
                derived_metrics_computed=0,
                profile_refreshed=False,
                live_valuation_computed=False,
                message=f"Commit rejected: validation failed ({err_msg})",
            )

        # Look up metric_definitions.flow_stock_type for all fact concepts
        cids = list({f.concept_id for f in payload.facts})
        norm_map = {cid: CONCEPT_ALIASES.get(cid.lower(), cid) for cid in cids}
        all_query_ids = list(set(cids) | set(norm_map.values()))
        flow_stock_map: dict[str, str] = {}
        if all_query_ids:
            try:
                res = await conn.execute(
                    text("SELECT metric_id, flow_stock_type FROM metric_definitions WHERE metric_id = ANY(:cids)"),
                    {"cids": all_query_ids},
                )
                db_flows = {row[0]: row[1] for row in res.fetchall()}
                for cid in cids:
                    norm = norm_map.get(cid, cid)
                    if cid in db_flows:
                        flow_stock_map[cid] = db_flows[cid]
                    elif norm in db_flows:
                        flow_stock_map[cid] = db_flows[norm]
            except Exception:
                pass

        # 1. Insert/update financial_facts
        default_contract_scale = resolve_scale(None, getattr(contract, "scaling_rules", None))
        facts_count = 0
        for f in payload.facts:
            cid = f.concept_id
            stmt_type = f.statement or "NOTE"

            # Determine period_type
            flow_stock = flow_stock_map.get(cid)
            if flow_stock and flow_stock.startswith("STOCK"):
                p_type = "instant"
            elif flow_stock and flow_stock.startswith("FLOW"):
                p_type = "duration_ytd"
            elif f.period_type:
                p_type = f.period_type
            else:
                p_type = "duration_ytd" if stmt_type in ("IS", "CF") else "instant"

            if p_type == "duration_q":
                p_type = "duration_qtd"
            elif p_type not in ("instant", "duration_qtd", "duration_ytd"):
                p_type = "duration_ytd" if stmt_type in ("IS", "CF") else "instant"

            seg_dict = f.segment

            # Determine grounding result
            method = "llm_extract"
            conf = 0.75
            needs_review = False
            source_bbox_val = f.bbox

            if evidence is not None and f.source_page in evidence:
                page_ev = evidence[f.source_page]
                if page_ev.text_source == "ocr":
                    method = "llm_extract"
                    conf = 0.65
                    needs_review = True
                elif f.cell_ref is not None:
                    is_grounded, _err, cell_conf, cell_bbox = check_cell_grounding(
                        f, page_ev, default_scale=default_contract_scale
                    )
                    if is_grounded:
                        method = "table_parser"
                        conf = round(cell_conf if cell_conf is not None else 0.95, 2)
                        source_bbox_val = cell_bbox or f.bbox
                        needs_review = False
                    else:
                        method = "llm_extract"
                        conf = 0.75
                        needs_review = False
                else:
                    method = "llm_extract"
                    conf = 0.75
                    needs_review = False

            source_bbox_json = json.dumps(source_bbox_val) if source_bbox_val else None

            await conn.execute(
                text(
                    """
                    INSERT INTO financial_facts (
                        source_doc_id, ticker, period_end, fiscal_period, statement, concept_id, concept_local,
                        value_numeric, unit, segment, period_type, accounting_std, source_page, source_bbox,
                        extraction_conf, extraction_method, needs_review
                    ) VALUES (
                        :doc_id, :ticker, :period_end, :period, :statement, :concept_id, :label,
                        :val, :unit, CAST(:seg AS jsonb), :period_type, :std, :page, CAST(:source_bbox AS jsonb),
                        :conf, :method, :needs_review
                    )
                    ON CONFLICT (ticker, fiscal_period, concept_id, (coalesce(segment, '{}'::jsonb)))
                    WHERE is_restated = false
                    DO UPDATE SET
                        value_numeric = EXCLUDED.value_numeric,
                        unit = EXCLUDED.unit,
                        segment = EXCLUDED.segment,
                        statement = EXCLUDED.statement,
                        period_type = EXCLUDED.period_type,
                        source_page = EXCLUDED.source_page,
                        source_bbox = EXCLUDED.source_bbox,
                        source_doc_id = EXCLUDED.source_doc_id,
                        extraction_method = EXCLUDED.extraction_method,
                        extraction_conf = EXCLUDED.extraction_conf,
                        needs_review = EXCLUDED.needs_review;
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
                    "source_bbox": source_bbox_json,
                    "conf": conf,
                    "method": method,
                    "needs_review": needs_review,
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

                        pdf_doc = pymupdf.open(str(cand))  # type: ignore[no-untyped-call]
                        pdf_pages = []
                        for i in range(len(pdf_doc)):
                            pg = pdf_doc[i]
                            txt = pg.get_text("text")  # type: ignore[no-untyped-call]
                            pdf_pages.append(PageContent(page_num=i + 1, text=txt, language="mixed", has_text_layer=True))
                        pdf_doc.close()  # type: ignore[no-untyped-call]

                        auto_chunks = chunk_pages(pdf_pages, ticker, "FS_ANNUAL", fiscal_period)
                        for chunk in auto_chunks:
                            sec = chunk.section if chunk.section in valid_sections else "OTHER"
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
                                    "page": chunk.source_page,
                                    "lang": chunk.language,
                                    "orig": chunk.text_original,
                                    "en": chunk.text_en or chunk.text_original,
                                    "speaker": chunk.speaker,
                                    "claim": chunk.claim_type,
                                    "concepts": chunk.mentioned_concepts or [],
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

        meta_committed: dict[str, Any] = {
            "facts_committed": facts_count,
            "narratives_committed": narratives_count,
            "guidance_committed": len(payload.guidance),
            "omissions_recorded": omissions_count,
            "derived_metrics_computed": compute_rep.computed,
            "profile_refreshed": profile_refreshed,
            "live_valuation_computed": live_val_ok,
        }
        if effective_usage:
            meta_committed.update(effective_usage)

        await _log_processing_event(
            conn,
            action="COMMITTED",
            source="commit_verified_report",
            file_name="",
            ticker=ticker,
            doc_id=doc_id,
            reason=f"Committed {facts_count} facts, {narratives_count} narratives, {len(payload.guidance)} guidance items. Derived {compute_rep.computed} metrics.",
            metadata=meta_committed,
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
    mcp.run()


if __name__ == "__main__":
    main()
