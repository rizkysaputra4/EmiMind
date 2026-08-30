"""Citation resolution and evidence verification API router."""

from __future__ import annotations

import base64
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from minio import Minio
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.api.deps import get_db, get_minio_client
from services.api.pdf_render import render_page_png
from services.shared.config import Settings, get_settings
from services.shared.logging import get_logger
from services.shared.types import BBox

logger = get_logger("api.citation")

router = APIRouter(prefix="/api/v1", tags=["citation"])

CITATION_PARSE_REGEX = re.compile(
    r"^\[?([A-Z0-9]{2,10})-([A-Z0-9_]+)-([A-Z0-9_]+)(?:#p(\d+))?\]?$"
)


class CitationDetailResponse(BaseModel):
    """Detailed evidence metadata and visual crop payload for a citation tag."""

    citation: str
    ticker: str
    fiscal_period: str
    page: int
    bbox: list[float] | None = None
    document: dict[str, Any] | None = None
    fact: dict[str, Any] | None = None
    chunk: dict[str, Any] | None = None
    image_base64: str | None = None
    image_error: str | None = None


class ReportCitationRequest(BaseModel):
    """Payload for reporting extraction inaccuracies."""

    citation: str
    feedback: str
    correct_value: str | None = None


@router.get("/citation/{citation_tag:path}/image")
async def get_citation_image(
    citation_tag: str,
    conn: AsyncConnection = Depends(get_db),
    minio: Minio = Depends(get_minio_client),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Renders and streams the PNG image of the cited filing page with highlighted bbox."""
    clean_tag = citation_tag.strip("[]")
    m = CITATION_PARSE_REGEX.match(clean_tag)
    if not m:
        raise HTTPException(status_code=400, detail=f"Malformed citation format: '{citation_tag}'")

    ticker, _doc_type, period, page_str = m.groups()
    page_num = int(page_str) if page_str else 1

    # Find document
    doc_res = await conn.execute(
        text(
            "SELECT id, minio_key FROM documents WHERE ticker = :ticker AND fiscal_period = :period LIMIT 1"
        ),
        {"ticker": ticker, "period": period},
    )
    doc = doc_res.mappings().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Source document not found for citation.")

    # Find bbox
    f_res = await conn.execute(
        text(
            "SELECT source_bbox FROM financial_facts "
            "WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"
        ),
        {"ticker": ticker, "period": period, "page": page_num},
    )
    f_row = f_res.mappings().first()
    bbox: BBox | None = None
    if f_row and f_row["source_bbox"]:
        bbox = BBox(*f_row["source_bbox"])

    # Fetch PDF from MinIO
    try:
        obj = minio.get_object(settings.minio_bucket_raw, doc["minio_key"])
        pdf_bytes = obj.read()
        obj.close()
        obj.release_conn()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to read filing from storage: {e}"
        ) from e

    png_bytes = render_page_png(pdf_bytes, page_num=page_num, bbox=bbox)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/citation/{citation_tag:path}", response_model=CitationDetailResponse)
async def resolve_citation_detail(
    citation_tag: str,
    conn: AsyncConnection = Depends(get_db),
    minio: Minio = Depends(get_minio_client),
    settings: Settings = Depends(get_settings),
) -> CitationDetailResponse:
    """Resolves citation tag to exact document, fact, chunk, and rendered thumbnail."""
    clean_tag = citation_tag.strip("[]")
    m = CITATION_PARSE_REGEX.match(clean_tag)
    if not m:
        raise HTTPException(status_code=400, detail=f"Malformed citation format: '{citation_tag}'")

    ticker, doc_type_tag, period, page_str = m.groups()
    page_num = int(page_str) if page_str else 1

    # PROFILE citations are non-page-based; short-circuit to the issuer profile card.
    if doc_type_tag == "PROFILE":
        p_res = await conn.execute(
            text(
                "SELECT ticker, name, sector, sub_sector, profile_summary_en, "
                "last_facts_period, key_kpis FROM issuer_profile WHERE ticker = :ticker LIMIT 1"
            ),
            {"ticker": ticker},
        )
        profile = p_res.mappings().first()
        if not profile:
            raise HTTPException(
                status_code=404, detail="Issuer profile not found for citation."
            )
        return CitationDetailResponse(
            citation=f"[{clean_tag}]",
            ticker=ticker,
            fiscal_period=period,
            page=0,
            bbox=None,
            document=None,
            fact=None,
            chunk={
                "id": None,
                "section": "PROFILE",
                "text_original": profile["profile_summary_en"] or "",
                "text_en": profile["profile_summary_en"] or "",
                "source_page": None,
            },
            image_base64=None,
            image_error=(
                "Profile citations summarize the issuer card and are not "
                "tied to a single PDF page."
            ),
        )

    doc_res = await conn.execute(
        text(
            "SELECT id, ticker, doc_type, fiscal_period, period_end, minio_key, doc_hash, status "
            "FROM documents WHERE ticker = :ticker AND fiscal_period = :period LIMIT 1"
        ),
        {"ticker": ticker, "period": period},
    )
    doc = doc_res.mappings().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Source document not found for citation.")

    # Find fact
    f_res = await conn.execute(
        text(
            "SELECT id, concept_id, concept_local, value_numeric, unit, source_page, source_bbox, extraction_conf AS confidence, extraction_method AS method "
            "FROM financial_facts WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"
        ),
        {"ticker": ticker, "period": period, "page": page_num},
    )
    fact = f_res.mappings().first()

    # Find narrative chunk
    nc_res = await conn.execute(
        text(
            "SELECT id, section, text_original, text_en, source_page "
            "FROM narrative_chunks WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"
        ),
        {"ticker": ticker, "period": period, "page": page_num},
    )
    chunk = nc_res.mappings().first()

    bbox_list: list[float] | None = None
    bbox_obj: BBox | None = None
    if fact and fact["source_bbox"]:
        bbox_list = list(fact["source_bbox"])
        bbox_obj = BBox(*fact["source_bbox"])

    # Render image thumbnail
    image_b64: str | None = None
    image_error: str | None = None
    try:
        obj = minio.get_object(settings.minio_bucket_raw, doc["minio_key"])
        pdf_bytes = obj.read()
        obj.close()
        obj.release_conn()
        png_bytes = render_page_png(pdf_bytes, page_num=page_num, bbox=bbox_obj, dpi=100)
        image_b64 = base64.b64encode(png_bytes).decode("utf-8")
    except Exception as exc:
        err_str = str(exc)
        if "NoSuchKey" in err_str or "specified key does not exist" in err_str.lower():
            image_error = (
                "Source PDF is missing from storage. The document is registered "
                "in the database but the file is no longer in MinIO — it likely "
                "needs to be re-uploaded."
            )
        else:
            image_error = f"Rendering failed: {err_str[:200]}"
        logger.warning(
            "Failed to render citation thumbnail",
            citation=clean_tag,
            ticker=ticker,
            period=period,
            page=page_num,
            minio_key=str(doc.get("minio_key")),
            error=err_str,
            exc_info=True,
        )

    return CitationDetailResponse(
        citation=f"[{clean_tag}]",
        ticker=ticker,
        fiscal_period=period,
        page=page_num,
        bbox=bbox_list,
        document=dict(doc),
        fact=dict(fact) if fact else None,
        chunk=dict(chunk) if chunk else None,
        image_base64=image_b64,
        image_error=image_error,
    )


@router.post("/citation/report")
async def report_citation(
    payload: ReportCitationRequest,
    conn: AsyncConnection = Depends(get_db),
) -> dict[str, Any]:
    """Records human auditor extraction error feedback in citation_reports table."""
    clean_tag = payload.citation.strip("[]")
    m = CITATION_PARSE_REGEX.match(clean_tag)
    doc_id = None
    fact_id = None
    chunk_id = None

    if m:
        ticker, _doc_type, period, page_str = m.groups()
        page_num = int(page_str) if page_str else 1
        d_res = await conn.execute(
            text(
                "SELECT id FROM documents "
                "WHERE ticker = :ticker AND fiscal_period = :period LIMIT 1"
            ),
            {"ticker": ticker, "period": period},
        )
        d_row = d_res.mappings().first()
        if d_row:
            doc_id = d_row["id"]

        f_res = await conn.execute(
            text(
                "SELECT id FROM financial_facts "
                "WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"
            ),
            {"ticker": ticker, "period": period, "page": page_num},
        )
        f_row = f_res.mappings().first()
        if f_row:
            fact_id = f_row["id"]

    reason_text = payload.feedback
    if payload.correct_value:
        reason_text += f" (Correct value: {payload.correct_value})"

    await conn.execute(
        text(
            """
            INSERT INTO citation_reports (
                citation_str, doc_id, fact_id, chunk_id, reason, status
            )
            VALUES (
                :citation, :doc_id, :fact_id, :chunk_id, :reason, 'open'
            );
            """
        ),
        {
            "citation": payload.citation,
            "doc_id": doc_id,
            "fact_id": fact_id,
            "chunk_id": chunk_id,
            "reason": reason_text,
        },
    )
    return {"status": "recorded", "citation": payload.citation}
