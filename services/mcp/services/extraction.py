"""Extraction submission and commit services for EMIMIND MCP Server.

Both entry points load the same evidence (indexed pages + table grids of every cited page, the
text of every indexed page when omissions are declared, metric definitions, cross-issuer
narrative hashes) and run the same pure validator. The commit path re-grounds every fact with
the same function the validator uses, so what is stored (method, confidence, bbox, grounding)
is exactly what was verified.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.derive.engine import compute_for_document as default_compute_for_document
from services.derive.valuation import calculate_valuation as default_calculate_valuation
from services.ingest.tasks.refresh_profile import (
    refresh_profile_task as default_refresh_profile_task,
)
from services.mcp.contracts import build_extraction_contract as default_build_extraction_contract
from services.mcp.fact_semantics import BUILTIN_CONCEPTS, resolve_period_type
from services.mcp.grounding import (
    GroundingOutcome,
    dominant_scale,
    ground_fact,
    is_synthetic_bbox,
    scale_from_rules,
)
from services.mcp.narrative_checks import narrative_md5
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
    ConceptDefinition,
    DraftSubmissionPayload,
    ExtractedFactItem,
    ExtractionContract,
    PageEvidence,
    PageTable,
    PageTableCell,
    ValidationReport,
)
from services.mcp.validator import (
    CONCEPT_ALIASES,
)
from services.mcp.validator import (
    validate_draft_submission as default_validate_draft_submission,
)
from services.shared.logging import get_logger

log = get_logger("mcp.services.extraction")

# Confidence for facts that are not cell-grounded (M9.4.3).
TEXT_GROUNDED_CONF = 0.75
OCR_CONF = 0.65
_VALID_SECTIONS = {"MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"}

# SQL twin of narrative_checks.narrative_md5 (and of the generated column
# narrative_chunks.text_hash from migration 026).
_SQL_TEXT_HASH = "md5(btrim(regexp_replace(lower({col}), '\\s+', ' ', 'g')))"


@dataclass
class LoadedEvidence:
    """Everything the validator needs about the document, loaded from the DB."""

    evidence: dict[int, PageEvidence] | None
    document_text: dict[int, str] | None = None
    load_error: str | None = None
    concept_defs: dict[str, ConceptDefinition] = field(default_factory=dict)


def _cited_pages(payload: DraftSubmissionPayload) -> set[int]:
    pages: set[int] = {f.source_page for f in payload.facts if f.source_page is not None}
    pages |= {n.source_page for n in payload.narratives}
    pages |= {c.source_page for c in payload.causal_links}
    pages |= {g.source_page for g in payload.guidance}
    return pages


async def _load_page_evidence(
    conn: AsyncConnection, doc_id: str, cited_pages: set[int], *, want_all_text: bool
) -> LoadedEvidence:
    """Page evidence for the cited pages; None when the document has no page index.

    Any failure is reported (never swallowed into 'skip grounding'): evidence stays None and the
    validator returns DOCUMENT_NOT_INDEXED.
    """
    try:
        has_pages_res = await conn.execute(
            text("SELECT 1 FROM document_pages WHERE doc_id = :doc_id LIMIT 1"),
            {"doc_id": doc_id},
        )
        if not has_pages_res.first():
            return LoadedEvidence(evidence=None, load_error="no document_pages rows")
        evidence: dict[int, PageEvidence] = {}
        document_text: dict[int, str] | None = None
        if want_all_text:
            all_res = await conn.execute(
                text("SELECT page_index, page_text FROM document_pages WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            document_text = {
                r["page_index"]: r["page_text"] or "" for r in all_res.mappings().all()
            }
        if cited_pages:
            pages_res = await conn.execute(
                text(
                    """
                    SELECT page_index, text_source, page_text
                    FROM document_pages
                    WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                    """
                ),
                {"doc_id": doc_id, "pages": sorted(cited_pages)},
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
                {"doc_id": doc_id, "pages": sorted(cited_pages)},
            )
            tables_by_page: dict[int, list[PageTable]] = {}
            for tr in tables_res.mappings().all():
                raw_cells = tr["cells"]
                if isinstance(raw_cells, str):
                    raw_cells = json.loads(raw_cells)
                conf = tr.get("confidence")
                tables_by_page.setdefault(tr["page_index"], []).append(
                    PageTable(
                        table_index=tr["table_index"],
                        extraction_method=tr.get("extraction_method") or "pdfplumber",
                        confidence=float(conf) if conf is not None else 0.0,
                        unit_hint=tr.get("unit_hint"),
                        cells=[PageTableCell.model_validate(c) for c in (raw_cells or [])],
                    )
                )
            for pr in pages_res.mappings().all():
                p_idx = pr["page_index"]
                evidence[p_idx] = PageEvidence(
                    page_index=p_idx,
                    text_source=pr["text_source"] or "pdf_text",
                    page_text=pr["page_text"] or "",
                    tables=tables_by_page.get(p_idx, []),
                )
        return LoadedEvidence(evidence=evidence, document_text=document_text)
    except Exception as e:
        log.error("Failed to load page evidence", doc_id=doc_id, error=str(e))
        await conn.rollback()
        return LoadedEvidence(evidence=None, load_error=f"evidence load failed: {e}")


async def _load_concept_defs(
    conn: AsyncConnection, concept_ids: set[str]
) -> dict[str, ConceptDefinition]:
    """metric_definitions rows (plus builtin tie-out concepts) keyed by raw and aliased id."""
    norm = {cid: CONCEPT_ALIASES.get(cid.lower(), cid) for cid in concept_ids}
    query_ids = sorted(set(norm) | set(norm.values()))
    by_id: dict[str, ConceptDefinition] = {}
    if query_ids:
        res = await conn.execute(
            text(
                """
                SELECT metric_id, name_id, name_en, synonyms_id, synonyms_en, flow_stock_type,
                       unit, value_type, statement_type
                FROM metric_definitions
                WHERE metric_id = ANY(:ids)
                """
            ),
            {"ids": query_ids},
        )
        for r in res.mappings().all():
            by_id[r["metric_id"]] = ConceptDefinition(
                metric_id=r["metric_id"],
                name_id=r.get("name_id") or "",
                name_en=r.get("name_en") or "",
                synonyms_id=list(r.get("synonyms_id") or []),
                synonyms_en=list(r.get("synonyms_en") or []),
                flow_stock_type=r.get("flow_stock_type"),
                unit=r.get("unit"),
                value_type=r.get("value_type"),
                statement_type=r.get("statement_type"),
            )
    out: dict[str, ConceptDefinition] = {}
    for cid, n in norm.items():
        cdef = by_id.get(cid) or by_id.get(n) or BUILTIN_CONCEPTS.get(n)
        if cdef is not None:
            out[cid] = cdef
            out[n] = cdef
    return out


async def _load_cross_issuer_narrative_hashes(
    conn: AsyncConnection, ticker: str, texts: list[str]
) -> dict[str, str]:
    """{narrative_md5(text): other_ticker} for payload texts already committed by another issuer.

    Looks the payload's own hashes up in narrative_chunks.text_hash (indexed, migration 026)
    instead of scanning a LIMITed sample of committed chunks.
    """
    if not texts:
        return {}
    res = await conn.execute(
        text(
            f"""
            SELECT x.ord, n.ticker
            FROM unnest(CAST(:texts AS text[])) WITH ORDINALITY AS x(t, ord)
            JOIN narrative_chunks n ON n.text_hash = {_SQL_TEXT_HASH.format(col="x.t")}
            WHERE n.ticker <> :ticker
            """
        ),
        {"texts": texts, "ticker": ticker.upper()},
    )
    out: dict[str, str] = {}
    for r in res.mappings().all():
        out[narrative_md5(texts[int(r["ord"]) - 1])] = r["ticker"]
    return out


async def _issuer_and_document(
    conn: AsyncConnection, ticker: str, doc_id: str
) -> tuple[str, str, str | None, int | None]:
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
    dt_res = await conn.execute(
        text("SELECT doc_type, page_count FROM documents WHERE id = :id"),
        {"id": doc_id},
    )
    dt_row = dt_res.mappings().first()
    doc_type = dt_row.get("doc_type") if dt_row else None
    page_count = dt_row.get("page_count") if dt_row else None
    return sector, company_name, doc_type, page_count


async def _prepare_validation(
    conn: AsyncConnection,
    payload: DraftSubmissionPayload,
    contract_builder: Callable[..., Any],
) -> tuple[str, ExtractionContract, int | None, LoadedEvidence, dict[str, str]]:
    ticker = payload.ticker.upper()
    sector, company_name, doc_type, page_count = await _issuer_and_document(
        conn, ticker, payload.doc_id
    )
    contract = await contract_builder(
        conn,
        doc_id=payload.doc_id,
        ticker=payload.ticker,
        company_name=company_name,
        sector=sector,
        fiscal_period=payload.fiscal_period,
        doc_type=doc_type,
    )
    loaded = await _load_page_evidence(
        conn, payload.doc_id, _cited_pages(payload), want_all_text=bool(payload.omitted_kpis)
    )
    concept_ids = {f.concept_id for f in payload.facts} | {
        o.metric_id for o in payload.omitted_kpis
    }
    loaded.concept_defs = await _load_concept_defs(conn, concept_ids)
    cross_hashes = await _load_cross_issuer_narrative_hashes(
        conn, ticker, [n.text_original for n in payload.narratives]
    )
    return sector, contract, page_count, loaded, cross_hashes


def _run_validator(
    validator_fn: Callable[..., Any],
    payload: DraftSubmissionPayload,
    *,
    contract: ExtractionContract,
    sector: str,
    page_count: int | None,
    loaded: LoadedEvidence,
    cross_hashes: dict[str, str],
    retry_attempt: int = 1,
) -> ValidationReport:
    report = validator_fn(
        payload,
        contract=contract,
        sector=sector,
        evidence=loaded.evidence,
        page_count=page_count,
        cross_issuer_narrative_hashes=cross_hashes,
        retry_attempt=retry_attempt,
        concept_defs=loaded.concept_defs,
        document_text=loaded.document_text,
    )
    if loaded.evidence is None and loaded.load_error:
        for issue in report.issues:
            if issue.category == "DOCUMENT_NOT_INDEXED":
                issue.details["reason"] = loaded.load_error
    return cast(ValidationReport, report)


def _usage_of(
    payload: DraftSubmissionPayload, usage: dict[str, Any] | None
) -> dict[str, Any] | None:
    if usage is not None:
        return usage
    if payload.usage is None:
        return None
    if hasattr(payload.usage, "model_dump"):
        return cast(dict[str, Any], payload.usage.model_dump(exclude_none=True))
    return dict(payload.usage)


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
    """Validates a draft extraction payload against its page evidence, accounting identities,
    concept semantics and narrative rules."""
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

    effective_usage = _usage_of(payload, usage)
    eng = engine or get_engine()
    async with eng.connect() as conn:
        sector, contract, page_count, loaded, cross_hashes = await _prepare_validation(
            conn, payload, contract_builder
        )

    report = _run_validator(
        validator_fn,
        payload,
        contract=contract,
        sector=sector,
        page_count=page_count,
        loaded=loaded,
        cross_hashes=cross_hashes,
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
            err_meta: dict[str, Any] = {"status": report.status, "retry_attempt": retry_attempt}
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
            extracted_meta: dict[str, Any] = {
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

    return report


@dataclass(frozen=True)
class FactCommitParams:
    """How a validated fact is stored: derived from the grounding outcome, never assumed."""

    method: str
    conf: float
    bbox: list[float] | None
    grounding: str | None
    needs_review: bool


def commit_params_for(
    fact: ExtractedFactItem, page_ev: PageEvidence | None, outcome: GroundingOutcome | None
) -> FactCommitParams:
    """extraction_method / conf / bbox / grounding for a fact that passed validation.

    * cell-grounded → table_parser, conf = min(table, cell), the cell's real bbox (else the
      agent's bbox, else NULL), grounding 'cell'
    * text-grounded on a text page → llm_extract, 0.75, grounding 'text'
    * OCR page → llm_extract, 0.65, needs_review, grounding 'text' when the OCR text confirmed
      the number next to its label, else 'ocr_unverified'
    """
    agent_bbox = fact.bbox if fact.bbox and not is_synthetic_bbox(fact.bbox) else None
    if outcome is None or not outcome.ok or page_ev is None:
        return FactCommitParams("llm_extract", TEXT_GROUNDED_CONF, agent_bbox, None, True)
    if outcome.kind == "cell":
        conf = round(outcome.confidence if outcome.confidence is not None else 0.0, 2)
        return FactCommitParams("table_parser", conf, outcome.bbox or agent_bbox, "cell", False)
    if page_ev.text_source == "ocr":
        return FactCommitParams("llm_extract", OCR_CONF, agent_bbox, outcome.kind, True)
    return FactCommitParams("llm_extract", TEXT_GROUNDED_CONF, agent_bbox, outcome.kind, False)


def _guidance_qualifier(low: Decimal | None, high: Decimal | None) -> str:
    if low is not None and high is not None:
        return "exact" if low == high else "range"
    if low is not None:
        return "at_least"
    if high is not None:
        return "at_most"
    return "direction"


def _rejected(
    doc_id: str, ticker: str, fiscal_period: str, status: str, message: str
) -> CommitReport:
    return CommitReport(
        status=status,
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
        message=message,
    )


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
    """Re-validates the payload with evidence, then commits facts, narratives, guidance and
    omissions, and runs the derive engine. Nothing is stored unless validation is VALID."""
    data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    payload = DraftSubmissionPayload.model_validate(data)

    effective_usage = _usage_of(payload, usage)
    eng = engine or get_engine()
    doc_id = payload.doc_id
    ticker = payload.ticker.upper()
    fiscal_period = payload.fiscal_period.upper()

    try:
        period_end_dt = period_end_for(fiscal_period)
    except ValueError as err:
        return _rejected(
            doc_id,
            ticker,
            fiscal_period,
            "ERROR",
            f"Invalid fiscal period '{fiscal_period}': {err}",
        )

    async with eng.connect() as conn:
        sector, contract, page_count, loaded, cross_hashes = await _prepare_validation(
            conn, payload, contract_builder
        )
        val_rep = _run_validator(
            validator_fn,
            payload,
            contract=contract,
            sector=sector,
            page_count=page_count,
            loaded=loaded,
            cross_hashes=cross_hashes,
        )
        if val_rep.status != "VALID":
            errors = [i for i in val_rep.issues if i.severity == "ERROR"] or val_rep.issues
            err_msg = errors[0].feedback_message if errors else "Validation failed"
            return _rejected(
                doc_id,
                ticker,
                fiscal_period,
                "REJECTED_VALIDATION_FAILED",
                f"Commit rejected: validation failed ({val_rep.errors_count} errors; first: {err_msg})",
            )

        evidence = loaded.evidence or {}
        doc_scale = dominant_scale(evidence) if evidence else None
        contract_scale = scale_from_rules(getattr(contract, "scaling_rules", None))
        commit_warnings = [
            f"{i.category}: {i.feedback_message[:160]}"
            for i in val_rep.issues
            if i.severity == "WARNING"
        ]

        facts_count = 0
        for f in payload.facts:
            cid = f.concept_id
            stmt_type = f.statement or "NOTE"
            cdef = loaded.concept_defs.get(cid) or loaded.concept_defs.get(
                CONCEPT_ALIASES.get(cid.lower(), cid)
            )
            verdict = resolve_period_type(f, cdef)
            if verdict.resolved is None:  # the validator rejects these; never coerce
                return _rejected(
                    doc_id, ticker, fiscal_period, "REJECTED_VALIDATION_FAILED", verdict.message
                )
            page_ev = evidence.get(f.source_page) if f.source_page is not None else None
            outcome = (
                ground_fact(
                    f,
                    page_ev,
                    period_end=period_end_dt,
                    doc_scale=doc_scale,
                    contract_scale=contract_scale,
                )
                if page_ev is not None
                else None
            )
            params = commit_params_for(f, page_ev, outcome)

            await conn.execute(
                text(
                    """
                    INSERT INTO financial_facts (
                        source_doc_id, ticker, period_end, fiscal_period, statement, concept_id, concept_local,
                        value_numeric, unit, segment, period_type, accounting_std, source_page, source_bbox,
                        extraction_conf, extraction_method, needs_review, grounding
                    ) VALUES (
                        :doc_id, :ticker, :period_end, :period, :statement, :concept_id, :label,
                        :val, :unit, CAST(:seg AS jsonb), :period_type, :std, :page, CAST(:source_bbox AS jsonb),
                        :conf, :method, :needs_review, :grounding
                    )
                    ON CONFLICT (ticker, fiscal_period, concept_id, period_type, (coalesce(segment, '{}'::jsonb)))
                    WHERE is_restated = false
                    DO UPDATE SET
                        value_numeric = EXCLUDED.value_numeric,
                        unit = EXCLUDED.unit,
                        segment = EXCLUDED.segment,
                        statement = EXCLUDED.statement,
                        concept_local = EXCLUDED.concept_local,
                        period_end = EXCLUDED.period_end,
                        source_page = EXCLUDED.source_page,
                        source_bbox = EXCLUDED.source_bbox,
                        source_doc_id = EXCLUDED.source_doc_id,
                        extraction_method = EXCLUDED.extraction_method,
                        extraction_conf = EXCLUDED.extraction_conf,
                        needs_review = EXCLUDED.needs_review,
                        grounding = EXCLUDED.grounding;
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
                    "seg": json.dumps(f.segment) if f.segment else None,
                    "period_type": verdict.resolved,
                    "std": payload.accounting_standard,
                    "page": f.source_page,
                    "source_bbox": json.dumps(params.bbox) if params.bbox else None,
                    "conf": params.conf,
                    "method": params.method,
                    "needs_review": params.needs_review,
                    "grounding": params.grounding,
                },
            )
            facts_count += 1

        # Narratives: verbatim quotes only (validated above). No auto-chunk fallback: a payload
        # without narratives stores none. Duplicates (same doc + normalized text) are skipped.
        narratives_count = 0
        seen_hashes: set[str] = set()
        for n in payload.narratives:
            n_hash = narrative_md5(n.text_original)
            if n_hash in seen_hashes:
                continue
            seen_hashes.add(n_hash)
            sec = n.section.upper() if n.section.upper() in _VALID_SECTIONS else "OTHER"
            ins = await conn.execute(
                text(
                    """
                    INSERT INTO narrative_chunks (
                        source_doc_id, ticker, period_end, fiscal_period, section, source_page, text_original, text_en, tsv
                    ) VALUES (
                        :doc_id, :ticker, :period_end, :period, :sec, :page, :orig, :en, to_tsvector('simple', :orig)
                    )
                    ON CONFLICT (source_doc_id, text_hash) DO NOTHING
                    RETURNING id;
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
            if ins.first() is not None:
                narratives_count += 1

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

        # Guidance targets are stored as GUIDANCE kg_nodes (the shape services.kg reads).
        guidance_count = 0
        for g in payload.guidance:
            g_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref)
                    VALUES ('GUIDANCE', :ticker, :period, CAST(:payload AS jsonb), CAST(:src AS jsonb))
                    RETURNING id;
                    """
                ),
                {
                    "ticker": ticker,
                    "period": fiscal_period,
                    "payload": json.dumps(
                        {
                            "metric": g.metric,
                            "low": float(g.target_low) if g.target_low is not None else None,
                            "high": float(g.target_high) if g.target_high is not None else None,
                            "period_target": g.target_period,
                            "qualifier": _guidance_qualifier(g.target_low, g.target_high),
                            "unit": g.unit,
                            "verbatim": g.context_statement or "",
                        }
                    ),
                    "src": json.dumps({"doc_id": doc_id, "page": g.source_page}),
                },
            )
            if g_res.scalar() is not None:
                guidance_count += 1

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

        # Archive only this document's own source file (never another file of the same ticker).
        doc_res = await conn.execute(
            text("SELECT source_url FROM documents WHERE id = :id"), {"id": doc_id}
        )
        doc_row = doc_res.mappings().first()
        archived_url = None
        if doc_row and doc_row.get("source_url"):
            archived_url = archive_fn(doc_row["source_url"])

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
            "guidance_committed": guidance_count,
            "causal_links_committed": causal_count,
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
            reason=(
                f"Committed {facts_count} facts, {narratives_count} narratives, {guidance_count} "
                f"guidance items, {omissions_count} omissions, {compute_rep.computed} derived metrics."
            ),
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
        guidance_committed=guidance_count,
        omissions_recorded=omissions_count,
        derived_metrics_computed=compute_rep.computed,
        profile_refreshed=profile_refreshed,
        live_valuation_computed=live_val_ok,
        message=(
            f"Successfully committed {facts_count} facts, {narratives_count} narratives and "
            f"{guidance_count} guidance items. Derived {compute_rep.computed} metrics."
        ),
        warnings=commit_warnings,
    )
