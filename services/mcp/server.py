"""EMIMIND Model Context Protocol (MCP) Ingestion and Validation Server.

This module is the thin MCP entry point declaring MCP server metadata,
tool schemas, docstrings, and parameter descriptions. Execution logic
is delegated to services in `services.mcp.services`.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy.ext.asyncio import AsyncEngine

# Forwarded dependencies for patchability and backward compatibility
from services.derive.engine import compute_for_document
from services.derive.valuation import calculate_valuation
from services.ingest.tasks.refresh_profile import refresh_profile_task
from services.mcp.contracts import build_extraction_contract
from services.mcp.services.common import (
    _archive_processed_file,
    _log_processing_event,
)
from services.mcp.services.common import (
    get_engine as _default_get_engine,
)
from services.mcp.services.extraction import (
    commit_verified_report as commit_verified_report_impl,
)
from services.mcp.services.extraction import (
    submit_draft_extraction as submit_draft_extraction_impl,
)
from services.mcp.services.inspection import (
    inspect_document as inspect_document_impl,
)
from services.mcp.services.inspection import (
    mark_document_skipped as mark_document_skipped_impl,
)
from services.mcp.services.review import (
    get_issuer_context as get_issuer_context_impl,
)
from services.mcp.services.review import (
    get_metric_ontology as get_metric_ontology_impl,
)
from services.mcp.services.review import (
    get_review_queue as get_review_queue_impl,
)
from services.mcp.services.review import (
    list_processed_documents as list_processed_documents_impl,
)
from services.mcp.services.review import (
    submit_discovered_metric as submit_discovered_metric_impl,
)
from services.mcp.services.routing import (
    get_extraction_contract as get_extraction_contract_impl,
)
from services.mcp.services.routing import (
    get_routed_pages as get_routed_pages_impl,
)
from services.mcp.types import (
    CommitReport,
    DiscoveredMetricCandidate,
    DiscoveredMetricResult,
    DocumentInspectionResult,
    DocumentSkipResult,
    ExtractionContract,
    MetricOntologyQueryResult,
    RoutedPages,
    ValidationReport,
)
from services.mcp.validator import validate_draft_submission
from services.retrieval.page_router import route_pages
from services.shared.minio_client import get_minio


def get_engine() -> AsyncEngine:
    """Returns database engine (patchable for testing)."""
    return _default_get_engine()


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
    doc_type: str | None = None,
) -> DocumentInspectionResult:
    """Inspects a PDF document by computing its SHA-256 fingerprint and checking processing status in EMIMIND."""
    return await inspect_document_impl(
        file_path=file_path,
        ticker=ticker,
        fiscal_period=fiscal_period,
        doc_type=doc_type,
        engine=get_engine(),
        log_event_fn=_log_processing_event,
    )


@mcp.tool()
async def mark_document_skipped(
    doc_id: str,
    reason: str,
    notes: str | None = None,
) -> DocumentSkipResult:
    """Record that the extraction agent decided a document is not worth extracting.

    Call this after inspect_document if — on peeking at the PDF's first pages —
    the agent judged the file to be administrative (cover letter, OJK checklist,
    Surat Pernyataan Direksi, transmittal, newspaper ad, etc.), a duplicate
    representation of the same FS, or otherwise carries no extractable financial
    or narrative content. This is the design intent: LLM decides relevance on
    the fly rather than relying on brittle filename regexes.

    Effects:
      1. Appends a SKIPPED_BY_LLM row to document_processing_log (audit trail).
      2. Updates documents.status = 'skipped_by_llm' so re-ingest won't retry.
      3. Archives the source file to processed/ so it clears the ingest queue.

    Parameters:
      doc_id: UUID returned by inspect_document.
      reason: A short machine-friendly tag. Suggested values:
              NOT_FINANCIAL_CONTENT | COVER_LETTER | OJK_CHECKLIST |
              BOD_STATEMENT_OF_RESPONSIBILITY | DUPLICATE_OF_OTHER_FS |
              NEWSPAPER_AD | INTERNAL_CORRESPONDENCE | OTHER
      notes:  Optional 1-2 sentence explanation the operator can read later.
    """
    return await mark_document_skipped_impl(
        doc_id=doc_id,
        reason=reason,
        notes=notes,
        engine=get_engine(),
        log_event_fn=_log_processing_event,
    )


@mcp.tool()
async def get_extraction_contract(doc_id: str) -> ExtractionContract:
    """Retrieves the dynamic extraction contract, required concepts, and scaling rules for a document."""
    return await get_extraction_contract_impl(
        doc_id=doc_id,
        engine=get_engine(),
        contract_builder=build_extraction_contract,
    )


@mcp.tool()
async def get_routed_pages(doc_id: str, module: str, top_k: int = 3) -> RoutedPages:
    """Return ranked page_index hits (+ expanded neighbours, text, image URL, and tables) for a contract module.

    Parameters:
      doc_id: UUID of the document returned by inspect_document.
      module: Module name from the contract (e.g. 'BALANCE_SHEET', 'INCOME_STATEMENT',
              'CASH_FLOW', 'MDA', 'BANK_LOANS_NPL', 'PLANTATION_AREA', 'CASH_BANKS',
              'REVENUE_CUSTOMERS', 'COGS_BREAKDOWN', 'DEBT_FACILITIES').
      top_k:  Number of seed pages to rank and expand (default: 3).
    """
    return await get_routed_pages_impl(
        doc_id=doc_id,
        module=module,
        top_k=top_k,
        engine=get_engine(),
        router_fn=route_pages,
        minio_getter=get_minio,
        log_event_fn=_log_processing_event,
    )


@mcp.tool()
async def submit_draft_extraction(
    payload_json: str,
    retry_attempt: int = 1,
    usage: dict[str, Any] | None = None,
) -> ValidationReport:
    """Validates a draft extraction payload against schema, accounting math equations, and unit scaling."""
    return await submit_draft_extraction_impl(
        payload_json=payload_json,
        retry_attempt=retry_attempt,
        usage=usage,
        engine=get_engine(),
        contract_builder=build_extraction_contract,
        validator_fn=validate_draft_submission,
        log_event_fn=_log_processing_event,
    )


@mcp.tool()
async def commit_verified_report(
    payload_json: str,
    usage: dict[str, Any] | None = None,
) -> CommitReport:
    """Commits verified financial facts, narrative chunks, and guidance to the database and runs the derive engine."""
    return await commit_verified_report_impl(
        payload_json=payload_json,
        usage=usage,
        engine=get_engine(),
        compute_fn=compute_for_document,
        refresh_fn=refresh_profile_task,
        valuation_fn=calculate_valuation,
        contract_builder=build_extraction_contract,
        validator_fn=validate_draft_submission,
        log_event_fn=_log_processing_event,
        archive_fn=_archive_processed_file,
    )


@mcp.tool()
async def get_issuer_context(ticker: str, period: str | None = None) -> dict[str, Any]:
    """Retrieves existing financial facts and derived metrics for an issuer to aid in comparative extraction."""
    return await get_issuer_context_impl(
        ticker=ticker,
        period=period,
        engine=get_engine(),
        valuation_fn=calculate_valuation,
    )


@mcp.tool()
async def get_metric_ontology(
    sector: str | None = None,
    query: str | None = None,
    category: str | None = None,
) -> MetricOntologyQueryResult:
    """Queries canonical financial and operational metric definitions from the EMIMIND Ontology registry.

    Args:
        sector: Optional sector code to filter by (e.g. 'BANK', 'MINING', 'CPO', 'PROPERTY', 'ALL').
        query: Optional search keyword to match against metric names, IDs, or synonyms.
        category: Optional category filter (e.g. 'INCOME', 'BALANCE_SHEET', 'OPERATIONAL', 'RESERVES').
    """
    return await get_metric_ontology_impl(
        sector=sector,
        query=query,
        category=category,
        engine=get_engine(),
    )


@mcp.tool()
async def submit_discovered_metric(candidate: DiscoveredMetricCandidate) -> DiscoveredMetricResult:
    """Submits a newly discovered industry/operational KPI candidate from a financial filing into EMIMIND memory.

    Discovered metrics are validated and quarantined for ontology curation to avoid uncontrolled schema explosion.
    """
    return await submit_discovered_metric_impl(
        candidate=candidate,
        engine=get_engine(),
    )


@mcp.tool()
async def get_review_queue() -> list[dict[str, Any]]:
    """Retrieves unverified documents and extraction exceptions quarantined in the review queue."""
    return await get_review_queue_impl(
        engine=get_engine(),
    )


@mcp.tool()
async def list_processed_documents(
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List documents already ingested and extracted, so downloaders can skip re-fetching.

    Returns rows for documents whose `status` is `parsed` or `facts_extracted`
    (i.e. their financial facts are already committed). The returned filename fields
    are derived from `source_url` / `minio_key` for stable local-file matching.

    Optional `tickers` filter narrows the result to a subset — useful when the caller
    only cares about a specific universe (LQ45, a client watchlist, etc.).
    """
    return await list_processed_documents_impl(
        tickers=tickers,
        engine=get_engine(),
    )


def main() -> None:
    """Entry point for running the EMIMIND MCP Server via stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
