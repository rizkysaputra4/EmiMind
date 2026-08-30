"""Pydantic schemas and types for the EMIMIND MCP Ingestion Server."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InspectionStatus(str, Enum):
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    AUTHORIZED = "AUTHORIZED"
    RESTATEMENT = "RESTATEMENT"
    ERROR = "ERROR"


class DocumentInspectionResult(BaseModel):
    status: InspectionStatus
    doc_hash: str
    doc_id: str | None = None
    ticker: str | None = None
    fiscal_period: str | None = None
    doc_type: str | None = None
    company_name: str | None = None
    sector: str | None = None
    message: str
    existing_facts_count: int = 0


class ExtractionFactRule(BaseModel):
    concept_id: str
    label: str
    statement_type: str  # 'BALANCE_SHEET', 'INCOME_STATEMENT', 'CASH_FLOW', 'PER_SHARE', 'NOTES'
    required: bool = True
    description: str | None = None


class ExtractionContract(BaseModel):
    doc_id: str
    ticker: str
    company_name: str
    sector: str
    fiscal_period: str
    period_type: str
    scaling_rules: dict[str, Any]
    required_facts: list[ExtractionFactRule]
    sector_specific_guidelines: list[str] = Field(default_factory=list)
    do_not_extract: list[str] = Field(default_factory=list)


class ExtractedFactItem(BaseModel):
    concept_id: str
    value_numeric: Decimal
    unit: str = "IDR"
    period_type: str = "instant"  # 'instant', 'duration_ytd', 'duration_q'
    source_page: int
    source_label_original: str | None = None
    bbox: list[float] | None = None
    note_reference: str | None = None


class ExtractedNarrativeItem(BaseModel):
    section: str  # 'MDA', 'STRATEGY', 'RISK', 'OUTLOOK', 'FOOTNOTE'
    text_original: str
    text_en: str | None = None
    source_page: int
    topic: str | None = None


class ExtractedGuidanceItem(BaseModel):
    metric: str
    target_period: str
    target_low: Decimal | None = None
    target_high: Decimal | None = None
    unit: str = "RATIO"
    source_page: int
    context_statement: str | None = None


class DraftSubmissionPayload(BaseModel):
    doc_id: str
    ticker: str
    fiscal_period: str
    accounting_standard: str = "PSAK_72"
    facts: list[ExtractedFactItem]
    narratives: list[ExtractedNarrativeItem] = Field(default_factory=list)
    guidance: list[ExtractedGuidanceItem] = Field(default_factory=list)


class IssueSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationIssue(BaseModel):
    severity: IssueSeverity
    category: str
    concept_id: str | None = None
    equation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    feedback_message: str
    target_pages: list[int] = Field(default_factory=list)


class ValidationReport(BaseModel):
    status: str  # 'VALID' or 'INVALID'
    submission_id: str
    doc_id: str
    ticker: str
    fiscal_period: str
    errors_count: int
    warnings_count: int
    can_retry: bool = True
    retry_attempt: int = 1
    max_retries: int = 3
    issues: list[ValidationIssue] = Field(default_factory=list)


class CommitReport(BaseModel):
    status: str
    doc_id: str
    ticker: str
    fiscal_period: str
    facts_committed: int
    narratives_committed: int
    guidance_committed: int
    derived_metrics_computed: int
    profile_refreshed: bool
    live_valuation_computed: bool
    message: str
