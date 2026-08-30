"""Unit tests for concept mapping and fuzzy matching."""

import pytest

from services.extraction.concepts import fuzzy_match_concept, normalize_label
from services.shared.errors import ConceptMappingError


def test_normalize_label() -> None:
    assert normalize_label("  Pendapatan Bunga (Net)  ") == "pendapatan bunga net"
    assert normalize_label("Laba / (Rugi) Bersih...") == "laba rugi bersih"


def test_fuzzy_match_exact() -> None:
    candidates = [
        ("Pendapatan Bunga Bersih", "idx:NetInterestIncome", "Banking"),
        ("Total Aset", "ifrs:Assets", "Banking"),
    ]
    canonical_id, conf = fuzzy_match_concept("pendapatan bunga bersih", candidates)
    assert canonical_id == "idx:NetInterestIncome"
    assert conf == 1.0


def test_fuzzy_match_similarity() -> None:
    candidates = [
        ("Pendapatan Bunga Bersih", "idx:NetInterestIncome", "Banking"),
        ("Total Aset", "ifrs:Assets", "Banking"),
    ]
    canonical_id, conf = fuzzy_match_concept("Pendapatan Bunga - Bersih", candidates)
    assert canonical_id == "idx:NetInterestIncome"
    assert conf >= 0.70


def test_fuzzy_match_unmapped_raises() -> None:
    candidates = [
        ("Pendapatan Bunga", "ifrs:InterestIncome", "Banking"),
    ]
    with pytest.raises(ConceptMappingError):
        fuzzy_match_concept("Unrelated random label 12345", candidates, threshold=0.7)
