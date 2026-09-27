"""Worker task: normalize_facts maps extracted tables to canonical financial facts."""

from __future__ import annotations

import io
import json
from typing import Any

import polars as pl
from sqlalchemy import text

from services.extraction.concepts import fuzzy_match_concept
from services.extraction.tables import tables_to_facts
from services.shared.config import get_settings
from services.shared.errors import ConceptMappingError
from services.shared.logging import get_logger
from services.shared.types import BBox, ExtractedTable, TableCell

log = get_logger("ingest.normalize_facts")
WORKER_VERSION = "1.0"


async def normalize_facts_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Normalizes tables.parquet into canonical financial_facts and flags unmapped concepts."""
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    minio_client = ctx.get("minio_client") or ctx.get("minio")
    if engine is None or minio_client is None:
        raise RuntimeError("Worker context missing database pool or MinIO client.")
    settings = get_settings()

    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                "SELECT id, ticker, period_end, fiscal_period, doc_hash, minio_key FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        ticker = doc["ticker"]
        period_end = doc["period_end"]
        fiscal_period = doc["fiscal_period"]
        doc_hash = doc["doc_hash"]
        minio_key = doc["minio_key"]

        # 1. Idempotency check
        run_res = await conn.execute(
            text(
                "SELECT status FROM worker_runs WHERE doc_hash = :hash AND worker_name = 'normalize_facts' AND worker_version = :ver"
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("normalize_facts already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        # 2. Read tables.parquet from MinIO
        tables_key = f"{minio_key}.tables.parquet"
        try:
            parquet_resp = minio_client.get_object(settings.minio_bucket_raw, tables_key)
            parquet_bytes = parquet_resp.read()
            parquet_resp.close()
            parquet_resp.release_conn()
        except Exception:
            log.warning("No tables.parquet found; skipping table normalization", doc_id=doc_id)
            return {"facts": 0, "reviews_queued": 0}

        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        if df.is_empty():
            log.info("tables.parquet is empty for document", doc_id=doc_id)
            return {"facts": 0, "reviews_queued": 0}

        # Reconstruct ExtractedTable objects
        tables_by_idx: dict[int, dict[str, Any]] = {}
        for row in df.iter_rows(named=True):
            t_idx = row["table_idx"]
            if t_idx not in tables_by_idx:
                tables_by_idx[t_idx] = {
                    "page_num": row["page_num"],
                    "extraction_method": row["extraction_method"],
                    "confidence": row["table_confidence"],
                    "cells": [],
                }
            tables_by_idx[t_idx]["cells"].append(
                TableCell(
                    row=row["row"],
                    col=row["col"],
                    text=row["text"],
                    bbox=BBox(row["bbox_x0"], row["bbox_y0"], row["bbox_x1"], row["bbox_y1"]),
                    confidence=row["cell_confidence"],
                )
            )

        extracted_tables = [
            ExtractedTable(
                page_num=t["page_num"],
                cells=t["cells"],
                extraction_method=t["extraction_method"],
                confidence=t["confidence"],
            )
            for t in tables_by_idx.values()
        ]

        # 3. Fetch candidate concepts from concept_map
        concept_res = await conn.execute(
            text("SELECT local_label, canonical_concept_id, sector FROM concept_map")
        )
        candidates = [
            (r["local_label"], r["canonical_concept_id"], r["sector"])
            for r in concept_res.mappings()
        ]

        # 4. Convert tables to raw facts
        raw_facts = tables_to_facts(
            tables=extracted_tables,
            sector=None,
            ticker=ticker,
            fiscal_period=fiscal_period,
            doc_id=doc_id,
        )

        inserted_facts = 0
        reviews_queued = 0

        for f in raw_facts:
            needs_review = f.confidence < 0.70
            try:
                canonical_id, map_conf = fuzzy_match_concept(f.concept_local, candidates)
                combined_conf = min(f.confidence, map_conf)
                if combined_conf < 0.70:
                    needs_review = True
            except ConceptMappingError:
                canonical_id = f"UNMAPPED:{f.concept_local}"
                combined_conf = f.confidence * 0.5
                needs_review = True

                # Insert into review queue
                await conn.execute(
                    text(
                        """
                        INSERT INTO concept_review (ticker, doc_id, local_label, status)
                        VALUES (:ticker, :doc_id, :label, 'open')
                        ON CONFLICT (ticker, doc_id, local_label) DO NOTHING;
                        """
                    ),
                    {"ticker": ticker, "doc_id": doc_id, "label": f.concept_local},
                )
                reviews_queued += 1

            statement = "IS"
            if any(
                k in canonical_id.lower()
                for k in ("asset", "liabilit", "equity", "cash", "deposit", "loan")
            ):
                statement = "BS"

            bbox_json = json.dumps(
                [f.source_bbox.x0, f.source_bbox.y0, f.source_bbox.x1, f.source_bbox.y1]
            )

            insert_sql = """
            INSERT INTO financial_facts (
                ticker, period_end, fiscal_period, statement, concept_id, concept_local,
                value_numeric, unit, is_restated, period_type, source_doc_id,
                source_page, source_bbox, extraction_method, extraction_conf, needs_review
            ) VALUES (
                :ticker, :period_end, :fiscal_period, :statement, :concept_id, :concept_local,
                :value_numeric, :unit, false, :period_type, :source_doc_id,
                :source_page, CAST(:source_bbox AS jsonb), :method, :extraction_conf, :needs_review
            )
            ON CONFLICT (ticker, fiscal_period, concept_id, (coalesce(segment, '{}'::jsonb))) WHERE is_restated = false
            DO UPDATE SET
                value_numeric = EXCLUDED.value_numeric,
                unit = EXCLUDED.unit,
                source_page = EXCLUDED.source_page,
                source_bbox = EXCLUDED.source_bbox,
                extraction_method = EXCLUDED.extraction_method,
                extraction_conf = EXCLUDED.extraction_conf,
                needs_review = EXCLUDED.needs_review
            WHERE financial_facts.extraction_conf < EXCLUDED.extraction_conf;
            """

            await conn.execute(
                text(insert_sql),
                {
                    "ticker": ticker,
                    "period_end": period_end,
                    "fiscal_period": fiscal_period,
                    "statement": statement,
                    "concept_id": canonical_id,
                    "concept_local": f.concept_local,
                    "value_numeric": f.value_numeric,
                    "unit": f.unit,
                    "period_type": f.period_type,
                    "source_doc_id": doc_id,
                    "source_page": f.source_page,
                    "source_bbox": bbox_json,
                    "method": f.method,
                    "extraction_conf": combined_conf,
                    "needs_review": needs_review,
                },
            )
            inserted_facts += 1

        if inserted_facts > 0:
            await conn.execute(
                text("UPDATE documents SET status = 'facts_extracted' WHERE id = :id"),
                {"id": doc_id},
            )

        # 5. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'normalize_facts', :ver, 'ok', now())
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

        log.info(
            "normalize_facts completed",
            doc_id=doc_id,
            facts=inserted_facts,
            reviews_queued=reviews_queued,
        )
        return {"facts": inserted_facts, "reviews_queued": reviews_queued}
