"""Concept mapping and fuzzy normalization to canonical accounting IDs."""

from __future__ import annotations

import re
from collections.abc import Sequence

from rapidfuzz import fuzz

from services.shared.errors import ConceptMappingError


def normalize_label(label: str) -> str:
    """Normalizes an accounting line item label for matching."""
    s = label.strip().lower()
    # Replace parentheses / hyphens / currency indicators
    s = re.sub(r"[()\[\]{}.,;:\-—/\u2013\u2014]", " ", s)
    # Collapse multiple whitespaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fuzzy_match_concept(
    local_label: str,
    candidates: Sequence[tuple[str, str, str | None]],
    threshold: float = 0.75,
) -> tuple[str, float]:
    """Matches a local label against candidates `(local_label, canonical_id, sector)`.

    Returns (canonical_concept_id, confidence) or raises ConceptMappingError.
    """
    norm_query = normalize_label(local_label)
    if not norm_query:
        raise ConceptMappingError(f"Empty label cannot be mapped: {local_label!r}")

    # 1. Exact match pass
    for cand_local, cand_canonical, _ in candidates:
        if normalize_label(cand_local) == norm_query:
            return cand_canonical, 1.0

    # 2. Fuzzy similarity pass via rapidfuzz
    best_match: str | None = None
    best_score = 0.0

    for cand_local, cand_canonical, _ in candidates:
        cand_norm = normalize_label(cand_local)
        # Token sort ratio handles word order variations between Indonesian & English
        score = fuzz.token_sort_ratio(norm_query, cand_norm) / 100.0
        if score > best_score:
            best_score = score
            best_match = cand_canonical

    if best_match is not None and best_score >= threshold:
        confidence = min(best_score, 0.85)
        return best_match, confidence

    raise ConceptMappingError(
        f"Unable to map label '{local_label}' to canonical concept (best score: {best_score:.2f})"
    )
