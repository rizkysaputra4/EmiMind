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


class ExtractionNarrativeRule(BaseModel):
    topic: str
    target_note_description: str
    expected_section: str  # 'MDA', 'RISK', 'FOOTNOTE', 'MGMT_STMT'
    guideline: str


class GranularNoteModule(BaseModel):
    name: str  # e.g. 'REVENUE_BREAKDOWN', 'COGS_COMPONENTS', 'SUBSIDIARIES', 'DEBT_BY_LENDER', 'BIOLOGICAL_ASSETS'
    description: str
    typical_note_title: str
    target_concepts: list[str] = Field(default_factory=list)
    expected_segment_fields: list[str] = Field(default_factory=list)
    guideline: str


class ExtractionContract(BaseModel):
    doc_id: str
    ticker: str
    company_name: str
    sector: str
    fiscal_period: str
    period_type: str
    scaling_rules: dict[str, Any]
    required_facts: list[ExtractionFactRule]
    required_narratives: list[ExtractionNarrativeRule] = Field(default_factory=list)
    granular_note_modules: list[GranularNoteModule] = Field(default_factory=list)
    sector_specific_guidelines: list[str] = Field(default_factory=list)
    do_not_extract: list[str] = Field(default_factory=list)


class ExtractedFactItem(BaseModel):
    concept_id: str
    value_numeric: Decimal
    unit: str = "IDR"
    period_type: str = "instant"  # 'instant', 'duration_ytd', 'duration_q'
    source_page: int
    source_label_original: str | None = None
    segment: dict[str, Any] | None = None
    bbox: list[float] | None = None
    note_reference: str | None = None


class ExtractedNarrativeItem(BaseModel):
    section: str  # 'MDA', 'STRATEGY', 'RISK', 'OUTLOOK', 'FOOTNOTE'
    text_original: str
    text_en: str | None = None
    source_page: int
    topic: str | None = None


class ExtractedCausalLink(BaseModel):
    """Represents a cause-and-effect relationship extracted from management discussion."""

    metric_affected: str  # e.g. 'ifrs:Revenue', 'ifrs:GrossProfit', 'idx:CpoProduction'
    direction: str = "INCREASED"  # 'INCREASED', 'DECREASED', 'STABLE'
    cause_category: str = "EXTERNAL_FACTOR"  # 'WEATHER_CLIMATE', 'PRICE_CHANGE', 'VOLUME_GROWTH', 'COST_PRESSURE', 'MACRO_CURRENCY', 'OPERATIONAL_EFFICIENCY'
    driver_description: str
    source_page: int
    confidence: float = 0.90


class ExtractedGuidanceItem(BaseModel):
    metric: str
    target_period: str
    target_low: Decimal | None = None
    target_high: Decimal | None = None
    unit: str = "RATIO"
    source_page: int
    context_statement: str | None = None


class OmittedMetricItem(BaseModel):
    metric_id: str
    reason: str = "NOT_DISCLOSED_IN_REPORT"  # 'NOT_DISCLOSED_IN_REPORT', 'NOT_APPLICABLE_FOR_INTERIM', 'ONLY_IN_PRESENTATION_DECK', 'MERGED_WITH_OTHER_LINE'
    explanation: str
    search_pages_checked: list[int] = Field(default_factory=list)


class DraftSubmissionPayload(BaseModel):
    doc_id: str
    ticker: str
    fiscal_period: str
    accounting_standard: str = "PSAK_72"
    facts: list[ExtractedFactItem]
    narratives: list[ExtractedNarrativeItem] = Field(default_factory=list)
    causal_links: list[ExtractedCausalLink] = Field(default_factory=list)
    guidance: list[ExtractedGuidanceItem] = Field(default_factory=list)
    omitted_kpis: list[OmittedMetricItem] = Field(default_factory=list)


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
    omissions_recorded: int = 0
    derived_metrics_computed: int
    profile_refreshed: bool
    live_valuation_computed: bool
    message: str


class MetricOntologyDefinition(BaseModel):
    metric_id: str
    name_en: str
    name_id: str
    category: str
    sector_applicability: list[str]
    importance: str
    value_type: str
    unit: str
    flow_stock_type: str
    extraction_mode: str
    calculation_formula: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    source_priority: list[str] = Field(default_factory=list)
    synonyms_id: list[str] = Field(default_factory=list)
    synonyms_en: list[str] = Field(default_factory=list)


class MetricOntologyQueryResult(BaseModel):
    total_found: int
    sector: str
    metrics: list[MetricOntologyDefinition]


class DiscoveredMetricCandidate(BaseModel):
    metric_id: str
    name_en: str
    name_id: str
    category: str
    sector_code: str
    sub_industry: str | None = None
    importance: str = "HIGH"
    value_type: str = "FLOAT"
    unit: str
    flow_stock_type: str = "FLOW_PERIOD"
    typical_source: str = "FS_NOTES_DETAIL"
    source_page: int
    sample_text: str
    synonyms_id: list[str] = Field(default_factory=list)
    synonyms_en: list[str] = Field(default_factory=list)
    analytical_rationale: str | None = None


class DiscoveredMetricResult(BaseModel):
    status: str  # 'QUARANTINED', 'PROMOTED', 'EXISTING'
    metric_id: str
    message: str

