"""Central domain types and validation models."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

TICKER_REGEX = re.compile(r"^[A-Z]{4}$")
FISCAL_PERIOD_REGEX = re.compile(r"^(19|20)\d{2}(Q[1-4]|FY|H[12])$")


def validate_ticker(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Ticker must be a string")
    if not TICKER_REGEX.match(v):
        raise ValueError(
            f"Invalid IDX ticker: '{v}'. Must be exactly 4 uppercase letters (e.g. 'BMRI')."
        )
    return v


def validate_fiscal_period(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("FiscalPeriod must be a string")
    if not FISCAL_PERIOD_REGEX.match(v):
        raise ValueError(
            f"Invalid fiscal period: '{v}'. Must match format YYYY(Q1-Q4|H1|H2|FY) "
            "(e.g. '2024Q4', '2023FY')."
        )
    return v


Ticker = Annotated[str, AfterValidator(validate_ticker)]
FiscalPeriod = Annotated[str, AfterValidator(validate_fiscal_period)]

DocType = Literal["PUBEX", "FS_QUARTERLY", "FS_ANNUAL", "ANNUAL_REPORT"]
Language = Literal["id", "en", "mixed"]
Statement = Literal["IS", "BS", "CF", "EQ", "NOTE"]
ExtractionMethod = Literal["xbrl", "table_parser", "llm_extract", "manual"]
PeriodType = Literal["instant", "duration_qtd", "duration_ytd"]


class Intent(StrEnum):
    """User query intention classification."""

    FACT_LOOKUP = "FACT_LOOKUP"
    EXPLANATION = "EXPLANATION"
    TREND = "TREND"
    COMPARE_PEERS = "COMPARE_PEERS"
    SCREEN = "SCREEN"
    GUIDANCE_CHECK = "GUIDANCE_CHECK"
    TECHNICAL = "TECHNICAL"
    META = "META"


class QueryClassification(BaseModel):
    """Structured query classification emitted by classifier."""

    intent: Intent
    tickers: list[Ticker] = Field(default_factory=list)
    periods: list[FiscalPeriod] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    is_drill: bool = False
    references_prior_claim: bool = False


class BBox(tuple[float, float, float, float]):
    """Bounding box coordinates (x0, y0, x1, y1) with x0 <= x1 and y0 <= y1."""

    def __new__(cls, x0: float, y0: float, x1: float, y1: float) -> BBox:
        fx0, fy0, fx1, fy1 = float(x0), float(y0), float(x1), float(y1)
        if fx0 > fx1 or fy0 > fy1:
            raise ValueError(
                f"Invalid BBox coordinates: ({fx0}, {fy0}, {fx1}, {fy1}). "
                "Must satisfy x0 <= x1 and y0 <= y1."
            )
        return super().__new__(cls, (fx0, fy0, fx1, fy1))

    @property
    def x0(self) -> float:
        return self[0]

    @property
    def y0(self) -> float:
        return self[1]

    @property
    def x1(self) -> float:
        return self[2]

    @property
    def y1(self) -> float:
        return self[3]

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        def validate(v: Any) -> BBox:
            if isinstance(v, BBox):
                return v
            if isinstance(v, (list, tuple)) and len(v) == 4:
                return BBox(float(v[0]), float(v[1]), float(v[2]), float(v[3]))
            raise ValueError("BBox must be a 4-element sequence (x0, y0, x1, y1)")

        return core_schema.no_info_after_validator_function(
            validate,
            core_schema.tuple_schema(
                [
                    core_schema.float_schema(),
                    core_schema.float_schema(),
                    core_schema.float_schema(),
                    core_schema.float_schema(),
                ]
            ),
        )


class UploadResponse(BaseModel):
    """Response returned upon document upload."""

    document_id: str
    status: str = "raw"
    deduplicated: bool = False


class ProposedMetadata(BaseModel):
    """Metadata proposed by the auto-extractor for user review."""

    ticker: str | None = None
    fiscal_period: str | None = None
    doc_type: DocType | None = None
    language: Language = "id"
    confidence: dict[str, float] = Field(default_factory=dict)
    evidence_snippet: str | None = None
    source: Literal["regex", "llm", "mixed", "none"] = "none"


class InspectResponse(BaseModel):
    """Response returned upon /upload/inspect — includes proposed metadata for review."""

    document_id: str
    proposed: ProposedMetadata
    deduplicated: bool = False
    existing_status: str | None = None


class ApproveRequest(BaseModel):
    """Body payload for /upload/approve/{doc_id}."""

    ticker: Ticker
    doc_type: DocType
    fiscal_period: FiscalPeriod
    language: Language


class ChatCitation(BaseModel):
    """Evidence citation returned with chat responses."""

    fact_id: int | None = None
    chunk_id: str | None = None
    document_id: str
    ticker: str
    fiscal_period: str
    page: int | None = None
    bbox: BBox | None = None
    snippet: str | None = None
    citation_tag: str | None = None


class ChatRequest(BaseModel):
    """Incoming chat query payload."""

    session_id: str | None = None
    message: str
    focus_ticker: str | None = None


class ChatResponse(BaseModel):
    """Chat response payload."""

    session_id: str
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    latency_ms: int | None = None
    token_usage: dict[str, Any] | None = None


class ScreenerRequest(BaseModel):
    """Incoming screener query payload."""

    query: str | None = None


class ScreenerResponse(BaseModel):
    """Screener results payload."""

    results: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class PageContent(BaseModel):
    """Content extracted from a single PDF page."""

    page_num: int
    text: str
    language: Language
    has_text_layer: bool
    bbox_by_char: list[tuple[str, BBox]] | None = None


class TableCell(BaseModel):
    """Single cell inside an extracted table."""

    row: int
    col: int
    text: str
    value: float | None = None
    bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedTable(BaseModel):
    """Table structure extracted from a document page."""

    page_num: int
    cells: list[TableCell]
    extraction_method: Literal["camelot_lattice", "camelot_stream", "ocr", "llm", "pdfplumber"]
    confidence: float = Field(ge=0.0, le=1.0)
    unit_hint: str | None = None


class ExtractedFact(BaseModel):
    """Financial fact extracted from a table or XBRL instance."""

    concept_local: str
    value_numeric: float
    unit: str
    period_type: PeriodType
    statement: Statement | None = None
    accounting_std: str | None = None
    segment: dict[str, Any] | None = None
    source_page: int
    source_bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)
    method: ExtractionMethod


class NarrativeChunkDraft(BaseModel):
    """Draft semantic narrative chunk before embedding generation."""

    source_page: int
    section: Literal["MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"]
    language: Language
    text_original: str
    text_en: str | None = None
    speaker: str | None = None
    claim_type: Literal["GUIDANCE", "EXPLANATION", "FORWARD_LOOKING", "RISK", "NEUTRAL"] | None = (
        None
    )
    mentioned_concepts: list[str] = Field(default_factory=list)
    mentioned_periods: list[str] = Field(default_factory=list)


class ConceptReviewItem(BaseModel):
    """Item queued in review queue for human review."""

    id: int | None = None
    ticker: str
    doc_id: str
    local_label: str
    suggested_canonical: str | None = None
    similarity_score: float | None = None
    status: Literal["open", "resolved", "rejected"] = "open"
    canonical_final: str | None = None
