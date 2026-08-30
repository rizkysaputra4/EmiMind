"""Knowledge graph domain types and validation models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from services.shared.types import FiscalPeriod, Ticker


class GuidancePayload(BaseModel):
    """Structured payload for management guidance target nodes."""

    metric: str
    low: Decimal | None = None
    high: Decimal | None = None
    period_target: FiscalPeriod
    qualifier: Literal["at_least", "at_most", "exact", "range", "direction"] = "range"
    direction: Literal["up", "down", "flat"] | None = None
    unit: str = "RATIO"
    verbatim: str


class CausalTriple(BaseModel):
    """Causal effect-cause relationship extracted from management discussions."""

    effect_metric: str
    cause_metric_or_phrase: str
    direction: Literal["up", "down", "flat", "increase", "decrease"] = "up"
    confidence: float = Field(ge=0.5, le=0.8, default=0.7)


class KGTriple(BaseModel):
    """Knowledge graph traversed edge triple connecting source and target nodes."""

    src_node: dict[str, Any]
    edge: dict[str, Any]
    dst_node: dict[str, Any]
    depth: int = 1


class MatchReport(BaseModel):
    """Summary of guidance actuals matching process."""

    ticker: Ticker
    period: FiscalPeriod
    matched_count: int = 0
    edges_created: list[int] = Field(default_factory=list)


class LinkReport(BaseModel):
    """Summary of causal linker extraction on a document."""

    doc_id: UUID
    chunks_analyzed: int = 0
    edges_created: list[int] = Field(default_factory=list)
