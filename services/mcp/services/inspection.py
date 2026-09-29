"""Inspection and skip-management services for EMIMIND documents."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.extraction.metadata_extractor import propose_metadata_from_text
from services.mcp.periods import (
    ResolvedPeriod,
    normalize_period,
    period_end_for,
    resolve_fiscal_period,
    resolve_period_from_text,
)
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

COVER_PAGES = 3
SHORT_DOC_MAX_PAGES = 3
# Letters bundled in front of a full statement are kept; only short letter files are skipped.
LETTER_MAX_PAGES = 10

_NOT_FS_NAME = [
    ("checklist", re.compile(r"c\s*h?\s*e\s*c?\s*k\s*l\s*i\s*s\s*t|ceklis", re.I)),
    (
        "esg_sustainability",
        re.compile(r"(?<![a-z])esg|sustainab|keberlanjutan|berkelanjutan", re.I),
    ),
    ("public_expose", re.compile(r"public\s*expos|pubex|paparan\s*publik", re.I)),
]
_LETTER_NAME = [
    ("cover_letter", re.compile(r"pengantar", re.I)),
    ("directors_statement", re.compile(r"pernyataan\s*direksi|surat\s*pernyataan", re.I)),
    (
        "directors_statement",
        re.compile(r"(?<![a-z])(spd|(dir(ectors?)?|bod)'?s?\s*statement)(?![a-z])", re.I),
    ),
    ("explanation_letter", re.compile(r"penjelasan", re.I)),
    (
        # condensed statements published in newspapers ("Bukti Iklan", "Iklan Investor Daily")
        "newspaper_publication",
        re.compile(
            r"(?<![a-z])(iklan|koran|surat\s*kabar|e\s*-?\s*paper)(?![a-z])|investor\s*daily"
            r"|media\s*indonesia|bisnis\s*indonesia|(?<![a-z])kontan(?![a-z])"
            r"|(news|press)\s*release|siaran\s*pers",
            re.I,
        ),
    ),
    (
        "change_over_20_percent",
        re.compile(
            r"perubahan.{0,40}(20\s*(persen|%)|lebih\s+dari)"
            r"|perubahan\s+(total\s+|jumlah\s+)?(aset|aktiva|liabilitas|kewajiban)",
            re.I,
        ),
    ),
]
_FS_CONTENT = re.compile(
    r"posisi\s+keuangan|financial\s+position|neraca|laba\s*[/\s-]?\s*rugi|profit\s+or\s+loss"
    r"|balance\s+sheet|income\s+statement|comprehensive\s+income|penghasilan\s+komprehensif",
    re.I,
)
_DOC_TYPES = {"PUBEX", "FS_QUARTERLY", "FS_ANNUAL", "ANNUAL_REPORT"}
_PREFIX = re.compile(r"^[A-Za-z0-9]+_\d{4}_(TW1|TW2|TW3|AUDIT|ANNUAL)_([A-Za-z0-9]+)_", re.I)
_ANNUAL_REPORT_NAME = re.compile(r"annual\s*report|laporan\s*tahunan", re.I)


@dataclass(frozen=True)
class PdfFacts:
    page_count: int
    cover_text: str


def read_pdf_facts(path: Path, cover_pages: int = COVER_PAGES) -> PdfFacts | None:
    """Real page count plus the text of the first pages; None when the PDF is unreadable."""
    try:
        with pymupdf.open(str(path)) as pdf:  # type: ignore[no-untyped-call]
            count = int(pdf.page_count)
            cover = "\n".join(str(pdf[i].get_text()) for i in range(min(cover_pages, count)))
    except Exception as exc:
        log.warning("PDF could not be opened", path=str(path), error=str(exc))
        return None
    return PdfFacts(page_count=count, cover_text=cover) if count >= 1 else None


def classify_administrative(filename: str, facts: PdfFacts | None) -> str | None:
    """Returns a skip reason for non-financial/administrative filings, else None."""
    name = re.sub(r"[_\-.]+", " ", Path(filename).stem)
    m = _PREFIX.match(Path(filename).name)
    title = re.sub(r"[_\-.]+", " ", Path(filename).name[m.end() :]) if m else name
    for reason, rx in _NOT_FS_NAME:
        if rx.search(title):
            return f"filename:{reason}"
    for reason, rx in _LETTER_NAME:
        if rx.search(title) and (facts is None or facts.page_count <= LETTER_MAX_PAGES):
            return f"filename:{reason}"
    if (
        facts is not None
        and facts.page_count <= SHORT_DOC_MAX_PAGES
        and not _FS_CONTENT.search(facts.cover_text)
    ):
        return "content:short_document_without_financial_statement"
    return None


def is_announcement(path: Path, sidecar_meta: dict[str, Any] | None) -> bool:
    """Announcement domain: downloader sidecar says so, or the file sits under announcements/."""
    if sidecar_meta and str(sidecar_meta.get("kind") or "").lower() == "announcement":
        return True
    return any(part.lower() == "announcements" for part in path.parts[:-1])


def infer_doc_type(
    filename: str,
    fiscal_period: str,
    content_doc_type: str | None,
    *,
    period_from_prefix: bool = True,
) -> str:
    """Infers documents.doc_type for periodic filings (the announcement domain is decided first).

    Domain token of the downloader prefix first: `ANNUAL_AAR` -> ANNUAL_REPORT; for `_RDF_`
    filings an "Annual Report" title is still an ANNUAL_REPORT, `AUDIT` -> FS_ANNUAL and
    `TW1..TW3` -> FS_QUARTERLY. Without a prefix: title, then cover-page content, then period.
    """
    base = Path(filename).name
    m = _PREFIX.match(base)
    title = base[m.end() :] if m else base
    if m:
        period_tok, kind = m.group(1).upper(), m.group(2).upper()
        if kind == "AAR" or period_tok == "ANNUAL" or _ANNUAL_REPORT_NAME.search(title):
            return "ANNUAL_REPORT"
        if period_from_prefix:
            return "FS_ANNUAL" if period_tok == "AUDIT" else "FS_QUARTERLY"
        # the prefix period was overridden (cover page / agent): the real period decides
        return "FS_ANNUAL" if fiscal_period.endswith("Q4") else "FS_QUARTERLY"
    if _ANNUAL_REPORT_NAME.search(title):
        return "ANNUAL_REPORT"
    if content_doc_type in _DOC_TYPES:
        return str(content_doc_type)
    return "FS_ANNUAL" if fiscal_period.endswith("Q4") else "FS_QUARTERLY"


def _period_from_cover(cover_text: str) -> ResolvedPeriod | None:
    res = resolve_period_from_text(cover_text)
    if res:
        return res
    raw = propose_metadata_from_text(cover_text).fiscal_period if cover_text.strip() else None
    if not raw:
        return None
    try:
        fp = normalize_period(raw)
    except ValueError:
        return None
    return ResolvedPeriod(fiscal_period=fp, period_end=period_end_for(fp), source="cover_page")


def _resolve_local_path(file_path: str) -> Path:
    p = Path(file_path)
    if p.is_absolute() or p.exists():
        return p
    repo_root = Path(__file__).resolve().parents[3]
    base_name = p.name
    # `{TICKER}` prefix in downloader filenames → also probe the per-ticker subfolder.
    ticker_prefix = base_name.split("_", 1)[0].upper() if "_" in base_name else None
    roots = [repo_root, Path.cwd()]
    rel = ["incoming_reports", "incoming_reports/processed"]
    if ticker_prefix:
        rel += [f"incoming_reports/{ticker_prefix}", f"incoming_reports/{ticker_prefix}/processed"]
    candidates = [(r / file_path).resolve() for r in roots]
    candidates += [(r / sub / base_name).resolve() for r in roots for sub in rel]
    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand
    return p


async def _default_enqueue(doc_id: str) -> None:
    from services.shared.redis_client import enqueue_job, get_redis_pool

    r_pool = await get_redis_pool()
    try:
        await enqueue_job(r_pool, "index_pages_task", doc_id)
    finally:
        await r_pool.aclose()


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


async def inspect_document(
    file_path: str,
    ticker: str | None = None,
    fiscal_period: str | None = None,
    doc_type: str | None = None,
    *,
    engine: AsyncEngine | None = None,
    log_event_fn: Callable[..., Any] = _log_processing_event,
    enqueue_fn: Callable[[str], Awaitable[None]] | None = None,
) -> DocumentInspectionResult:
    """Inspects a PDF: fingerprint, dedupe, administrative triage, period and page-count metadata."""
    p = _resolve_local_path(file_path)

    if not p.exists() or not p.is_file():
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

    doc_hash = _sha256(p)

    # Sidecar (downloader .meta.json): doc_class_hint and ticker only. The announcement date
    # is a publication date, not a fiscal period, so it is never used as a period hint.
    sidecar_meta = _read_sidecar_meta(p)
    sidecar_doc_type: str | None = None
    if sidecar_meta:
        sidecar_doc_type = (sidecar_meta.get("doc_class_hint") or "").upper() or None
        if not ticker and sidecar_meta.get("ticker"):
            ticker = str(sidecar_meta["ticker"]).upper()

    eng = engine or get_engine()
    async with eng.connect() as conn:
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
            f_res = await conn.execute(
                text("SELECT count(*) FROM financial_facts WHERE source_doc_id = :d_id"),
                {"d_id": d_id},
            )
            facts_count = f_res.scalar() or 0

            if facts_count > 0 and doc["status"] in ("parsed", "facts_extracted"):
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

        t_clean = (ticker or (p.stem.split("_")[0] if "_" in p.stem else "UNKNOWN")).upper()
        t_log = t_clean if t_clean != "UNKNOWN" else None
        facts = read_pdf_facts(p)

        # ---- DOMAIN FIRST: announcements are 1-10 page disclosures, not statements, so the
        # financial-statement triage below must not skip them.
        announcement = is_announcement(p, sidecar_meta)

        # ---- ADMINISTRATIVE TRIAGE (deterministic: filename + first-pages keywords) ----
        admin_reason = None if announcement else classify_administrative(p.name, facts)
        if admin_reason:
            await log_event_fn(
                conn,
                action="SKIPPED_ADMINISTRATIVE",
                source="inspect_document",
                file_name=p.name,
                ticker=t_log,
                file_path=str(p),
                doc_hash=doc_hash,
                reason=f"Administrative / non-financial filing ({admin_reason}).",
                metadata={
                    "rule": admin_reason,
                    "page_count": facts.page_count if facts else None,
                },
            )
            await conn.commit()
            return DocumentInspectionResult(
                status=InspectionStatus.SKIPPED_ADMINISTRATIVE,
                doc_hash=doc_hash,
                ticker=t_log,
                message=(
                    f"Skipped: administrative or non-financial filing ({admin_reason}). "
                    "Not registered for extraction. Move on to the next file."
                ),
            )

        # ---- PERIOD (hint > downloader prefix > filename tokens; cover page on conflict) ----
        needs_reason: str | None = None
        period_meta: dict[str, Any] = {}
        try:
            resolved = resolve_fiscal_period(p.name, fiscal_period)
        except ValueError as exc:
            resolved = None
            needs_reason = f"Invalid fiscal_period {fiscal_period!r}: {exc}. Use YYYYQ1..YYYYQ4."

        cover_text = facts.cover_text if facts else ""
        if resolved and resolved.conflict:
            period_meta = {
                "filename_period": resolved.fiscal_period,
                "conflicting_period": resolved.conflicting_period,
            }
            cover = _period_from_cover(cover_text)
            if cover:
                period_meta["cover_period"] = cover.fiscal_period
                resolved = cover
            else:
                resolved = None
                needs_reason = (
                    f"Filename prefix says {period_meta['filename_period']} but the title says "
                    f"{period_meta['conflicting_period']}, and the cover page does not resolve it."
                )
        elif resolved is None and needs_reason is None:
            resolved = _period_from_cover(cover_text)

        if not resolved:
            reason = needs_reason or (
                "Cannot resolve fiscal period from filename or cover page; "
                "fiscal_period required from agent."
            )
            await log_event_fn(
                conn,
                action="NEEDS_METADATA",
                source="inspect_document",
                file_name=p.name,
                ticker=t_log,
                file_path=str(p),
                doc_hash=doc_hash,
                reason=reason,
                metadata=period_meta,
            )
            await conn.commit()
            return DocumentInspectionResult(
                status=InspectionStatus.NEEDS_METADATA,
                doc_hash=doc_hash,
                ticker=t_log,
                fiscal_period=None,
                doc_type=doc_type,
                message=(
                    f"{reason} Please call inspect_document again passing fiscal_period "
                    "explicitly (e.g. '2025Q2') after checking the cover page."
                ),
            )

        if facts is None:
            await log_event_fn(
                conn,
                action="ERROR",
                source="inspect_document",
                file_name=p.name,
                ticker=t_log,
                file_path=str(p),
                doc_hash=doc_hash,
                reason="PDF could not be opened; page count unknown.",
            )
            await conn.commit()
            return DocumentInspectionResult(
                status=InspectionStatus.ERROR,
                doc_hash=doc_hash,
                ticker=t_log,
                fiscal_period=resolved.fiscal_period,
                message="PDF could not be opened (corrupt or encrypted); page count unknown. Not registered.",
            )

        fp_clean = resolved.fiscal_period
        period_end_dt = resolved.period_end
        if doc_type:
            doc_type_source = "argument"
        elif sidecar_doc_type:
            doc_type, doc_type_source = sidecar_doc_type, "sidecar"
        elif announcement:
            doc_type, doc_type_source = "GENERIC_DISCLOSURE", "announcement_default"
        else:
            content_type = propose_metadata_from_text(cover_text).doc_type if cover_text else None
            prefix = resolve_fiscal_period(p.name)
            from_prefix = bool(prefix and prefix.fiscal_period == fp_clean)
            doc_type = infer_doc_type(p.name, fp_clean, content_type, period_from_prefix=from_prefix)
            doc_type_source = "inferred"

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

        if not doc:
            d_id = str(uuid.uuid4())
            minio_key = f"raw/{doc_type}/{t_clean}/{fp_clean}/{p.name}"
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
                    "page_count": facts.page_count,
                },
            )
            if sidecar_meta and (
                sidecar_meta.get("kind") == "announcement" or sidecar_doc_type is not None
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
                        "doc_class": (sidecar_doc_type or "GENERIC_DISCLOSURE"),
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
                "period_source": resolved.source,
                "doc_type": doc_type,
                "doc_type_source": doc_type_source,
                "page_count": facts.page_count,
                **period_meta,
            },
        )
        await conn.commit()

    try:
        await (enqueue_fn or _default_enqueue)(d_id)
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
            f"Document authorized for extraction ({doc_type}, {fp_clean}, "
            f"{facts.page_count} pages, period from {resolved.source}). Next: call "
            "get_extraction_contract(doc_id), then get_routed_pages(doc_id, module) per module. "
            "If the routed pages show this is not a financial filing, call "
            "mark_document_skipped(doc_id, reason='NOT_FINANCIAL_CONTENT', notes='...')."
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
