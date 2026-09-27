"""Worker task: xbrl_sidecar fast path ingestion for XBRL instance documents."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.extraction.xbrl import parse_xbrl
from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger("ingest.xbrl_sidecar")
WORKER_VERSION = "1.0"


async def xbrl_sidecar(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Parses XBRL sidecar XML and writes facts with 1.0 confidence, superseding PDF extractions."""
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
                "SELECT status FROM worker_runs WHERE doc_hash = :hash AND worker_name = 'xbrl_sidecar' AND worker_version = :ver"
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        existing_run = run_res.mappings().first()
        if existing_run and existing_run["status"] == "ok":
            log.info("xbrl_sidecar already completed for document", doc_id=doc_id)
            return {"status": "already_ok"}

        # 2. Check if .xbrl.xml exists in MinIO
        xbrl_key = f"{minio_key}.xbrl.xml"
        try:
            xbrl_resp = minio_client.get_object(settings.minio_bucket_raw, xbrl_key)
            xbrl_bytes = xbrl_resp.read()
            xbrl_resp.close()
            xbrl_resp.release_conn()
        except Exception:
            log.info("No XBRL sidecar found for document; bypassing fast path", doc_id=doc_id)
            return {"xbrl_present": False}

        # 3. Parse XBRL instance facts
        extracted_facts = parse_xbrl(xbrl_bytes)
        if not extracted_facts:
            return {"xbrl_present": True, "facts": 0}

        # 4. Fetch XBRL alias taxonomy mapping
        alias_res = await conn.execute(
            text("SELECT taxonomy_concept, canonical_concept_id FROM xbrl_alias")
        )
        alias_map = {r["taxonomy_concept"]: r["canonical_concept_id"] for r in alias_res.mappings()}

        # 5. Insert facts into financial_facts table
        inserted_count = 0
        for f in extracted_facts:
            canonical_id = alias_map.get(f.concept_local)
            if not canonical_id:
                # Try matching by local suffix
                local_suffix = f.concept_local.split("/")[-1]
                for tax_uri, c_id in alias_map.items():
                    if tax_uri.endswith(local_suffix):
                        canonical_id = c_id
                        break

            if not canonical_id:
                canonical_id = f"xbrl:{f.concept_local.split('/')[-1]}"

            statement = "IS"
            if any(
                k in canonical_id.lower()
                for k in ("asset", "liabilit", "equity", "cash", "deposit", "loan")
            ):
                statement = "BS"

            insert_sql = """
            INSERT INTO financial_facts (
                ticker, period_end, fiscal_period, statement, concept_id, concept_local,
                value_numeric, unit, is_restated, period_type, source_doc_id,
                source_page, source_bbox, extraction_method, extraction_conf, needs_review
            ) VALUES (
                :ticker, :period_end, :fiscal_period, :statement, :concept_id, :concept_local,
                :value_numeric, :unit, false, :period_type, :source_doc_id,
                0, '[0, 0, 0, 0]'::jsonb, 'xbrl', 1.0, false
            )
            ON CONFLICT (ticker, fiscal_period, concept_id, (coalesce(segment, '{}'::jsonb))) WHERE is_restated = false
            DO UPDATE SET
                value_numeric = EXCLUDED.value_numeric,
                unit = EXCLUDED.unit,
                extraction_method = 'xbrl',
                extraction_conf = 1.0,
                needs_review = false
            WHERE financial_facts.extraction_conf < 1.0;
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
                },
            )
            inserted_count += 1

        if inserted_count > 0:
            await conn.execute(
                text("UPDATE documents SET status = 'facts_extracted' WHERE id = :id"),
                {"id": doc_id},
            )

        # 6. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'xbrl_sidecar', :ver, 'ok', now())
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

        log.info("xbrl_sidecar completed", doc_id=doc_id, facts=inserted_count)
        return {"xbrl_present": True, "facts": inserted_count}
