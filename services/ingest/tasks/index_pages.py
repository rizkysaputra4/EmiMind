"""Worker task: index_pages indexes document pages with text, OCR fallback, thumbnails and grids."""

from __future__ import annotations

import io
import json
import re
import time
from typing import Any

import pymupdf
from anyio import Path as AsyncPath
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.extraction.ocr import OcrUnavailableError, ocr_page
from services.extraction.page_quality import needs_ocr, non_whitespace_len
from services.extraction.pdf import detect_language, parse_pdf
from services.extraction.tables import extract_page_table_grids
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import get_logger
from services.shared.minio_client import ensure_bucket, get_minio
from services.shared.types import PageContent

log = get_logger("ingest.index_pages")
WORKER_VERSION = "2.0"
WORKER_NAME = "index_pages"

PAGE_COMMIT_BATCH = 25  # pages (and table-grid pages) written per transaction
THUMBNAIL_DPI = 150

# --- printed page labels -------------------------------------------------------------------
_EDGE_FRACTION = 0.08  # bare numbers/roman numerals must sit fully inside the top/bottom 8%
_MARKER_EDGE_FRACTION = 0.12  # "Lampiran 5/27", "Page 3 of 9" markers: top/bottom 12%
_MAX_LABEL_CHARS = 32
_DASHES = r"[\-–—\s]*"
_BARE_LABEL_RE = re.compile(rf"^{_DASHES}(\d{{1,4}}|[ivxlcdm]{{1,6}}){_DASHES}$", re.IGNORECASE)
_ROMAN_RE = re.compile(r"^m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$", re.I)
_MARKER_LABEL_RE = re.compile(
    r"^(?:lampiran|schedule|halaman|hal\.|page)\s*"
    r"(\d{1,4}(?:\s*/\s*\d{1,4})?|[ivxlcdm]{1,6})"
    r"(?:\s+(?:dari|of)\s+\d{1,4})?"
    r"(?:\s+(?:schedule|page|halaman|lampiran))?$",
    re.IGNORECASE,
)


def _bare_label(block_text: str) -> str | None:
    m = _BARE_LABEL_RE.match(block_text)
    if not m:
        return None
    label = m.group(1)
    if label.isdigit():
        # 4-digit years in running headers/footers are not page numbers
        if len(label) == 4 and 1900 <= int(label) <= 2100:
            return None
        return label
    return label if _ROMAN_RE.match(label) else None


def _marker_label(block_text: str) -> str | None:
    m = _MARKER_LABEL_RE.match(block_text)
    if not m:
        return None
    label = re.sub(r"\s+", "", m.group(1))
    if label.isalpha() and not _ROMAN_RE.match(label):
        return None
    return label


def detect_page_label(page: pymupdf.Page) -> str | None:
    """Printed page label from a short standalone text block at the page edge.

    Accepted, bottom band before top band:
      * a bare page number (1-4 digits, not a year) or a valid roman numeral, optionally
        wrapped in dashes, whose block lies fully inside the top/bottom 8% of the page;
      * an explicit marker ("Lampiran 5/27 Schedule", "Halaman 3", "Page 3 of 9") whose block
        lies fully inside the top/bottom 12% (running schedule labels sit just below the
        company header, e.g. AALI's "Lampiran 5/27").
    Blocks longer than 32 characters (sentences, table rows) are never labels.
    """
    rect = page.rect
    height = float(rect.height)
    if height <= 0:
        return None
    top = float(rect.y0)

    bottom_hits: list[tuple[float, str]] = []
    top_hits: list[tuple[float, str]] = []
    blocks = page.get_text("blocks")  # type: ignore[no-untyped-call]
    for _x0, y0, _x1, y1, b_text, _b_no, b_type in blocks:
        if b_type != 0:
            continue
        clean = re.sub(r"\s+", " ", str(b_text)).strip()
        if not clean or len(clean) > _MAX_LABEL_CHARS:
            continue
        rel_y0 = (float(y0) - top) / height
        rel_y1 = (float(y1) - top) / height
        in_bottom = rel_y0 >= 1.0 - _EDGE_FRACTION
        in_top = rel_y1 <= _EDGE_FRACTION
        label = _bare_label(clean) if (in_bottom or in_top) else None
        if label is None:
            in_bottom = rel_y0 >= 1.0 - _MARKER_EDGE_FRACTION
            in_top = rel_y1 <= _MARKER_EDGE_FRACTION
            if in_bottom or in_top:
                label = _marker_label(clean)
        if label is None:
            continue
        if in_bottom:
            bottom_hits.append((-rel_y0, label))  # lowest block first
        else:
            top_hits.append((rel_y1, label))  # highest block first

    if bottom_hits:
        return min(bottom_hits)[1]
    if top_hits:
        return min(top_hits)[1]
    return None


