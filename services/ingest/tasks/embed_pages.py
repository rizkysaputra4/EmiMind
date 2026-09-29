"""Worker task for computing and storing dense page embeddings (bge-m3)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.narrative.embedder import Embedder
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("ingest.embed_pages")
WORKER_NAME = "embed_pages"
WORKER_VERSION = "2.0"
DEFAULT_BATCH_SIZE = 32

# Pages whose vector is missing, of unknown origin (NULL model = legacy md5 hash vectors),
# or produced by a different model than the current embedder.
_COUNT_STALE_SQL = text(
    "SELECT count(*) FROM document_pages WHERE doc_id = :id "
    "AND (embedding IS NULL OR embedding_model IS DISTINCT FROM :model)"
)
_SELECT_STALE_SQL = text(
    """
    SELECT id, page_index, page_text, md5(page_text) AS text_md5
    FROM document_pages
    WHERE doc_id = :id AND (embedding IS NULL OR embedding_model IS DISTINCT FROM :model)
    ORDER BY page_index ASC
    """
)
# The md5 guard: a page re-indexed after it was read keeps its (now stale) state.
_UPDATE_FLOAT_SQL = text(
    """
    UPDATE document_pages SET embedding = :emb, embedding_model = :model
    WHERE id = :pid AND md5(page_text) = :text_md5
    """
)
_UPDATE_HALFVEC_SQL = text(
    """
    UPDATE document_pages SET embedding = CAST(:emb AS halfvec(1024)), embedding_model = :model
    WHERE id = :pid AND md5(page_text) = :text_md5
    """
)


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


async def count_stale_pages(conn: AsyncConnection, doc_id: str, model_id: str) -> int:
    res = await conn.execute(
        _COUNT_STALE_SQL, {"id": doc_id, "model": model_id}
    )
    return int(res.scalar() or 0)


async def embed_pages_task(
    ctx: dict[str, Any],
    doc_id: str,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Embeds every page of a document whose vector is missing or from another model.

    Guarantees:
      - Each batch (default 32 pages) is committed on its own, so a crash loses at most one
        batch; the next run resumes from the pages still stale.
      - Writes `embedding` and `embedding_model` together. The UPDATE is guarded by the md5 of
        the page text that was embedded, so a page re-indexed meanwhile is never clobbered
        with a vector of its old text (it simply stays stale).
      - Embedder failures propagate (no fake vectors); worker_runs records 'failed'.
    """
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    embedder: Any = ctx.get("embedder") or Embedder()
    settings = ctx.get("settings") or get_settings()
    batch = int(batch_size or ctx.get("batch_size") or DEFAULT_BATCH_SIZE)
    # duck-typed test embedders may lack model_id; their class name then identifies the vectors
    model_id = str(getattr(embedder, "model_id", None) or type(embedder).__name__)

    if engine is None:
        engine = create_pool(settings.postgres_dsn)

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, doc_hash FROM documents WHERE id = :id"), {"id": doc_id}
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")
        doc_hash = str(doc["doc_hash"])

        pages_res = await conn.execute(_SELECT_STALE_SQL, {"id": doc_id, "model": model_id})
        pages_to_embed = pages_res.mappings().all()

        if not pages_to_embed:
            total_res = await conn.execute(
                text("SELECT count(*) FROM document_pages WHERE doc_id = :id"), {"id": doc_id}
            )
            if int(total_res.scalar() or 0) == 0:
                log.warning("Document has no indexed pages; nothing to embed", doc_id=doc_id)
                return {"status": "not_indexed", "embedded_count": 0, "model": model_id}
            await _set_run_status(conn, doc_hash, "ok")
            await conn.commit()
            log.info("No pages require embedding", doc_id=doc_id, model=model_id)
            return {"status": "already_ok", "embedded_count": 0, "model": model_id}

        has_vector_res = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        has_vector = has_vector_res.first() is not None
        update_sql = _UPDATE_HALFVEC_SQL if has_vector else _UPDATE_FLOAT_SQL

        total_pages = len(pages_to_embed)
        log.info(
            "Starting embedding for document pages",
            doc_id=doc_id,
            pages=total_pages,
            batch_size=batch,
            model=model_id,
            device=getattr(embedder, "device", None),
        )
        await _set_run_status(conn, doc_hash, "running")
        await conn.commit()

        total_embedded = 0
        skipped_changed = 0
        overall_start = time.perf_counter()
        try:
            for i in range(0, total_pages, batch):
                rows = pages_to_embed[i : i + batch]
                t_start = time.perf_counter()
                vectors = await embedder.embed([str(p["page_text"] or "") for p in rows])
                if len(vectors) != len(rows):
                    raise RuntimeError(
                        f"Embedder returned {len(vectors)} vectors for {len(rows)} pages"
                    )
                elapsed = time.perf_counter() - t_start

                for p, vec in zip(rows, vectors, strict=True):
                    emb: Any = f"[{','.join(repr(float(x)) for x in vec)}]" if has_vector else vec
                    upd = await conn.execute(
                        update_sql,
                        {"emb": emb, "model": model_id, "pid": p["id"], "text_md5": p["text_md5"]},
                    )
                    if (getattr(upd, "rowcount", 1) or 0) == 0:
                        skipped_changed += 1
                    else:
                        total_embedded += 1
                await conn.commit()
                log.info(
                    "Embedded page batch",
                    doc_id=doc_id,
                    batch_start=i + 1,
                    batch_size=len(rows),
                    elapsed_s=round(elapsed, 3),
                    pages_per_sec=round(len(rows) / elapsed, 1) if elapsed > 0 else None,
                )
        except Exception as exc:
            await conn.rollback()
            await _set_run_status(conn, doc_hash, "failed", f"{type(exc).__name__}: {exc}")
            await conn.commit()
            log.error("embed_pages failed", doc_id=doc_id, error=str(exc))
            raise

        remaining = await count_stale_pages(conn, doc_id, model_id)
        await _set_run_status(
            conn,
            doc_hash,
            "ok" if remaining == 0 else "failed",
            None if remaining == 0 else f"{remaining} pages still stale (re-indexed during run)",
        )
        await conn.commit()

    total_elapsed = time.perf_counter() - overall_start
    overall_rate = total_embedded / total_elapsed if total_elapsed > 0 else 0.0
    log.info(
        "Completed page embeddings for document",
        doc_id=doc_id,
        total_pages=total_embedded,
        skipped_changed=skipped_changed,
        elapsed_s=round(total_elapsed, 3),
        overall_pages_per_sec=round(overall_rate, 1),
    )
    return {
        "status": "ok" if remaining == 0 else "partial",
        "embedded_count": total_embedded,
        "skipped_changed": skipped_changed,
        "remaining": remaining,
        "model": model_id,
        "elapsed_s": total_elapsed,
        "pages_per_sec": overall_rate,
    }
