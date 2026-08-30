"""EMIMIND Model Context Protocol (MCP) Ingestion and Validation Server."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import text

from services.derive.engine import compute_for_document
from services.derive.valuation import calculate_valuation
from services.ingest.tasks.refresh_profile import refresh_profile_task
from services.mcp.contracts import build_extraction_contract
from services.mcp.types import (
    CommitReport,
    DocumentInspectionResult,
    DraftSubmissionPayload,
    ExtractionContract,
    InspectionStatus,
    ValidationReport,
)
from services.mcp.validator import validate_draft_submission
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import shutil

from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger("mcp.server")


def _archive_processed_file(file_path_str: str) -> str | None:
    """Moves a processed file to a 'processed/' subfolder if located in incoming_reports/."""
    try:
        p = Path(file_path_str).resolve()
        if p.exists() and p.is_file() and "incoming_reports" in p.parts and "processed" not in p.parts:
            processed_dir = p.parent / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            target_path = processed_dir / p.name
            shutil.move(str(p), str(target_path))
            log.info("Archived file to processed directory", src=str(p), dest=str(target_path))
            return str(target_path)
    except Exception as e:
        log.warning("Failed to move processed file to archive", error=str(e))
    return None


def get_engine():
    settings = get_settings()
    return create_async_engine(
        settings.postgres_dsn,
        poolclass=NullPool,
        connect_args={"server_settings": {"statement_timeout": "5000ms"}},
    )

# Instantiate MCPServer
mcp = MCPServer(
    name="emimind-ingestion-server",
    instructions=(
        "You are connected to the EMIMIND Financial Intelligence MCP Authority Server. "
        "Before extracting PDF financial statements, inspect the document and retrieve the extraction contract. "
        "Submit draft extractions for multi-tier accounting validation before final commit."
    ),
)


@mcp.tool()
async def inspect_document(
    file_path: str,
    ticker: str | None = None,
    fiscal_period: str | None = None,
    doc_type: str = "FS_QUARTERLY",
) -> DocumentInspectionResult:
    """Inspects a PDF document by computing its SHA-256 fingerprint and checking processing status in EMIMIND."""
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return DocumentInspectionResult(
            status=InspectionStatus.ERROR,
            doc_hash="",
            message=f"File not found on disk at path: {file_path}",
        )

    # Compute SHA-256 hash of raw file bytes
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    doc_hash = hasher.hexdigest()

    engine = get_engine()
    async with engine.connect() as conn:
        # Check if hash already exists in documents
        res = await conn.execute(
            text("SELECT id, ticker, fiscal_period, doc_type, status FROM documents WHERE doc_hash = :hash"),
            {"hash": doc_hash},
        )
        doc = res.mappings().first()

        if doc:
            t = doc["ticker"]
            fp = doc["fiscal_period"]
            d_id = str(doc["id"])

            # Check if facts are already extracted
            f_res = await conn.execute(
                text("SELECT count(*) FROM financial_facts WHERE source_doc_id = :d_id"),
                {"d_id": d_id},
            )
            facts_count = f_res.scalar() or 0

            if facts_count > 0 and doc["status"] in ("parsed", "facts_extracted"):
                # Archive to processed subfolder if located in incoming_reports
                new_path = _archive_processed_file(str(p))
                return DocumentInspectionResult(
                    status=InspectionStatus.ALREADY_PROCESSED,
                    doc_hash=doc_hash,
                    doc_id=d_id,
                    ticker=t,
                    fiscal_period=fp,
                    doc_type=doc["doc_type"],
                    message=f"Document already fully processed and committed to database with {facts_count} financial facts. File moved to processed/ archive.",
                    existing_facts_count=facts_count,
                )

        # Resolve ticker and fiscal period from metadata or filename if not provided
        t_clean = (ticker or (p.stem.split("_")[0] if "_" in p.stem else "UNKNOWN")).upper()
        fp_clean = (fiscal_period or ("2024Q4" if "Q" not in p.stem else p.stem.split("_")[1])).upper()

        # Fetch sector and company name
        sec_res = await conn.execute(
            text("SELECT name, sector, sub_sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
            {"ticker": t_clean},
        )
        sec_row = sec_res.mappings().first()
        company_name = sec_row["name"] if sec_row and sec_row.get("name") else f"PT {t_clean} Tbk"
        sector_name = sec_row["sector"] if sec_row and sec_row.get("sector") else "GENERIC"

        # Register document if new
        if not doc:
            doc_uuid = uuid.uuid4()
            d_id = str(doc_uuid)
            minio_key = f"raw/{doc_type}/{t_clean}/{fp_clean}/{p.name}"
            await conn.execute(
                text(
                    """
                    INSERT INTO documents (id, ticker, doc_type, period_end, fiscal_period, language, source_url, minio_key, doc_hash, page_count, status)
                    VALUES (:id, :ticker, :doc_type, '2024-12-31', :fiscal_period, 'id', :url, :minio_key, :doc_hash, 1, 'raw')
                    ON CONFLICT (doc_hash) DO NOTHING;
                    """
                ),
                {
                    "id": d_id,
                    "ticker": t_clean,
                    "doc_type": doc_type,
                    "fiscal_period": fp_clean,
                    "url": str(p),
                    "minio_key": minio_key,
                    "doc_hash": doc_hash,
                },
            )
            await conn.commit()
        else:
            d_id = str(doc["id"])

        return DocumentInspectionResult(
            status=InspectionStatus.AUTHORIZED,
            doc_hash=doc_hash,
            doc_id=d_id,
            ticker=t_clean,
            fiscal_period=fp_clean,
            doc_type=doc_type,
            company_name=company_name,
            sector=sector_name,
            message="Document authorized for extraction. Call get_extraction_contract(doc_id) to receive extraction schema and sector guidelines.",
            existing_facts_count=0,
        )


@mcp.tool()
async def get_extraction_contract(doc_id: str) -> ExtractionContract:
    """Retrieves the dynamic extraction contract, required concepts, and scaling rules for a document."""
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, ticker, fiscal_period, doc_type FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document with ID {doc_id} not found in database.")

        ticker = doc["ticker"]
        fiscal_period = doc["fiscal_period"]

        sec_res = await conn.execute(
            text("SELECT name, sector, sub_sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
            {"ticker": ticker},
        )
        sec_row = sec_res.mappings().first()
        company_name = sec_row["name"] if sec_row and sec_row.get("name") else f"PT {ticker} Tbk"
        sector_name = sec_row["sector"] if sec_row and sec_row.get("sector") else "GENERIC"

        return build_extraction_contract(
            doc_id=str(doc_id),
            ticker=ticker,
            company_name=company_name,
            sector=sector_name,
            fiscal_period=fiscal_period,
        )


@mcp.tool()
async def submit_draft_extraction(payload_json: str, retry_attempt: int = 1) -> ValidationReport:
    """Validates a draft extraction payload against schema, accounting math equations, and unit scaling."""
    try:
        data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        payload = DraftSubmissionPayload.model_validate(data)
    except Exception as e:
        return ValidationReport(
            status="INVALID",
            submission_id=f"err_{uuid.uuid4().hex[:8]}",
            doc_id="UNKNOWN",
            ticker="UNKNOWN",
            fiscal_period="UNKNOWN",
            errors_count=1,
            warnings_count=0,
            can_retry=True,
            retry_attempt=retry_attempt,
            max_retries=3,
            issues=[
                {
                    "severity": "ERROR",
                    "category": "MALFORMED_JSON_SCHEMA",
                    "feedback_message": f"Failed to parse draft submission payload: {e}",
                    "target_pages": [],
                }
            ],
        )

    engine = get_engine()
    sector = "GENERIC"
    async with engine.connect() as conn:
        sec_res = await conn.execute(
            text("SELECT sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
            {"ticker": payload.ticker.upper()},
        )
        sec_row = sec_res.mappings().first()
        if sec_row and sec_row.get("sector"):
            sector = sec_row["sector"]

    report = validate_draft_submission(payload, sector=sector, retry_attempt=retry_attempt)

    # If invalid after 3 attempts, log to review_queue
    if report.status == "INVALID" and retry_attempt >= 3:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO ingest_review_queue (
                        ticker, fiscal_period, doc_id, issue_type, severity, validation_report, draft_payload, status
                    ) VALUES (
                        :ticker, :period, :doc_id, :issue, 'ERROR', CAST(:rep AS jsonb), CAST(:draft AS jsonb), 'PENDING'
                    );
                    """
                ),
                {
                    "ticker": payload.ticker.upper(),
                    "period": payload.fiscal_period.upper(),
                    "doc_id": payload.doc_id,
                    "issue": "MAX_RETRIES_EXHAUSTED",
                    "rep": json.dumps(report.model_dump(mode="json")),
                    "draft": json.dumps(payload.model_dump(mode="json")),
                },
            )
            await conn.commit()

    return report