# --- worker_runs helpers -------------------------------------------------------------------


async def _set_run_status(
    conn: AsyncConnection, doc_hash: str, status: str, error: str | None = None
) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, error,
                                     started_at, finished_at)
            VALUES (:hash, :name, :ver, :status, :error, now(),
                    CASE WHEN :status = 'running' THEN NULL ELSE now() END)
            ON CONFLICT (doc_hash, worker_name, worker_version) DO UPDATE SET
                status = EXCLUDED.status,
                error = EXCLUDED.error,
                started_at = CASE WHEN EXCLUDED.status = 'running' THEN now()
                                  ELSE worker_runs.started_at END,
                finished_at = EXCLUDED.finished_at;
            """
        ),
        {
            "hash": doc_hash,
            "name": WORKER_NAME,
            "ver": WORKER_VERSION,
            "status": status,
            "error": error[:4000] if error else None,
        },
    )


async def _load_pdf_bytes(doc: Any, minio_client: Any, settings: Any, doc_id: str) -> bytes:
    minio_key = doc["minio_key"]
    source_url = doc.get("source_url")
    pdf_bytes: bytes | None = None
    if minio_key:
        try:
            response = minio_client.get_object(settings.minio_bucket_raw, minio_key)
            try:
                pdf_bytes = response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            log.warning("Could not read PDF from MinIO", minio_key=minio_key, error=str(exc))

    if not pdf_bytes and source_url:
        p = AsyncPath(source_url)
        if await p.is_file():
            pdf_bytes = await p.read_bytes()
            if minio_key:
                try:
                    minio_client.put_object(
                        settings.minio_bucket_raw,
                        minio_key,
                        io.BytesIO(pdf_bytes),
                        length=len(pdf_bytes),
                        content_type="application/pdf",
                    )
                except Exception as exc:
                    log.warning(
                        "Could not upload PDF to MinIO", minio_key=minio_key, error=str(exc)
                    )

    if not pdf_bytes:
        raise FileNotFoundError(
            f"Could not load PDF bytes for doc {doc_id} from MinIO ({minio_key}) "
            f"or source_url ({source_url})"
        )
    return pdf_bytes


_UPSERT_PAGE = text(
    """
    INSERT INTO document_pages (
        doc_id, page_index, page_label, page_text, text_source, language, image_key
    )
    VALUES (
        :doc_id, :page_index, :page_label, :page_text, :text_source, :language, :image_key
    )
    ON CONFLICT (doc_id, page_index) DO UPDATE SET
        page_label = EXCLUDED.page_label,
        -- a changed text invalidates the page vector; unchanged text keeps it
        embedding = CASE WHEN document_pages.page_text IS DISTINCT FROM EXCLUDED.page_text
                         THEN NULL ELSE document_pages.embedding END,
        embedding_model = CASE WHEN document_pages.page_text IS DISTINCT FROM EXCLUDED.page_text
                               THEN NULL ELSE document_pages.embedding_model END,
        page_text = EXCLUDED.page_text,
        text_source = EXCLUDED.text_source,
        language = EXCLUDED.language,
        image_key = EXCLUDED.image_key;
    """
)

_INSERT_GRID = text(
    """
    INSERT INTO document_page_tables (
        doc_id, page_index, table_index, extraction_method, confidence, unit_hint, cells
    ) VALUES (
        :doc_id, :page_index, :table_index, :extraction_method, :confidence, :unit_hint,
        CAST(:cells AS jsonb)
    )
    ON CONFLICT (doc_id, page_index, table_index) DO UPDATE SET
        extraction_method = EXCLUDED.extraction_method,
        confidence = EXCLUDED.confidence,
        unit_hint = EXCLUDED.unit_hint,
        cells = EXCLUDED.cells;
    """
)


def _page_text_with_ocr(
    mu_page: pymupdf.Page, raw_text: str, min_chars: int
) -> tuple[str, str, str | None]:
    """(page_text, text_source, ocr_error). OCR errors or too little text → 'ocr_failed'."""
    try:
        ocr_text = ocr_page(mu_page)
        ocr_error = None
    except OcrUnavailableError as exc:
        ocr_text, ocr_error = "", str(exc)
    if non_whitespace_len(ocr_text) >= min_chars:
        return ocr_text, "ocr", None
    if ocr_error is None:
        ocr_error = f"OCR produced {non_whitespace_len(ocr_text)} chars (< {min_chars})"
    # keep whatever text exists so the page is still searchable; the source flags it
    best = ocr_text if non_whitespace_len(ocr_text) > non_whitespace_len(raw_text) else raw_text
    return best, "ocr_failed", ocr_error


async def _index_document(
    conn: AsyncConnection, doc_id: str, pdf_bytes: bytes, minio_client: Any, settings: Any
) -> dict[str, Any]:
    t0 = time.perf_counter()
    parsed_pages = parse_pdf(pdf_bytes)
    mu_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    total_pages = len(mu_doc)
    min_chars = int(getattr(settings, "ocr_min_chars", 50))
    log.info("Indexing pages for document", doc_id=doc_id, pages=total_pages)

    pdf_text_pages: list[PageContent] = []
    counts = {"pdf_text": 0, "ocr": 0, "ocr_failed": 0, "labelled": 0}
    ocr_errors: dict[int, str] = {}
    try:
        for page_index in range(1, total_pages + 1):
            mu_page = mu_doc[page_index - 1]
            parsed = parsed_pages[page_index - 1] if page_index <= len(parsed_pages) else None
            raw_text = parsed.text if parsed else str(mu_page.get_text("text"))  # type: ignore[no-untyped-call]

            if needs_ocr(raw_text, min_chars=min_chars):
                page_text, text_source, ocr_error = _page_text_with_ocr(
                    mu_page, raw_text, min_chars
                )
                if ocr_error:
                    ocr_errors[page_index] = ocr_error
                page_lang = detect_language(page_text) if page_text.strip() else "id"
            else:
                text_source = "pdf_text"
                page_text = raw_text
                page_lang = parsed.language if parsed else detect_language(page_text)
                pdf_text_pages.append(
                    parsed
                    if parsed
                    else PageContent(
                        page_num=page_index,
                        text=page_text,
                        language=page_lang,
                        has_text_layer=True,
                    )
                )
            counts[text_source] += 1

            pix = mu_page.get_pixmap(dpi=THUMBNAIL_DPI)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            img.save(buf, format="WEBP")
            webp_bytes = buf.getvalue()
            image_key = f"thumbnails/{doc_id}/page_{page_index}.webp"
            minio_client.put_object(
                settings.minio_bucket_raw,
                image_key,
                io.BytesIO(webp_bytes),
                length=len(webp_bytes),
                content_type="image/webp",
            )

            page_label = detect_page_label(mu_page)
            counts["labelled"] += page_label is not None

            await conn.execute(
                _UPSERT_PAGE,
                {
                    "doc_id": doc_id,
                    "page_index": page_index,
                    "page_label": page_label,
                    "page_text": page_text,
                    "text_source": text_source,
                    "language": page_lang,
                    "image_key": image_key,
                },
            )
            if page_index % PAGE_COMMIT_BATCH == 0:
                await conn.commit()
    finally:
        mu_doc.close()  # type: ignore[no-untyped-call]

    # Pages beyond the current page count (a replaced PDF) are stale.
    await conn.execute(
        text("DELETE FROM document_pages WHERE doc_id = :id AND page_index > :n"),
        {"id": doc_id, "n": total_pages},
    )
    await conn.commit()
    if ocr_errors:
        log.warning(
            "OCR failed on pages",
            doc_id=doc_id,
            pages=sorted(ocr_errors),
            first_error=next(iter(ocr_errors.values())),
        )

    # Table grids: stale rows from a previous index are dropped, then rebuilt in page batches.
    await conn.execute(
        text("DELETE FROM document_page_tables WHERE doc_id = :id"), {"id": doc_id}
    )
    n_grids = 0
    for i in range(0, len(pdf_text_pages), PAGE_COMMIT_BATCH):
        chunk = pdf_text_pages[i : i + PAGE_COMMIT_BATCH]
        for grid in extract_page_table_grids(pdf_bytes, chunk):
            await conn.execute(
                _INSERT_GRID,
                {
                    "doc_id": doc_id,
                    "page_index": grid["page_index"],
                    "table_index": grid["table_index"],
                    "extraction_method": grid["extraction_method"],
                    "confidence": grid["confidence"],
                    "unit_hint": grid["unit_hint"],
                    "cells": json.dumps(grid["cells"]),
                },
            )
            n_grids += 1
        await conn.commit()
    await conn.commit()

    return {
        "status": "ok",
        "pages": total_pages,
        "text_sources": {k: v for k, v in counts.items() if k != "labelled"},
        "labelled_pages": counts["labelled"],
        "ocr_failed_pages": sorted(ocr_errors) if counts["ocr_failed"] else [],
        "tables": n_grids,
        "elapsed_s": round(time.perf_counter() - t0, 2),
    }


async def index_pages_task(
    ctx: dict[str, Any], doc_id: str, *, force: bool = False
) -> dict[str, Any]:
    """Indexes all physical pages of a document into document_pages / document_page_tables.

    1. Skip when worker_runs has (doc_hash, 'index_pages', WORKER_VERSION) = ok (unless force).
    2. Load the PDF (MinIO, else source_url) and open it once.
    3. Per page: text layer, or OCR on the already-open page when the text layer has
       < EMI_OCR_MIN_CHARS characters; OCR errors / short OCR output → text_source='ocr_failed'.
    4. Thumbnail (150 DPI WebP) to MinIO, printed page label, upsert; commit every 25 pages.
    5. Drop stale page/table rows, rebuild table grids for text pages in 25-page batches.
    6. worker_runs 'ok'; on any exception worker_runs 'failed' with the error, then re-raise.
    """
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    minio_client = ctx.get("minio_client") or ctx.get("minio")
    settings = ctx.get("settings") or get_settings()

    if engine is None:
        engine = create_pool(settings.postgres_dsn)
    if minio_client is None:
        minio_client = get_minio(settings)

    ensure_bucket(minio_client, settings.minio_bucket_raw)

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, doc_hash, minio_key, source_url FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")
        doc_hash = str(doc["doc_hash"])

        run_res = await conn.execute(
            text(
                "SELECT status FROM worker_runs WHERE doc_hash = :hash "
                "AND worker_name = :name AND worker_version = :ver"
            ),
            {"hash": doc_hash, "name": WORKER_NAME, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok" and not force:
            log.info("index_pages already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        await _set_run_status(conn, doc_hash, "running")
        await conn.commit()
        try:
            pdf_bytes = await _load_pdf_bytes(doc, minio_client, settings, doc_id)
            result = await _index_document(conn, doc_id, pdf_bytes, minio_client, settings)
        except Exception as exc:
            await conn.rollback()
            await _set_run_status(conn, doc_hash, "failed", f"{type(exc).__name__}: {exc}")
            await conn.commit()
            log.error("index_pages failed", doc_id=doc_id, error=str(exc))
            raise

        await _set_run_status(conn, doc_hash, "ok")
        await conn.commit()

    log.info("index_pages completed", doc_id=doc_id, **result)
    return result
