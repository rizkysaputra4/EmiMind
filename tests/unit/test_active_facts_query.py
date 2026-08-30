"""Unit tests for active_facts_query confidence gate helper."""

from services.shared.db import active_facts_query


def test_active_facts_query_structure() -> None:
    sql, params = active_facts_query(
        ticker="BMRI", fiscal_period="2024Q4", concept_id="idx:NetInterestIncome"
    )

    assert "needs_review = false" in sql
    assert "(extraction_conf >= 0.7 OR extraction_method = 'xbrl')" in sql
    assert "ticker = :ticker" in sql
    assert "fiscal_period = :fiscal_period" in sql
    assert "concept_id = :concept_id" in sql

    assert params["ticker"] == "BMRI"
    assert params["fiscal_period"] == "2024Q4"
    assert params["concept_id"] == "idx:NetInterestIncome"


def test_active_facts_query_no_params() -> None:
    sql, params = active_facts_query()
    assert "needs_review = false" in sql
    assert len(params) == 0
