"""Unit tests for XBRL parsing."""

from __future__ import annotations

from pathlib import Path

from services.extraction.xbrl import parse_xbrl

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_parse_sample_xbrl() -> None:
    xbrl_path = FIXTURES_DIR / "sample_bmri.xbrl.xml"
    assert xbrl_path.exists()

    facts = parse_xbrl(xbrl_path.read_bytes())
    assert len(facts) >= 5

    # Check for 1.0 confidence and xbrl method
    for f in facts:
        assert f.confidence == 1.0
        assert f.method == "xbrl"
        assert f.source_page == 0

    concept_uris = [f.concept_local for f in facts]
    assert any("Assets" in u for u in concept_uris)
    assert any("NetInterestIncome" in u for u in concept_uris)
