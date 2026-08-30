"""Document upload router: legacy one-shot upload + LLM-assisted inspect/approve flow."""

from __future__ import annotations

import datetime
import hashlib
import json

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from minio import Minio
from minio.commonconfig import CopySource
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.api.deps import get_db_conn, get_minio_client, get_redis
from services.extraction.metadata_extractor import propose_metadata
from services.shared.config import get_settings
from services.shared.logging import get_logger
from services.shared.minio_client import pending_key, put_pdf, raw_key
from services.shared.redis_client import enqueue_job
from services.shared.types import (
    ApproveRequest,
    DocType,
    InspectResponse,
    Language,
    ProposedMetadata,
    UploadResponse,
    validate_fiscal_period,
    validate_ticker,
)

logger = get_logger("api.upload")
router = APIRouter(prefix="/api/v1", tags=["upload"])

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


def derive_period_end(fiscal_period: str) -> datetime.date:
    """Derives standard quarter-end or year-end date from fiscal period string."""
    year = int(fiscal_period[:4])
    suffix = fiscal_period[4:].upper()

    if suffix in ("Q1",):
        return datetime.date(year, 3, 31)
    if suffix in ("Q2", "H1"):
        return datetime.date(year, 6, 30)
    if suffix in ("Q3",):
        return datetime.date(year, 9, 30)
    if suffix in ("Q4", "FY", "H2"):
        return datetime.date(year, 12, 31)
    return datetime.date(year, 12, 31)


async def _read_and_validate_pdf(file: UploadFile) -> bytes:
    """Shared checks: content-type, size, non-empty. Raises HTTPException on failure."""
    if file.content_type not in ("application/pdf", "application/x-pdf") and not (
        file.filename and file.filename.lower().endswith(".pdf")
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded file must be a valid PDF (application/pdf).",
        )
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE // (1024 * 1024)}MB.",
        )
    if len(pdf_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF file is empty.",
        )
    return pdf_bytes


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    ticker: str = Form(...),
    doc_type: DocType = Form(...),
    fiscal_period: str = Form(...),
    language: Language = Form(...),
    file: UploadFile = Form(...),
    xbrl_file: UploadFile | None = None,
    db: AsyncConnection = Depends(get_db_conn),
    minio_client: Minio = Depends(get_minio_client),
    redis_pool: ArqRedis = Depends(get_redis),
) -> UploadResponse:
    """Uploads a PDF financial document, stores to MinIO, and registers in DB (legacy one-shot)."""
    try:
        valid_ticker = validate_ticker(ticker)
        valid_period = validate_fiscal_period(fiscal_period)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err

    pdf_bytes = await _read_and_validate_pdf(file)

    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()
    query_existing = text("SELECT id, status FROM documents WHERE doc_hash = :doc_hash LIMIT 1;")
    result = await db.execute(query_existing, {"doc_hash": doc_hash})
    existing_row = result.mappings().first()

    if existing_row:
        return UploadResponse(
            document_id=str(existing_row["id"]),
            status=str(existing_row["status"]),
            deduplicated=True,
        )

    pdf_minio_key = raw_key(valid_ticker, doc_type, valid_period, doc_hash, "pdf")
    put_pdf(minio_client, pdf_minio_key, pdf_bytes)

    if xbrl_file is not None:
        xbrl_bytes = await xbrl_file.read()
        if xbrl_bytes:
            xbrl_minio_key = raw_key(valid_ticker, doc_type, valid_period, doc_hash, "xbrl.xml")
            put_pdf(minio_client, xbrl_minio_key, xbrl_bytes)

    period_end = derive_period_end(valid_period)
    insert_sql = text(
        """
        INSERT INTO documents (
            ticker, doc_type, period_end, fiscal_period, language, minio_key, doc_hash, status
        ) VALUES (
            :ticker, :doc_type, :period_end, :fiscal_period, :language, :minio_key, :doc_hash, 'raw'
        )
        RETURNING id, status;
        """
    )
    insert_result = await db.execute(
        insert_sql,
        {
            "ticker": valid_ticker,
            "doc_type": doc_type,
            "period_end": period_end,
            "fiscal_period": valid_period,
            "language": language,
            "minio_key": pdf_minio_key,
            "doc_hash": doc_hash,
        },
    )
    await db.commit()
    new_row = insert_result.mappings().one()
    doc_id = str(new_row["id"])

    try:
        await enqueue_job(redis_pool, "ingest_document", doc_id)
    except Exception as exc:
        logger.warning("Failed to enqueue ingestion task", document_id=doc_id, error=str(exc))

    return UploadResponse(
        document_id=doc_id,
        status="raw",
        deduplicated=False,
    )


