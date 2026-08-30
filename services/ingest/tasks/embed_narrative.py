"""Worker task for translating and embedding narrative chunks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.narrative.embedder import Embedder
from services.narrative.translator import translate
from services.shared.logging import get_logger

log = get_logger(__name__)

WORKER_VERSION = "1.0"


async def embed_narrative_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Translates non-English chunks and computes 1024-dim BGE-M3 embeddings."""
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    if engine is None:
        raise RuntimeError("Worker context missing database pool.")

    embedder = ctx.get("embedder") or Embedder()

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, doc_hash FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        doc_hash = doc["doc_hash"]

        # 1. Idempotency check
        run_res = await conn.execute(
            text(
                """
                SELECT status FROM worker_runs
                WHERE doc_hash = :hash AND worker_name = 'embed_narrative' AND worker_version = :ver
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("embed_narrative already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        # 2. Fetch chunks requiring translation or embedding
        c_res = await conn.execute(
            text(
                """
                SELECT id, text_original, text_en, language
                FROM narrative_chunks
                WHERE source_doc_id = :id;
                """
            ),
            {"id": doc_id},
        )
        chunks = c_res.mappings().all()

        if not chunks:
            log.info("No narrative chunks found for embedding", doc_id=doc_id)
            return {"status": "ok", "embedded_count": 0}

        # 3. Translate where necessary
        texts_to_embed: list[str] = []

        # Prepare translation inputs
        needs_translation_indices: list[int] = []
        texts_for_translation: list[str] = []

        for idx, c in enumerate(chunks):
            if c["text_en"]:
                en_text = c["text_en"]
            elif c["language"] == "en":
                en_text = c["text_original"]
            else:
                en_text = ""
                needs_translation_indices.append(idx)
                texts_for_translation.append(c["text_original"])

            texts_to_embed.append(en_text)

        if texts_for_translation:
            translated = await translate(texts_for_translation)
            for orig_idx, trans_text in zip(needs_translation_indices, translated, strict=False):
                texts_to_embed[orig_idx] = trans_text

        # 4. Generate embeddings
        embeddings = await embedder.embed(texts_to_embed)

        # 5. Check if vector extension is enabled in database
        has_vector_res = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        has_vector = has_vector_res.first() is not None

        # 6. Update narrative_chunks
        for c, en_text, emb in zip(chunks, texts_to_embed, embeddings, strict=False):
            if has_vector:
                emb_str = f"[{','.join(str(x) for x in emb)}]"
                await conn.execute(
                    text(
                        """
                        UPDATE narrative_chunks
                        SET text_en = :en,
                            embedding = CAST(:emb AS halfvec(1024))
                        WHERE id = :cid;
                        """
                    ),
                    {"en": en_text, "emb": emb_str, "cid": c["id"]},
                )
            else:
                await conn.execute(
                    text(
                        """
                        UPDATE narrative_chunks
                        SET text_en = :en
                        WHERE id = :cid;
                        """
                    ),
                    {"en": en_text, "cid": c["id"]},
                )

        # 7. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'embed_narrative', :ver, 'ok', now())
                ON CONFLICT (doc_hash, worker_name, worker_version)
                DO UPDATE SET status = 'ok', finished_at = now();
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        await conn.commit()

    log.info("Embedded narrative chunks successfully", doc_id=doc_id, count=len(chunks))
    return {"status": "ok", "embedded_count": len(chunks)}