@mcp.tool()
async def commit_verified_report(payload_json: str) -> CommitReport:
    """Commits verified financial facts, narrative chunks, and guidance to the database and runs the derive engine."""
    data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    payload = DraftSubmissionPayload.model_validate(data)

    engine = get_engine()
    doc_id = payload.doc_id
    ticker = payload.ticker.upper()
    fiscal_period = payload.fiscal_period.upper()

    # Derive period_end date object
    from datetime import date

    year_int = int(fiscal_period[:4]) if len(fiscal_period) >= 4 and fiscal_period[:4].isdigit() else 2024
    if "Q1" in fiscal_period:
        period_end_dt = date(year_int, 3, 31)
    elif "Q2" in fiscal_period:
        period_end_dt = date(year_int, 6, 30)
    elif "Q3" in fiscal_period:
        period_end_dt = date(year_int, 9, 30)
    else:
        period_end_dt = date(year_int, 12, 31)

    async with engine.connect() as conn:
        # 1. Insert/update financial_facts
        facts_count = 0
        for f in payload.facts:
            cid = f.concept_id
            if any(k in cid for k in ("Assets", "Liabilities", "Equity", "Cash", "Loans", "Deposits", "Inventories", "Receivables", "Borrowings")):
                stmt_type = "BS"
                p_type = "instant"
            elif any(k in cid for k in ("Revenue", "CostOfSales", "GrossProfit", "OperatingProfit", "ProfitLoss", "InterestIncome", "FinanceCosts")):
                stmt_type = "IS"
                p_type = "duration_ytd"
            elif "CashFlows" in cid or "PaymentsToAcquire" in cid:
                stmt_type = "CF"
                p_type = "duration_ytd"
            else:
                stmt_type = "NOTE"
                p_type = f.period_type or "instant"

            await conn.execute(
                text(
                    """
                    INSERT INTO financial_facts (
                        source_doc_id, ticker, period_end, fiscal_period, statement, concept_id, concept_local,
                        value_numeric, unit, period_type, accounting_std, source_page, extraction_conf, extraction_method
                    ) VALUES (
                        :doc_id, :ticker, :period_end, :period, :statement, :concept_id, :label,
                        :val, :unit, :period_type, :std, :page, 0.95, 'llm_extract'
                    )
                    ON CONFLICT (ticker, fiscal_period, concept_id, (coalesce(segment->>'segment','')))
                    WHERE is_restated = false
                    DO UPDATE SET
                        value_numeric = EXCLUDED.value_numeric,
                        unit = EXCLUDED.unit,
                        source_page = EXCLUDED.source_page,
                        source_doc_id = EXCLUDED.source_doc_id,
                        extraction_method = 'llm_extract',
                        extraction_conf = 0.95;
                    """
                ),
                {
                    "doc_id": doc_id,
                    "ticker": ticker,
                    "period_end": period_end_dt,
                    "period": fiscal_period,
                    "statement": stmt_type,
                    "concept_id": cid,
                    "label": f.source_label_original or cid,
                    "val": float(f.value_numeric),
                    "unit": f.unit,
                    "period_type": p_type,
                    "std": payload.accounting_standard,
                    "page": f.source_page,
                },
            )
            facts_count += 1

        # 2. Insert narrative chunks
        narratives_count = 0
        valid_sections = {"MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"}
        if payload.narratives:
            for n in payload.narratives:
                sec = n.section.upper() if n.section.upper() in valid_sections else "OTHER"
                await conn.execute(
                    text(
                        """
                        INSERT INTO narrative_chunks (
                            source_doc_id, ticker, period_end, fiscal_period, section, source_page, text_original, text_en, tsv
                        ) VALUES (
                            :doc_id, :ticker, :period_end, :period, :sec, :page, :orig, :en, to_tsvector('simple', :orig)
                        );
                        """
                    ),
                    {
                        "doc_id": doc_id,
                        "ticker": ticker,
                        "period_end": period_end_dt,
                        "period": fiscal_period,
                        "sec": sec,
                        "page": n.source_page,
                        "orig": n.text_original,
                        "en": n.text_en or n.text_original,
                    },
                )
                narratives_count += 1
        else:
            # Automatic narrative chunking fallback from local PDF file
            doc_file_res = await conn.execute(text("SELECT source_url FROM documents WHERE id = :id"), {"id": doc_id})
            doc_f = doc_file_res.mappings().first()
            candidate_paths: list[Path] = []
            if doc_f and doc_f.get("source_url"):
                candidate_paths.append(Path(doc_f["source_url"]))
                candidate_paths.append(Path(doc_f["source_url"]).parent / "processed" / Path(doc_f["source_url"]).name)

            for p in Path("incoming_reports/processed").glob(f"*{ticker}*.pdf"):
                candidate_paths.append(p)
            for p in Path("incoming_reports").glob(f"*{ticker}*.pdf"):
                candidate_paths.append(p)

            for cand in candidate_paths:
                if cand.exists() and cand.is_file():
                    try:
                        import pymupdf
                        from services.narrative.chunker import chunk_pages
                        from services.shared.types import PageContent

                        pdf_doc = pymupdf.open(str(cand))
                        pdf_pages = []
                        for i, pg in enumerate(pdf_doc):
                            txt = pg.get_text("text")
                            pdf_pages.append(PageContent(page_num=i + 1, text=txt, language="mixed", has_text_layer=True))
                        pdf_doc.close()

                        auto_chunks = chunk_pages(pdf_pages, ticker, "FS_ANNUAL", fiscal_period)
                        for c in auto_chunks:
                            sec = c.section if c.section in valid_sections else "OTHER"
                            await conn.execute(
                                text(
                                    """
                                    INSERT INTO narrative_chunks (
                                        source_doc_id, ticker, period_end, fiscal_period, section, source_page,
                                        language, text_original, text_en, speaker, claim_type, mentioned_concepts, tsv
                                    ) VALUES (
                                        :doc_id, :ticker, :period_end, :period, :sec, :page,
                                        :lang, :orig, :en, :speaker, :claim, :concepts, to_tsvector('simple', :orig)
                                    );
                                    """
                                ),
                                {
                                    "doc_id": doc_id,
                                    "ticker": ticker,
                                    "period_end": period_end_dt,
                                    "period": fiscal_period,
                                    "sec": sec,
                                    "page": c.source_page,
                                    "lang": c.language,
                                    "orig": c.text_original,
                                    "en": c.text_en or c.text_original,
                                    "speaker": c.speaker,
                                    "claim": c.claim_type,
                                    "concepts": c.mentioned_concepts or [],
                                },
                            )
                            narratives_count += 1
                        log.info("Auto-extracted narrative chunks from PDF", count=narratives_count, path=str(cand))
                        break
                    except Exception as e:
                        log.warning("Automatic fallback narrative chunking failed", error=str(e), path=str(cand))

        # 2.5 Insert Causal Links into Knowledge Graph (kg_nodes & kg_edges)
        causal_count = 0
        for cl in payload.causal_links:
            # 1. Insert Metric Node (DST)
            metric_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref)
                    VALUES ('METRIC', :ticker, :period, CAST(:payload AS jsonb), CAST(:src AS jsonb))
                    RETURNING id;
                    """
                ),
                {
                    "ticker": ticker,
                    "period": fiscal_period,
                    "payload": json.dumps({"metric": cl.metric_affected, "direction": cl.direction}),
                    "src": json.dumps({"doc_id": doc_id, "page": cl.source_page}),
                },
            )
            metric_node_id = metric_res.scalar()

            # 2. Insert Cause Claim Node (SRC)
            cause_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref)
                    VALUES ('CLAIM', :ticker, :period, CAST(:payload AS jsonb), CAST(:src AS jsonb))
                    RETURNING id;
                    """
                ),
                {
                    "ticker": ticker,
                    "period": fiscal_period,
                    "payload": json.dumps({"driver": cl.driver_description, "category": cl.cause_category}),
                    "src": json.dumps({"doc_id": doc_id, "page": cl.source_page}),
                },
            )
            cause_node_id = cause_res.scalar()

            # 3. Insert Edge: Cause -> CAUSED_BY -> Metric
            if metric_node_id and cause_node_id:
                await conn.execute(
                    text(
                        """
                        INSERT INTO kg_edges (src_id, dst_id, edge_type, confidence, evidence_ref, payload)
                        VALUES (:src, :dst, 'CAUSED_BY', :conf, CAST(:evidence AS jsonb), CAST(:pld AS jsonb));
                        """
                    ),
                    {
                        "src": cause_node_id,
                        "dst": metric_node_id,
                        "conf": cl.confidence,
                        "evidence": json.dumps({"citation": f"[{ticker}-FS-{fiscal_period}#p{cl.source_page}]"}),
                        "pld": json.dumps({"category": cl.cause_category}),
                    },
                )
                causal_count += 1

        # 3. Update document status and archive local file if in incoming folder
        doc_res = await conn.execute(text("SELECT source_url FROM documents WHERE id = :id"), {"id": doc_id})
        doc_row = doc_res.mappings().first()
        if doc_row and doc_row.get("source_url"):
            _archive_processed_file(doc_row["source_url"])

        await conn.execute(
            text("UPDATE documents SET status = 'facts_extracted', ingested_at = now() WHERE id = :id"),
            {"id": doc_id},
        )
        await conn.commit()

    # 4. Trigger derive metrics engine
    compute_rep = await compute_for_document(doc_id, engine)

    # 5. Refresh L6 Issuer Profile
    try:
        await refresh_profile_task({"db_pool": engine}, doc_id)
        profile_refreshed = True
    except Exception as e:
        log.warning("Profile refresh failed", error=str(e))
        profile_refreshed = False

    # 6. Compute live valuation
    async with engine.connect() as conn:
        val = await calculate_valuation(conn, ticker, is_live=True)
        live_val_ok = val.get("price") is not None

    return CommitReport(
        status="COMMITTED",
        doc_id=doc_id,
        ticker=ticker,
        fiscal_period=fiscal_period,
        facts_committed=facts_count,
        narratives_committed=narratives_count,
        guidance_committed=len(payload.guidance),
        derived_metrics_computed=compute_rep.computed,
        profile_refreshed=profile_refreshed,
        live_valuation_computed=live_val_ok,
        message=f"Successfully committed {facts_count} facts and {narratives_count} narratives. Derived {compute_rep.computed} metrics.",
    )


