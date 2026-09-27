"""Pydantic schemas and types for the EMIMIND MCP Ingestion Server."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class InspectionStatus(str, Enum):
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    AUTHORIZED = "AUTHORIZED"
    RESTATEMENT = "RESTATEMENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SKIPPED_ADMINISTRATIVE = "SKIPPED_ADMINISTRATIVE"
    ERROR = "ERROR"
    NEEDS_METADATA = "NEEDS_METADATA"


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


class DocumentSkipResult(BaseModel):
    """Return type of mark_document_skipped — confirms the skip was logged and
    the file archived out of the ingest queue."""
    doc_id: str
    ticker: str | None = None
    reason: str
    notes: str | None = None
    archived_to: str | None = None
    message: str


class ExtractionFactRule(BaseModel):
    concept_id: str
    label: str
    statement_type: str  # 'BALANCE_SHEET', 'INCOME_STATEMENT', 'CASH_FLOW', 'PER_SHARE', 'NOTE', 'OPERATIONAL_KPI'
    required: bool = True
    description: str | None = None
    importance: str = "HIGH"  # 'CRITICAL' | 'HIGH' | 'OPTIONAL'
    extraction_mode: str = "EXTRACTED_RAW"  # 'EXTRACTED_RAW' | 'CALCULATED_DETERMINISTIC'
    synonyms_id: list[str] = Field(default_factory=list)
    synonyms_en: list[str] = Field(default_factory=list)
    search_hints: list[str] = Field(default_factory=list)
    extraction_guideline: str | None = None
    expected_segment_fields: list[str] = Field(default_factory=list)
    calculation_formula: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    unit: str = "IDR"
    value_type: str = "MONETARY"


class ExtractionNarrativeRule(BaseModel):
    topic: str
    target_note_description: str
    expected_section: str  # 'MDA', 'RISK', 'FOOTNOTE', 'MGMT_STMT'
    guideline: str


class RouteQuery(BaseModel):
    terms_id: list[str] = Field(default_factory=list)
    terms_en: list[str] = Field(default_factory=list)
    max_pages: int = 6
    anchor_patterns: list[str] = Field(default_factory=list)


class GranularNoteModule(BaseModel):
    name: str  # e.g. 'REVENUE_BREAKDOWN', 'COGS_COMPONENTS', 'SUBSIDIARIES', 'DEBT_BY_LENDER', 'BIOLOGICAL_ASSETS'
    description: str
    typical_note_title: str
    target_concepts: list[str] = Field(default_factory=list)
    expected_segment_fields: list[str] = Field(default_factory=list)
    guideline: str
    route_query: RouteQuery | None = None


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
    core_modules: dict[str, RouteQuery] = Field(default_factory=dict)
    sector_specific_guidelines: list[str] = Field(default_factory=list)
    do_not_extract: list[str] = Field(default_factory=list)


class ExtractedFactItem(BaseModel):
    concept_id: str
    value_numeric: Decimal
    unit: str = "IDR"
    period_type: str | None = None  # 'instant', 'duration_qtd', 'duration_ytd', 'duration_q', 'duration_12m', 'duration'
    source_page: int
    statement: Literal["BS", "IS", "CF", "EQ", "NOTE"] | None = None
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


class CoverageBucket(BaseModel):
    found: int = 0
    expected: int = 0
    omitted_with_justification: int = 0
    missing: list[str] = Field(default_factory=list)


class ExtractionCoverage(BaseModel):
    critical: CoverageBucket = Field(default_factory=CoverageBucket)
    high: CoverageBucket = Field(default_factory=CoverageBucket)
    optional: CoverageBucket = Field(default_factory=CoverageBucket)


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
    coverage: ExtractionCoverage = Field(default_factory=ExtractionCoverage)
    previous_attempt_misses: list[str] = Field(default_factory=list)


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


class PageTableCell(BaseModel):
    row: int
    col: int
    text: str
    value: float | None = None
    bbox: list[float] | None = None
    confidence: float | None = None


class PageTable(BaseModel):
    table_index: int
    extraction_method: str = "pdfplumber"
    confidence: float = 1.0
    unit_hint: str | None = None
    cells: list[PageTableCell] = Field(default_factory=list)


class RoutedPage(BaseModel):
    page_index: int
    page_label: str | None = None
    text_source: str = "pdf_text"
    score: float = 0.0
    page_text: str = ""
    image_url: str | None = None
    tables: list[PageTable] = Field(default_factory=list)


class RoutedPages(BaseModel):
    doc_id: str
    module: str
    total_pages_returned: int
    pages: list[RoutedPage] = Field(default_factory=list)
    spans: list[list[int]] = Field(default_factory=list)

