"""Domain-specific error classes for EmiMind."""

from __future__ import annotations


class EmiError(Exception):
    """Base exception for all EmiMind domain errors."""


class ExtractionError(EmiError):
    """Raised when PDF, table, XBRL, or OCR extraction fails."""


class NormalizationError(EmiError):
    """Raised when concept normalization, unit scaling, or accounting alignment fails."""


class ConceptMappingError(NormalizationError):
    """Raised when a local label cannot be resolved to a canonical concept ID."""


class RetrievalError(EmiError):
    """Raised when retrieval, indexing, or vector lookup fails."""


class LLMError(EmiError):
    """Raised when an LLM provider call fails or returns an unparseable response."""


class BudgetExceededError(EmiError):
    """Raised when the chat context or token budget is exceeded."""


class ProvenanceError(EmiError):
    """Raised when a fact cannot be linked to a verifiable source document/page/bbox."""
