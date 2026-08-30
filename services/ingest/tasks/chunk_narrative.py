"""Worker task: chunk_narrative produces semantic text chunks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.narrative.chunker import chunk_pages
from services.shared.config import get_settings
from services.shared.logging import get_logger
from services.shared.types import PageContent

log = get_logger("ingest.chunk_narrative")
WORKER_VERSION = "2.1"


async def chunk_narrative_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Generates semantic narrative chunks and inserts into narrative_chunks table."""
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    minio_client = ctx.get("minio_client") or ctx.get("minio")
    if engine is None or minio_client is None:
        raise RuntimeError("Worker context missing database pool or MinIO client.")
    settings = get_settings()

    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                "SELECT id, ticker, doc_type, fiscal_period, doc_hash, minio_key FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        ticker = doc["ticker"]
        doc_type = doc["doc_type"]
        fiscal_period = doc["fiscal_period"]
        doc_hash = doc["doc_hash"]
        minio_key = doc["minio_key"]

        # 1. Idempotency check
        run_res = await conn.execute(
            text(
                "SELECT status FROM worker_runs WHERE doc_hash = :hash AND worker_name = 'chunk_narrative' AND worker_version = :ver"
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("chunk_narrative already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        # 2. Read pages.jsonl from MinIO
        pages_key = f"{minio_key}.pages.jsonl"
        try:
            pages_resp = minio_client.get_object(settings.minio_bucket_raw, pages_key)
            pages_content = pages_resp.read().decode("utf-8")
            pages_resp.close()
            pages_resp.release_conn()
        except Exception:
            log.warning("No pages.jsonl found; skipping narrative chunking", doc_id=doc_id)
            return {"chunks": 0}

        pages = [
            PageContent.model_validate_json(line)
            for line in pages_content.splitlines()
            if line.strip()
        ]

        # 3. Chunk pages with deterministic semantic extractor
        chunks = chunk_pages(
            pages=pages,
            ticker=ticker,
            doc_type=doc_type,
            fiscal_period=fiscal_period,
        )

        # 4. Insert chunks into narrative_chunks table
        inserted_count = 0
        insert_sql = """
        INSERT INTO narrative_chunks (
            ticker, source_doc_id, source_page, fiscal_period, section,
            language, text_original, text_en, speaker, claim_type,
            mentioned_concepts, mentioned_periods, tsv
        ) VALUES (
            :ticker, :doc_id, :page, :fiscal_period, :section,
            :lang, :text_orig, :text_en, :speaker, :claim_type,
            :concepts, :periods, to_tsvector('simple', :text_orig)
        );
        """

        for c in chunks:
            await conn.execute(
                text(insert_sql),
                {
                    "ticker": ticker,
                    "doc_id": doc_id,
                    "page": c.source_page,
                    "fiscal_period": fiscal_period,
                    "section": c.section,
                    "lang": c.language,
                    "text_orig": c.text_original,
                    "text_en": c.text_en,
                    "speaker": c.speaker,
                    "claim_type": c.claim_type,
                    "concepts": c.mentioned_concepts,
                    "periods": c.mentioned_periods,
                },
            )
            inserted_count += 1

        # 5. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'chunk_narrative', :ver, 'ok', now())
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

        log.info("chunk_narrative completed", doc_id=doc_id, chunks=inserted_count)
        return {"chunks": inserted_count}
