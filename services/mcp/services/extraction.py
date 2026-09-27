"""Extraction submission and commit services for EMIMIND MCP Server."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.derive.engine import compute_for_document as default_compute_for_document
from services.derive.valuation import calculate_valuation as default_calculate_valuation
from services.ingest.tasks.refresh_profile import (
    refresh_profile_task as default_refresh_profile_task,
)
from services.mcp.contracts import build_extraction_contract as default_build_extraction_contract
from services.mcp.grounding import check_cell_grounding, resolve_scale
from services.mcp.periods import period_end_for
from services.mcp.services.common import (
    _archive_processed_file as default_archive_processed_file,
)
from services.mcp.services.common import (
    _log_processing_event as default_log_processing_event,
)
from services.mcp.services.common import (
    get_engine,
)
from services.mcp.types import (
    CommitReport,
    DraftSubmissionPayload,
    PageEvidence,
    PageTable,
    PageTableCell,
    ValidationReport,
)
from services.mcp.validator import (
    CONCEPT_ALIASES,
    narrative_md5,
)
from services.mcp.validator import (
    validate_draft_submission as default_validate_draft_submission,
)
from services.shared.logging import get_logger

log = get_logger("mcp.services.extraction")


async def _load_cross_issuer_narrative_hashes(conn: Any, ticker: str) -> dict[str, str]:
    """Loads MD5 hashes of committed narrative chunks for issuers other than ticker."""
    cross_hashes: dict[str, str] = {}
    try:
        narr_res = await conn.execute(
            text(
                "SELECT ticker, text_original FROM narrative_chunks WHERE ticker != :ticker LIMIT 5000"
            ),
            {"ticker": ticker.upper()},
        )
        for nr in narr_res.mappings().all():
            nh = narrative_md5(nr["text_original"])
            cross_hashes[nh] = nr["ticker"]
    except Exception as e:
        log.warning("Failed to load cross-issuer narrative hashes: %s", e)
    return cross_hashes


async def submit_draft_extraction(
    payload_json: str,
    retry_attempt: int = 1,
    usage: dict[str, Any] | None = None,
    *,
    engine: AsyncEngine | None = None,
    contract_builder: Callable[..., Any] = default_build_extraction_contract,
    validator_fn: Callable[..., Any] = default_validate_draft_submission,
    log_event_fn: Callable[..., Any] = default_log_processing_event,
) -> ValidationReport:
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

    effective_usage: dict[str, Any] | None = usage
    if effective_usage is None and payload.usage is not None:
        effective_usage = (
            payload.usage.model_dump(exclude_none=True)
            if hasattr(payload.usage, "model_dump")
            else dict(payload.usage)
        )

    eng = engine or get_engine()
    sector = "GENERIC"
    company_name = f"PT {payload.ticker.upper()} Tbk"
    doc_type_val: str | None = None
    async with eng.connect() as conn:
        sec_res = await conn.execute(
            text("SELECT name, sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
            {"ticker": payload.ticker.upper()},
        )
        sec_row = sec_res.mappings().first()
        if sec_row:
            sector = sec_row.get("sector") or "GENERIC"
            if sec_row.get("name"):
                company_name = sec_row["name"]

        doc_page_count: int | None = None
        try:
            dt_res = await conn.execute(
                text("SELECT doc_type, page_count FROM documents WHERE id = :id"),
                {"id": payload.doc_id},
            )
            dt_row = dt_res.mappings().first()
            if dt_row:
                doc_type_val = dt_row["doc_type"]
                doc_page_count = dt_row.get("page_count")
        except Exception:
            doc_type_val = None

        contract = await contract_builder(
            conn,
            doc_id=payload.doc_id,
            ticker=payload.ticker,
            company_name=company_name,
            sector=sector,
            fiscal_period=payload.fiscal_period,
            doc_type=doc_type_val,
        )

        # Load evidence for every cited source_page
        cited_pages: set[int] = set()
        for f in payload.facts:
            if f.source_page is not None:
                cited_pages.add(f.source_page)
        for n in payload.narratives:
            cited_pages.add(n.source_page)
        for c in payload.causal_links:
            cited_pages.add(c.source_page)
        for g in payload.guidance:
            cited_pages.add(g.source_page)

        evidence: dict[int, PageEvidence] | None = None
        try:
            has_pages_res = await conn.execute(
                text("SELECT 1 FROM document_pages WHERE doc_id = :doc_id LIMIT 1"),
                {"doc_id": payload.doc_id},
            )
            if has_pages_res.first():
                evidence = {}
                if cited_pages:
                    pages_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, text_source, page_text
                            FROM document_pages
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            """
                        ),
                        {"doc_id": payload.doc_id, "pages": list(cited_pages)},
                    )
                    tables_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, table_index, extraction_method, confidence, unit_hint, cells
                            FROM document_page_tables
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            ORDER BY page_index, table_index
                            """
                        ),
                        {"doc_id": payload.doc_id, "pages": list(cited_pages)},
                    )
                    tables_by_page: dict[int, list[PageTable]] = {}
                    for tr in tables_res.mappings().all():
                        p_idx = tr["page_index"]
                        raw_cells = tr["cells"]
                        if isinstance(raw_cells, str):
                            raw_cells = json.loads(raw_cells)
                        cell_objs = [PageTableCell.model_validate(c) for c in (raw_cells or [])]
                        pt = PageTable(
                            table_index=tr["table_index"],
                            extraction_method=tr.get("extraction_method") or "pdfplumber",
                            confidence=float(tr.get("confidence") or 1.0),
                            unit_hint=tr.get("unit_hint"),
                            cells=cell_objs,
                        )
                        tables_by_page.setdefault(p_idx, []).append(pt)

                    for pr in pages_res.mappings().all():
                        p_idx = pr["page_index"]
                        evidence[p_idx] = PageEvidence(
                            page_index=p_idx,
                            text_source=pr["text_source"] or "pdf_text",
                            page_text=pr["page_text"] or "",
                            tables=tables_by_page.get(p_idx, []),
                        )
        except Exception as e:
            log.warning("Failed to load page evidence for doc %s: %s", payload.doc_id, e)
            evidence = None

        cross_issuer_hashes: dict[str, str] | None = None
        if payload.narratives:
            cross_issuer_hashes = await _load_cross_issuer_narrative_hashes(conn, payload.ticker)

    report = validator_fn(
        payload,
        contract=contract,
        sector=sector,
        evidence=evidence,
        page_count=doc_page_count,
        cross_issuer_narrative_hashes=cross_issuer_hashes,
        retry_attempt=retry_attempt,
    )

    # If invalid after 3 attempts, log to review_queue with the coverage block
    if report.status == "INVALID" and retry_attempt >= 3:
        async with eng.connect() as conn:
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
            err_meta = {"status": report.status, "retry_attempt": retry_attempt}
            if effective_usage:
                err_meta.update(effective_usage)
            await log_event_fn(
                conn,
                action="ERROR",
                source="submit_draft_extraction",
                file_name="",
                ticker=payload.ticker.upper(),
                doc_id=payload.doc_id,
                reason=f"Validation failed after {retry_attempt} retries; sent to review queue.",
                metadata=err_meta,
            )
            await conn.commit()
    else:
        try:
            extracted_meta = {
                "status": report.status,
                "retry_attempt": retry_attempt,
                "facts_count": len(payload.facts),
            }
            if effective_usage:
                extracted_meta.update(effective_usage)
            async with eng.connect() as conn:
                await log_event_fn(
                    conn,
                    action="EXTRACTED",
                    source="submit_draft_extraction",
                    file_name="",
                    ticker=payload.ticker.upper(),
                    doc_id=payload.doc_id,
                    reason=f"Draft submitted (validation={report.status}, attempt={retry_attempt}).",
                    metadata=extracted_meta,
                )
                await conn.commit()
        except Exception as exc:
            log.warning("Failed to log EXTRACTED event", error=str(exc))

    return cast(ValidationReport, report)


async def commit_verified_report(
    payload_json: str,
    usage: dict[str, Any] | None = None,
    *,
    engine: AsyncEngine | None = None,
    compute_fn: Callable[..., Any] = default_compute_for_document,
    refresh_fn: Callable[..., Any] = default_refresh_profile_task,
    valuation_fn: Callable[..., Any] = default_calculate_valuation,
    contract_builder: Callable[..., Any] = default_build_extraction_contract,
    validator_fn: Callable[..., Any] = default_validate_draft_submission,
    log_event_fn: Callable[..., Any] = default_log_processing_event,
    archive_fn: Callable[..., Any] = default_archive_processed_file,
) -> CommitReport:
    """Commits verified financial facts, narrative chunks, and guidance to the database and runs the derive engine."""
    data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    payload = DraftSubmissionPayload.model_validate(data)

    effective_usage: dict[str, Any] | None = usage
    if effective_usage is None and payload.usage is not None:
        effective_usage = (
            payload.usage.model_dump(exclude_none=True)
            if hasattr(payload.usage, "model_dump")
            else dict(payload.usage)
        )

    eng = engine or get_engine()
    doc_id = payload.doc_id
    ticker = payload.ticker.upper()
    fiscal_period = payload.fiscal_period.upper()

    try:
        period_end_dt = period_end_for(fiscal_period)
        _ = int(fiscal_period[:4])
    except ValueError as err:
        return CommitReport(
            status="ERROR",
            doc_id=doc_id,
            ticker=ticker,
            fiscal_period=fiscal_period,
            facts_committed=0,
            narratives_committed=0,
            guidance_committed=0,
            omissions_recorded=0,
            derived_metrics_computed=0,
            profile_refreshed=False,
            live_valuation_computed=False,
            message=f"Invalid fiscal period '{fiscal_period}': {err}",
        )

    async with eng.connect() as conn:
        sector = "GENERIC"
        company_name = f"PT {ticker} Tbk"
        sec_res = await conn.execute(
            text("SELECT name, sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"),
            {"ticker": ticker},
        )
        sec_row = sec_res.mappings().first()
        if sec_row:
            sector = sec_row.get("sector") or "GENERIC"
            if sec_row.get("name"):
                company_name = sec_row["name"]

        doc_type_val = None
        doc_page_count = None
        try:
            dt_res = await conn.execute(
                text("SELECT doc_type, page_count FROM documents WHERE id = :id"),
                {"id": doc_id},
            )
            dt_row = dt_res.mappings().first()
            if dt_row:
                doc_type_val = dt_row.get("doc_type")
                doc_page_count = dt_row.get("page_count")
        except Exception:
            pass

        contract = await contract_builder(
            conn,
            doc_id=doc_id,
            ticker=ticker,
            company_name=company_name,
            sector=sector,
            fiscal_period=fiscal_period,
            doc_type=doc_type_val,
        )

        cited_pages: set[int] = set()
        for f in payload.facts:
            if f.source_page is not None:
                cited_pages.add(f.source_page)
        for n in payload.narratives:
            cited_pages.add(n.source_page)
        for c in payload.causal_links:
            cited_pages.add(c.source_page)
        for g in payload.guidance:
            cited_pages.add(g.source_page)

        evidence: dict[int, PageEvidence] | None = None
        try:
            has_pages_res = await conn.execute(
                text("SELECT 1 FROM document_pages WHERE doc_id = :doc_id LIMIT 1"),
                {"doc_id": doc_id},
            )
            if has_pages_res.first():
                evidence = {}
                if cited_pages:
                    pages_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, text_source, page_text
                            FROM document_pages
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            """
                        ),
                        {"doc_id": doc_id, "pages": list(cited_pages)},
                    )
                    tables_res = await conn.execute(
                        text(
                            """
                            SELECT page_index, table_index, extraction_method, confidence, unit_hint, cells
                            FROM document_page_tables
                            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                            ORDER BY page_index, table_index
                            """
                        ),
                        {"doc_id": doc_id, "pages": list(cited_pages)},
                    )
                    tables_by_page: dict[int, list[PageTable]] = {}
                    for tr in tables_res.mappings().all():
                        p_idx = tr["page_index"]
                        raw_cells = tr["cells"]
                        if isinstance(raw_cells, str):
                            raw_cells = json.loads(raw_cells)
                        cell_objs = [PageTableCell.model_validate(c) for c in (raw_cells or [])]
                        pt = PageTable(
                            table_index=tr["table_index"],
                            extraction_method=tr.get("extraction_method") or "pdfplumber",
                            confidence=float(tr.get("confidence") or 1.0),
                            unit_hint=tr.get("unit_hint"),
                            cells=cell_objs,
                        )
                        tables_by_page.setdefault(p_idx, []).append(pt)

                    for pr in pages_res.mappings().all():
                        p_idx = pr["page_index"]
                        evidence[p_idx] = PageEvidence(
                            page_index=p_idx,
                            text_source=pr["text_source"] or "pdf_text",
                            page_text=pr["page_text"] or "",
                            tables=tables_by_page.get(p_idx, []),
                        )
        except Exception as e:
            log.warning("Failed to load page evidence for doc %s in commit: %s", doc_id, e)
            evidence = None

        cross_issuer_hashes: dict[str, str] | None = None
        if payload.narratives:
            cross_issuer_hashes = await _load_cross_issuer_narrative_hashes(conn, ticker)

        val_rep = validator_fn(
            payload,
            contract=contract,
            sector=sector,
            evidence=evidence,
            page_count=doc_page_count,
            cross_issuer_narrative_hashes=cross_issuer_hashes,
        )
        if val_rep.status != "VALID":
            err_msg = val_rep.issues[0].feedback_message if val_rep.issues else "Validation failed"
            return CommitReport(
                status="REJECTED_VALIDATION_FAILED",
                doc_id=doc_id,
                ticker=ticker,
                fiscal_period=fiscal_period,
                facts_committed=0,
                narratives_committed=0,
                guidance_committed=0,
                omissions_recorded=0,
                derived_metrics_computed=0,
                profile_refreshed=False,
                live_valuation_computed=False,
                message=f"Commit rejected: validation failed ({err_msg})",
            )

        cids = list({f.concept_id for f in payload.facts})
        norm_map = {cid: CONCEPT_ALIASES.get(cid.lower(), cid) for cid in cids}
        all_query_ids = list(set(cids) | set(norm_map.values()))
        flow_stock_map: dict[str, str] = {}
        if all_query_ids:
            try:
                res = await conn.execute(
                    text(
                        "SELECT metric_id, flow_stock_type FROM metric_definitions WHERE metric_id = ANY(:cids)"
                    ),
                    {"cids": all_query_ids},
                )
                db_flows = {row[0]: row[1] for row in res.fetchall()}
                for cid in cids:
                    norm = norm_map.get(cid, cid)
                    if cid in db_flows:
                        flow_stock_map[cid] = db_flows[cid]
                    elif norm in db_flows:
                        flow_stock_map[cid] = db_flows[norm]
            except Exception:
                pass

        default_contract_scale = resolve_scale(None, getattr(contract, "scaling_rules", None))
        facts_count = 0
        for f in payload.facts:
            cid = f.concept_id
            stmt_type = f.statement or "NOTE"

            flow_stock = flow_stock_map.get(cid)
            if flow_stock and flow_stock.startswith("STOCK"):
                p_type = "instant"
            elif flow_stock and flow_stock.startswith("FLOW"):
                p_type = "duration_ytd"
            elif f.period_type:
                p_type = f.period_type
            else:
                p_type = "duration_ytd" if stmt_type in ("IS", "CF") else "instant"

            if p_type == "duration_q":
                p_type = "duration_qtd"
            elif p_type not in ("instant", "duration_qtd", "duration_ytd"):
                p_type = "duration_ytd" if stmt_type in ("IS", "CF") else "instant"

            seg_dict = f.segment

            method = "llm_extract"
            conf = 0.75
            needs_review = False
            source_bbox_val = f.bbox

            if evidence is not None and f.source_page in evidence:
                page_ev = evidence[f.source_page]
                if page_ev.text_source == "ocr":
                    method = "llm_extract"
                    conf = 0.65
                    needs_review = True
                elif f.cell_ref is not None:
                    is_grounded, _err, cell_conf, cell_bbox = check_cell_grounding(
                        f, page_ev, default_scale=default_contract_scale
                    )
                    if is_grounded:
                        method = "table_parser"
                        conf = round(cell_conf if cell_conf is not None else 0.95, 2)
                        source_bbox_val = cell_bbox or f.bbox
                        needs_review = False
                    else:
                        method = "llm_extract"
                        conf = 0.75
                        needs_review = False
                else:
                    method = "llm_extract"
                    conf = 0.75
                    needs_review = False

            source_bbox_json = json.dumps(source_bbox_val) if source_bbox_val else None

            await conn.execute(
                text(
                    """
                    INSERT INTO financial_facts (
                        source_doc_id, ticker, period_end, fiscal_period, statement, concept_id, concept_local,
                        value_numeric, unit, segment, period_type, accounting_std, source_page, source_bbox,
                        extraction_conf, extraction_method, needs_review
                    ) VALUES (
                        :doc_id, :ticker, :period_end, :period, :statement, :concept_id, :label,
                        :val, :unit, CAST(:seg AS jsonb), :period_type, :std, :page, CAST(:source_bbox AS jsonb),
                        :conf, :method, :needs_review
                    )
                    ON CONFLICT (ticker, fiscal_period, concept_id, (coalesce(segment, '{}'::jsonb)))
                    WHERE is_restated = false
                    DO UPDATE SET
                        value_numeric = EXCLUDED.value_numeric,
                        unit = EXCLUDED.unit,
                        segment = EXCLUDED.segment,
                        statement = EXCLUDED.statement,
                        period_type = EXCLUDED.period_type,
                        source_page = EXCLUDED.source_page,
                        source_bbox = EXCLUDED.source_bbox,
                        source_doc_id = EXCLUDED.source_doc_id,
                        extraction_method = EXCLUDED.extraction_method,
                        extraction_conf = EXCLUDED.extraction_conf,
                        needs_review = EXCLUDED.needs_review;
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
                    "seg": json.dumps(seg_dict) if seg_dict else None,
                    "period_type": p_type,
                    "std": payload.accounting_standard,
                    "page": f.source_page,
                    "source_bbox": source_bbox_json,
                    "conf": conf,
                    "method": method,
                    "needs_review": needs_review,
                },
            )
            facts_count += 1

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
            doc_file_res = await conn.execute(
                text("SELECT source_url FROM documents WHERE id = :id"), {"id": doc_id}
            )
            doc_f = doc_file_res.mappings().first()
            candidate_paths: list[Path] = []
            if doc_f and doc_f.get("source_url"):
                candidate_paths.append(Path(doc_f["source_url"]))
                candidate_paths.append(
                    Path(doc_f["source_url"]).parent / "processed" / Path(doc_f["source_url"]).name
                )

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

                        pdf_doc = pymupdf.open(str(cand))  # type: ignore[no-untyped-call]
                        pdf_pages = []
                        for i in range(len(pdf_doc)):
                            pg = pdf_doc[i]
                            txt = pg.get_text("text")  # type: ignore[no-untyped-call]
                            pdf_pages.append(
                                PageContent(
                                    page_num=i + 1, text=txt, language="mixed", has_text_layer=True
                                )
                            )
                        pdf_doc.close()  # type: ignore[no-untyped-call]

                        auto_chunks = chunk_pages(pdf_pages, ticker, "FS_ANNUAL", fiscal_period)
                        for chunk in auto_chunks:
                            sec = chunk.section if chunk.section in valid_sections else "OTHER"
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
                                    "page": chunk.source_page,
                                    "lang": chunk.language,
                                    "orig": chunk.text_original,
                                    "en": chunk.text_en or chunk.text_original,
                                    "speaker": chunk.speaker,
                                    "claim": chunk.claim_type,
                                    "concepts": chunk.mentioned_concepts or [],
                                },
                            )
                            narratives_count += 1
                        log.info(
                            "Auto-extracted narrative chunks from PDF",
                            count=narratives_count,
                            path=str(cand),
                        )
                        break
                    except Exception as e:
                        log.warning(
                            "Automatic fallback narrative chunking failed",
                            error=str(e),
                            path=str(cand),
                        )

        causal_count = 0
        for cl in payload.causal_links:
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
                    "payload": json.dumps(
                        {"metric": cl.metric_affected, "direction": cl.direction}
                    ),
                    "src": json.dumps({"doc_id": doc_id, "page": cl.source_page}),
                },
            )
            metric_node_id = metric_res.scalar()

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
                    "payload": json.dumps(
                        {"driver": cl.driver_description, "category": cl.cause_category}
                    ),
                    "src": json.dumps({"doc_id": doc_id, "page": cl.source_page}),
                },
            )
            cause_node_id = cause_res.scalar()

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
                        "evidence": json.dumps(
                            {"citation": f"[{ticker}-FS-{fiscal_period}#p{cl.source_page}]"}
                        ),
                        "pld": json.dumps({"category": cl.cause_category}),
                    },
                )
                causal_count += 1

        omissions_count = 0
        for omitted in payload.omitted_kpis:
            await conn.execute(
                text(
                    """
                    INSERT INTO concept_review (
                        ticker, doc_id, local_label, suggested_canonical, similarity_score, status, resolved_by
                    ) VALUES (
                        :ticker, :doc_id, :label, :canonical, 0.00, 'resolved', :reason
                    )
                    ON CONFLICT (ticker, doc_id, local_label) DO NOTHING;
                    """
                ),
                {
                    "ticker": ticker,
                    "doc_id": doc_id,
                    "label": f"OMITTED: {omitted.metric_id}",
                    "canonical": omitted.metric_id,
                    "reason": f"[{omitted.reason}] {omitted.explanation} (Checked pages: {omitted.search_pages_checked})",
                },
            )
            omissions_count += 1

        doc_res = await conn.execute(
            text("SELECT source_url FROM documents WHERE id = :id"), {"id": doc_id}
        )
        doc_row = doc_res.mappings().first()
        archived_url = None
        if doc_row and doc_row.get("source_url"):
            archived_url = archive_fn(doc_row["source_url"])

        if not archived_url:
            for cand in Path("incoming_reports").glob(f"*{ticker}*.pdf"):
                archived_url = archive_fn(str(cand))
                if archived_url:
                    break

        if archived_url:
            await conn.execute(
                text(
                    "UPDATE documents SET source_url = :url, status = 'facts_extracted', ingested_at = now() WHERE id = :id"
                ),
                {"url": archived_url, "id": doc_id},
            )
        else:
            await conn.execute(
                text(
                    "UPDATE documents SET status = 'facts_extracted', ingested_at = now() WHERE id = :id"
                ),
                {"id": doc_id},
            )
        await conn.commit()

    compute_rep = await compute_fn(doc_id, eng)

    try:
        await refresh_fn({"db_pool": eng}, doc_id)
        profile_refreshed = True
    except Exception as e:
        log.warning("Profile refresh failed", error=str(e))
        profile_refreshed = False

    async with eng.connect() as conn:
        val = await valuation_fn(conn, ticker, is_live=True)
        live_val_ok = val.get("price") is not None

        meta_committed: dict[str, Any] = {
            "facts_committed": facts_count,
            "narratives_committed": narratives_count,
            "guidance_committed": len(payload.guidance),
            "omissions_recorded": omissions_count,
            "derived_metrics_computed": compute_rep.computed,
            "profile_refreshed": profile_refreshed,
            "live_valuation_computed": live_val_ok,
        }
        if effective_usage:
            meta_committed.update(effective_usage)

        await log_event_fn(
            conn,
            action="COMMITTED",
            source="commit_verified_report",
            file_name="",
            ticker=ticker,
            doc_id=doc_id,
            reason=f"Committed {facts_count} facts, {narratives_count} narratives, {omissions_count} omissions, {compute_rep.computed} derived metrics.",
            metadata=meta_committed,
        )
        await conn.commit()

    return CommitReport(
        status="COMMITTED",
        doc_id=doc_id,
        ticker=ticker,
        fiscal_period=fiscal_period,
        facts_committed=facts_count,
        narratives_committed=narratives_count,
        guidance_committed=len(payload.guidance),
        omissions_recorded=omissions_count,
        derived_metrics_computed=compute_rep.computed,
        profile_refreshed=profile_refreshed,
        live_valuation_computed=live_val_ok,
        message=f"Successfully committed {facts_count} facts and {narratives_count} narratives. Derived {compute_rep.computed} metrics.",
    )
