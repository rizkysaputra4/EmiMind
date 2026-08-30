"""LLM provider exception classes."""

from __future__ import annotations


class LLMError(Exception):
    """Base exception for all LLM client errors."""


class LLMCapabilityError(LLMError):
    """Raised when an operation requires an LLM capability not supported by the configured provider/model."""


class LLMProviderError(LLMError):
    """Raised when an upstream provider returns an unrecoverable error."""
