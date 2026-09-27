"""Worker task: index_pages indexes document pages with text, OCR fallback, and thumbnails."""

from __future__ import annotations

import io
import json
import re
from typing import Any

import pymupdf
from anyio import Path as AsyncPath
from PIL import Image
from sqlalchemy import text

from services.extraction.ocr import ocr_page
from services.extraction.page_quality import needs_ocr
from services.extraction.pdf import detect_language, parse_pdf
from services.extraction.tables import extract_page_table_grids
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import get_logger
from services.shared.minio_client import ensure_bucket, get_minio
from services.shared.types import PageContent

log = get_logger("ingest.index_pages")
WORKER_VERSION = "1.0"

_PAGE_LABEL_RE = re.compile(r"^[\-\u2013\u2014\s]*([0-9]{1,4}|[ivxlcdm]+)[\-\u2013\u2014\s]*$", re.IGNORECASE)


def detect_page_label(page: pymupdf.Page) -> str | None:
    """Detects printed page label (a standalone number or roman numeral in the top/bottom 8% of the page).

    Checks bottom 8% first (most standard location for page numbers), then top 8%.
    """
    rect = page.rect
    height = rect.height
    if height <= 0:
        return None

    top_cutoff = 0.08 * height
    bottom_cutoff = 0.92 * height

    # PyMuPDF get_text("blocks") returns tuples: (x0, y0, x1, y1, text, block_no, block_type)
    blocks = page.get_text("blocks")  # type: ignore[no-untyped-call]

    # 1. Check bottom 8%
    for _x0, y0, _x1, y1, b_text, _b_no, b_type in blocks:
        if b_type == 0 and (y0 >= bottom_cutoff or y1 >= bottom_cutoff):
            for line in b_text.splitlines():
                clean = line.strip()
                m = _PAGE_LABEL_RE.match(clean)
                if m:
                    return m.group(1)

    # 2. Check top 8%
    for _x0, y0, _x1, y1, b_text, _b_no, b_type in blocks:
        if b_type == 0 and (y1 <= top_cutoff or y0 <= top_cutoff):
            for line in b_text.splitlines():
                clean = line.strip()
                # Ignore 4-digit years in header (e.g. 2024, 2025)
                if clean.isdigit() and 2000 <= int(clean) <= 2050:
                    continue
                m = _PAGE_LABEL_RE.match(clean)
                if m:
                    return m.group(1)

    return None


async def index_pages_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Indexes all physical pages of a document into document_pages.

    Steps:
      1. Check worker_runs idempotency (doc_hash, 'index_pages', WORKER_VERSION).
      2. Download PDF bytes from MinIO or fallback to local source_url.
      3. Parse per-page text and detect language.
      4. If page needs OCR (fewer than 15 chars or corrupted glyphs), run OCR fallback.
      5. Render 150 DPI WebP image and upload to MinIO thumbnails key.
      6. Detect printed page label in top/bottom 8% of page.
      7. Upsert into document_pages table.
      8. Mark worker_runs status as 'ok'.
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
        minio_key = doc["minio_key"]
        source_url = doc.get("source_url")

        # 1. Check worker_runs idempotency
        run_res = await conn.execute(
            text(
                "SELECT status FROM worker_runs WHERE doc_hash = :hash AND worker_name = 'index_pages' AND worker_version = :ver"
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("index_pages already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        # 2. Retrieve PDF bytes
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
                # Ensure it is also in MinIO
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
                        log.warning("Could not upload PDF to MinIO", minio_key=minio_key, error=str(exc))

        if not pdf_bytes:
            raise FileNotFoundError(
                f"Could not load PDF bytes for doc {doc_id} from MinIO ({minio_key}) or source_url ({source_url})"
            )

        # 3. Parse PDF with pdfplumber and pymupdf
        parsed_pages = parse_pdf(pdf_bytes)
        mu_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]

        total_pages = len(mu_doc)
        log.info("Indexing pages for document", doc_id=doc_id, pages=total_pages)
        pdf_text_pages: list[PageContent] = []

        try:
            for page_index in range(1, total_pages + 1):
                mu_page = mu_doc[page_index - 1]
                parsed_page = parsed_pages[page_index - 1] if page_index <= len(parsed_pages) else None

                raw_text = parsed_page.text if parsed_page else mu_page.get_text("text")  # type: ignore[no-untyped-call]

                # 4. OCR fallback check
                if needs_ocr(raw_text):
                    ocr_text = ocr_page(pdf_bytes, page_index, lang="ind+eng")
                    text_source = "ocr"
                    page_text = ocr_text if ocr_text else raw_text
                    page_lang = detect_language(page_text) if page_text else (parsed_page.language if parsed_page else "id")
                else:
                    text_source = "pdf_text"
                    page_text = raw_text
                    page_lang = parsed_page.language if parsed_page else detect_language(page_text)
                    pdf_text_pages.append(
                        parsed_page
                        if parsed_page
                        else PageContent(page_num=page_index, text=page_text, language=page_lang, has_text_layer=True)
                    )

                # 5. Render 150 DPI WebP image and upload to MinIO
                pix = mu_page.get_pixmap(dpi=150)
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

                # 6. Detect printed page label
                page_label = detect_page_label(mu_page)

                # 7. Upsert into document_pages
                await conn.execute(
                    text(
                        """
                        INSERT INTO document_pages (
                            doc_id, page_index, page_label, page_text, text_source, language, image_key
                        )
                        VALUES (
                            :doc_id, :page_index, :page_label, :page_text, :text_source, :language, :image_key
                        )
                        ON CONFLICT (doc_id, page_index) DO UPDATE SET
                            page_label = EXCLUDED.page_label,
                            page_text = EXCLUDED.page_text,
                            text_source = EXCLUDED.text_source,
                            language = EXCLUDED.language,
                            image_key = EXCLUDED.image_key;
                        """
                    ),
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

            # 8. Extract table grids for pdf_text pages and store in document_page_tables
            if pdf_text_pages:
                grids = extract_page_table_grids(pdf_bytes, pdf_text_pages)
                for grid in grids:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO document_page_tables (
                                doc_id, page_index, table_index, extraction_method,
                                confidence, unit_hint, cells
                            ) VALUES (
                                :doc_id, :page_index, :table_index, :extraction_method,
                                :confidence, :unit_hint, CAST(:cells AS jsonb)
                            )
                            ON CONFLICT (doc_id, page_index, table_index) DO UPDATE SET
                                extraction_method = EXCLUDED.extraction_method,
                                confidence = EXCLUDED.confidence,
                                unit_hint = EXCLUDED.unit_hint,
                                cells = EXCLUDED.cells;
                            """
                        ),
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

            # 9. Record worker_runs
            await conn.execute(
                text(
                    """
                    INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                    VALUES (:hash, 'index_pages', :ver, 'ok', now())
                    ON CONFLICT (doc_hash, worker_name, worker_version)
                    DO UPDATE SET status = 'ok', finished_at = now();
                    """
                ),
                {
                    "hash": doc_hash,
                    "ver": WORKER_VERSION,
                },
            )
            await conn.commit()

        finally:
            mu_doc.close()  # type: ignore[no-untyped-call]

        log.info("index_pages completed", doc_id=doc_id, pages=total_pages)
        return {"status": "ok", "pages": total_pages}
