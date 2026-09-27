"""Worker task for computing and storing dense page embeddings."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

from services.narrative.embedder import Embedder
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("ingest.embed_pages")
WORKER_VERSION = "1.0"


async def embed_pages_task(
    ctx: dict[str, Any],
    doc_id: str,
    batch_size: int = 32,
) -> dict[str, Any]:
    """Computes and writes dense embeddings for document_pages where embedding IS NULL.

    Args:
        ctx: Worker context with db_pool/db_engine, embedder, and settings.
        doc_id: UUID of document to embed.
        batch_size: Batch size passed to embedder (default: 32).

    Guarantees:
        - Batches written transactionally (crash loses at most 1 batch).
        - Idempotent via worker_runs check and embedding IS NULL query.
        - Log pages/sec.
    """
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    embedder = ctx.get("embedder")
    settings = ctx.get("settings") or get_settings()

    if engine is None:
        engine = create_pool(settings.postgres_dsn)
    if embedder is None:
        embedder = Embedder()

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, doc_hash FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        doc_hash = str(doc["doc_hash"])

        # 1. Idempotency check via worker_runs
        run_res = await conn.execute(
            text(
                """
                SELECT status FROM worker_runs
                WHERE doc_hash = :hash AND worker_name = 'embed_pages' AND worker_version = :ver
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            # Also verify if any NULL embeddings remain
            remaining_res = await conn.execute(
                text("SELECT count(*) FROM document_pages WHERE doc_id = :id AND embedding IS NULL"),
                {"id": doc_id},
            )
            if (remaining_res.scalar() or 0) == 0:
                log.info("embed_pages already completed for document", doc_id=doc_id)
                return {"status": "already_ok", "embedded_count": 0}

        # 2. Fetch pages requiring embedding
        pages_res = await conn.execute(
            text(
                """
                SELECT id, page_index, page_text
                FROM document_pages
                WHERE doc_id = :id AND embedding IS NULL
                ORDER BY page_index ASC
                """
            ),
            {"id": doc_id},
        )
        pages_to_embed = pages_res.mappings().all()

        if not pages_to_embed:
            # Mark ok in worker_runs
            await conn.execute(
                text(
                    """
                    INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                    VALUES (:hash, 'embed_pages', :ver, 'ok', now())
                    ON CONFLICT (doc_hash, worker_name, worker_version)
                    DO UPDATE SET status = 'ok', finished_at = now();
                    """
                ),
                {"hash": doc_hash, "ver": WORKER_VERSION},
            )
            await conn.commit()
            log.info("No pages require embedding", doc_id=doc_id)
            return {"status": "already_ok", "embedded_count": 0}

        # 3. Check vector extension
        has_vector_res = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        has_vector = has_vector_res.first() is not None

        total_pages = len(pages_to_embed)
        log.info("Starting embedding for document pages", doc_id=doc_id, pages=total_pages, batch_size=batch_size)

        total_embedded = 0
        overall_start = time.perf_counter()

        # 4. Batch processing (per-batch transaction commit for crash resilience)
        for i in range(0, total_pages, batch_size):
            batch = pages_to_embed[i : i + batch_size]
            batch_texts = [p["page_text"] for p in batch]

            t_start = time.perf_counter()
            embeddings = await embedder.embed(batch_texts)
            elapsed = time.perf_counter() - t_start

            rate = len(batch) / elapsed if elapsed > 0 else 0.0
            log.info(
                "Embedded page batch",
                doc_id=doc_id,
                batch_start=i + 1,
                batch_size=len(batch),
                elapsed_s=round(elapsed, 3),
                pages_per_sec=round(rate, 1),
            )

            if has_vector:
                for p, emb in zip(batch, embeddings, strict=False):
                    emb_str = f"[{','.join(str(x) for x in emb)}]"
                    await conn.execute(
                        text(
                            """
                            UPDATE document_pages
                            SET embedding = CAST(:emb AS halfvec(1024))
                            WHERE id = :pid;
                            """
                        ),
                        {"emb": emb_str, "pid": p["id"]},
                    )
            else:
                for p, emb in zip(batch, embeddings, strict=False):
                    await conn.execute(
                        text(
                            """
                            UPDATE document_pages
                            SET embedding = :emb
                            WHERE id = :pid;
                            """
                        ),
                        {"emb": emb, "pid": p["id"]},
                    )
            await conn.commit()
            total_embedded += len(batch)

        # 5. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'embed_pages', :ver, 'ok', now())
                ON CONFLICT (doc_hash, worker_name, worker_version)
                DO UPDATE SET status = 'ok', finished_at = now();
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        await conn.commit()

        total_elapsed = time.perf_counter() - overall_start
        overall_rate = total_embedded / total_elapsed if total_elapsed > 0 else 0.0
        log.info(
            "Completed page embeddings for document",
            doc_id=doc_id,
            total_pages=total_embedded,
            elapsed_s=round(total_elapsed, 3),
            overall_pages_per_sec=round(overall_rate, 1),
        )

        return {
            "status": "ok",
            "embedded_count": total_embedded,
            "elapsed_s": total_elapsed,
            "pages_per_sec": overall_rate,
        }