@mcp.tool()
async def get_issuer_context(ticker: str, period: str | None = None) -> dict[str, Any]:
    """Retrieves existing financial facts and derived metrics for an issuer to aid in comparative extraction."""
    engine = get_engine()
    ticker_clean = ticker.upper()

    async with engine.connect() as conn:
        facts_res = await conn.execute(
            text(
                """
                SELECT concept_id, fiscal_period, value_numeric, unit
                FROM financial_facts
                WHERE ticker = :ticker
                ORDER BY fiscal_period DESC, concept_id ASC
                LIMIT 50;
                """
            ),
            {"ticker": ticker_clean},
        )
        facts = [dict(r) for r in facts_res.mappings()]

        derived_res = await conn.execute(
            text(
                """
                SELECT metric_id, fiscal_period, value_numeric, unit
                FROM derived_metrics
                WHERE ticker = :ticker
                ORDER BY fiscal_period DESC, metric_id ASC
                LIMIT 25;
                """
            ),
            {"ticker": ticker_clean},
        )
        metrics = [dict(r) for r in derived_res.mappings()]

        # Live valuation
        val = await calculate_valuation(conn, ticker_clean, is_live=True)

        return {
            "ticker": ticker_clean,
            "target_period": period,
            "existing_facts": facts,
            "existing_metrics": metrics,
            "live_valuation": val,
        }


@mcp.tool()
async def get_review_queue() -> list[dict[str, Any]]:
    """Retrieves unverified documents and extraction exceptions quarantined in the review queue."""
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT id, ticker, fiscal_period, doc_id, issue_type, severity, validation_report, status, created_at
                FROM ingest_review_queue
                WHERE status = 'PENDING'
                ORDER BY created_at DESC
                LIMIT 50;
                """
            )
        )
        return [dict(r) for r in res.mappings()]


def main() -> None:
    """Entry point for running the EMIMIND MCP Server via stdio."""
    import asyncio
    mcp.run()


if __name__ == "__main__":
    main()