@router.post("/upload/inspect", response_model=InspectResponse)
async def inspect_document(
    file: UploadFile = Form(...),
    db: AsyncConnection = Depends(get_db_conn),
    minio_client: Minio = Depends(get_minio_client),
) -> InspectResponse:
    """Stores a PDF to the pending prefix and proposes metadata for review.

    Regex-first, LLM-fallback extraction. Creates a `documents` row with
    status='pending_review'. No ingestion is enqueued until the user approves.
    """
    pdf_bytes = await _read_and_validate_pdf(file)
    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Dedup: if the hash matches an existing non-pending doc, return its id.
    result = await db.execute(
        text("SELECT id, status, ticker, fiscal_period, doc_type, language "
             "FROM documents WHERE doc_hash = :h LIMIT 1;"),
        {"h": doc_hash},
    )
    existing = result.mappings().first()
    if existing:
        proposed = ProposedMetadata(
            ticker=existing["ticker"],
            fiscal_period=existing["fiscal_period"],
            doc_type=existing["doc_type"],
            language=existing["language"],
            confidence={"ticker": 1.0, "fiscal_period": 1.0, "doc_type": 1.0},
            source="regex",
        )
        return InspectResponse(
            document_id=str(existing["id"]),
            proposed=proposed,
            deduplicated=True,
            existing_status=str(existing["status"]),
        )

    # Store to pending/ prefix.
    p_key = pending_key(doc_hash, "pdf")
    put_pdf(minio_client, p_key, pdf_bytes)

    # Propose metadata (regex + LLM fallback).
    proposed = await propose_metadata(pdf_bytes)

    # Insert placeholder row so refresh/reload preserves state.
    placeholder_ticker = proposed.ticker or "XXXX"
    placeholder_period = proposed.fiscal_period or "2000FY"
    placeholder_doctype: DocType = proposed.doc_type or "FS_QUARTERLY"
    period_end = derive_period_end(placeholder_period)

    insert_sql = text(
        """
        INSERT INTO documents (
            ticker, doc_type, period_end, fiscal_period, language, minio_key, doc_hash,
            status, proposed_metadata
        ) VALUES (
            :ticker, :doc_type, :period_end, :fiscal_period, :language, :minio_key, :doc_hash,
            'pending_review', CAST(:proposed AS JSONB)
        )
        RETURNING id;
        """
    )
    ins = await db.execute(
        insert_sql,
        {
            "ticker": placeholder_ticker,
            "doc_type": placeholder_doctype,
            "period_end": period_end,
            "fiscal_period": placeholder_period,
            "language": proposed.language,
            "minio_key": p_key,
            "doc_hash": doc_hash,
            "proposed": json.dumps(proposed.model_dump()),
        },
    )
    await db.commit()
    new_row = ins.mappings().one()

    return InspectResponse(
        document_id=str(new_row["id"]),
        proposed=proposed,
        deduplicated=False,
    )


@router.post("/upload/approve/{document_id}", response_model=UploadResponse)
async def approve_document(
    document_id: str,
    payload: ApproveRequest,
    db: AsyncConnection = Depends(get_db_conn),
    minio_client: Minio = Depends(get_minio_client),
    redis_pool: ArqRedis = Depends(get_redis),
) -> UploadResponse:
    """Finalises a pending_review document: writes final metadata, moves the object, enqueues ingest."""
    row_result = await db.execute(
        text("SELECT id, status, doc_hash, minio_key FROM documents WHERE id = :id LIMIT 1;"),
        {"id": document_id},
    )
    row = row_result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    if row["status"] != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not awaiting review (current status: {row['status']}).",
        )

    doc_hash = str(row["doc_hash"])
    current_key = str(row["minio_key"])
    canonical_key = raw_key(
        payload.ticker, payload.doc_type, payload.fiscal_period, doc_hash, "pdf"
    )

    if canonical_key != current_key:
        bucket = get_settings().minio_bucket_raw
        try:
            minio_client.copy_object(
                bucket_name=bucket,
                object_name=canonical_key,
                source=CopySource(bucket, current_key),
            )
            # Verify the copy actually landed before removing the source.
            minio_client.stat_object(bucket, canonical_key)
            minio_client.remove_object(bucket, current_key)
        except Exception as exc:
            logger.error(
                "Failed to move approved document in MinIO",
                document_id=document_id,
                src=current_key,
                dst=canonical_key,
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail="Storage move failed.") from exc

    period_end = derive_period_end(payload.fiscal_period)
    await db.execute(
        text(
            """
            UPDATE documents SET
                ticker = :ticker,
                doc_type = :doc_type,
                period_end = :period_end,
                fiscal_period = :fiscal_period,
                language = :language,
                minio_key = :minio_key,
                status = 'raw',
                proposed_metadata = NULL
            WHERE id = :id;
            """
        ),
        {
            "ticker": payload.ticker,
            "doc_type": payload.doc_type,
            "period_end": period_end,
            "fiscal_period": payload.fiscal_period,
            "language": payload.language,
            "minio_key": canonical_key,
            "id": document_id,
        },
    )
    await db.commit()

    try:
        await enqueue_job(redis_pool, "ingest_document", document_id)
    except Exception as exc:
        logger.warning(
            "Failed to enqueue ingestion task after approval",
            document_id=document_id,
            error=str(exc),
        )

    return UploadResponse(document_id=document_id, status="raw", deduplicated=False)


@router.delete("/upload/pending/{document_id}")
async def discard_pending_document(
    document_id: str,
    db: AsyncConnection = Depends(get_db_conn),
    minio_client: Minio = Depends(get_minio_client),
) -> dict[str, str]:
    """Removes a pending_review document (DB row + MinIO object)."""
    row_result = await db.execute(
        text("SELECT id, status, minio_key FROM documents WHERE id = :id LIMIT 1;"),
        {"id": document_id},
    )
    row = row_result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    if row["status"] != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=f"Only pending documents may be discarded (status: {row['status']}).",
        )

    bucket = get_settings().minio_bucket_raw
    try:
        minio_client.remove_object(bucket, str(row["minio_key"]))
    except Exception as exc:
        logger.warning(
            "Failed to remove pending MinIO object",
            document_id=document_id,
            key=str(row["minio_key"]),
            error=str(exc),
        )

    await db.execute(text("DELETE FROM documents WHERE id = :id;"), {"id": document_id})
    await db.commit()

    return {"status": "discarded", "document_id": document_id}
