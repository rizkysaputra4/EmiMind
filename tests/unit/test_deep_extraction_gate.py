"""Unit tests for the Deep Extraction Acceptance Gate (M9.6.2).

Each check is proven able to FAIL, and every missing input (column, ROUTED log, PDF, contract,
recall report) fails instead of passing. No database is touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from eval import deep_extraction_gate as gate
from eval.deep_extraction_gate import (
    depth_threshold,
    evaluate_document,
    evaluate_gate,
    is_annual,
    missing_columns,
    omission_contradictions,
    omission_search_terms,
    report,
    tokens_from_routed_logs,
)


def passing_metric(ticker: str = "BMRI") -> dict[str, Any]:
    """A metrics dict where every check passes (annual BANK filing)."""
    return {
        "ticker": ticker,
        "fiscal_period": "2025Q4",
        "doc_id": f"doc-{ticker}",
        "doc_type": "FS_ANNUAL",
        "sector": "BANK",
        "annual": True,
        "period_end": "2025-12-31",
        "expected_period_end": "2025-12-31",
        "page_count": 100,
        "actual_page_count": 100,
        "pdf_path": "C:/reports/BMRI/processed/x.pdf",
        "missing_columns": [],
        "mean_core_recall": 0.95,
        "mean_notes_recall": 0.85,
        "mean_precision": 0.5,
        "router_modules": 8,
        "mandatory_kpis_count": 10,
        "extracted_kpis_count": 9,
        "kpi_extracted_ratio": 0.9,
        "omitted_kpis": ["idx:CostOfCredit"],
        "uncovered_kpis": [],
        "uncovered_critical": [],
        "contradicted_omissions": {},
        "required_narratives_count": 2,
        "fact_count": 120,
        "distinct_concepts_count": 95,
        "depth_threshold": 90,
        "depth_basis": "max(2 x baseline 45, BANK min 60)",
        "depth_extractable_count": 40,
        "depth_hit_count": 38,
        "depth_ratio": 0.95,
        "segmented_facts_count": 30,
        "bad_provenance_count": 0,
        "facts_on_text_pages": 120,
        "grounded_on_text_pages": 120,
        "grounding_breakdown": [["pdf_text", "cell", 110], ["pdf_text", "text", 10]],
        "indexed_pages": 100,
        "pages_with_expected_embedding": 100,
        "routed_tokens": 20_000,
        "token_detail": "9 ROUTED calls",
        "whole_book_est": 200_000,
        "narrative_count": 4,
        "narratives_not_verbatim": 0,
        "boilerplate_hits": 0,
        "in_doc_duplicates": 0,
        "cross_ticker_duplicates": 0,
    }


def _failed(results: list[gate.CheckResult]) -> set[str]:
    return {r.dimension for r in results if r.status == "FAIL"}


def test_all_checks_pass_on_good_metrics() -> None:
    ok, results, summary = evaluate_gate([passing_metric(), passing_metric("LSIP")], False, "2025Q4")
    assert ok is True
    assert summary["failed_checks"] == 0
    dims = {r.dimension for r in results}
    assert dims == {
        "Router recall", "KPI coverage", "Concept depth", "Segmented facts", "Grounding",
        "Narratives", "Provenance", "Token efficiency", "Period correctness", "Embeddings",
    }  # fmt: skip


FAILURES: list[tuple[str, dict[str, Any], str]] = [
    ("recall core", {"mean_core_recall": 0.85}, "Router recall"),
    ("recall notes", {"mean_notes_recall": 0.70}, "Router recall"),
    ("precision", {"mean_precision": 0.30}, "Router recall"),
    ("recall report missing", {"mean_core_recall": None, "mean_precision": None}, "Router recall"),
    ("kpi extracted < 80%", {"kpi_extracted_ratio": 0.7, "extracted_kpis_count": 7}, "KPI coverage"),
    ("critical kpi uncovered", {"uncovered_critical": ["ifrs:Assets"]}, "KPI coverage"),
    ("omission contradicted", {"contradicted_omissions": {"idx:CASA": [40]}}, "KPI coverage"),
    ("no mandatory kpis", {"mandatory_kpis_count": 0, "kpi_extracted_ratio": 0.0}, "KPI coverage"),
    ("depth < 90% of extractable", {"depth_hit_count": 35, "depth_ratio": 0.875}, "Concept depth"),
    ("depth nothing extractable", {"depth_extractable_count": 0, "depth_ratio": 0.0},
     "Concept depth"),
    ("segments", {"segmented_facts_count": 24}, "Segmented facts"),
    ("grounding < 100%", {"grounded_on_text_pages": 119}, "Grounding"),
    ("grounding column missing", {"grounding_error": "column missing (026)"}, "Grounding"),
    ("no facts", {"fact_count": 0, "facts_on_text_pages": 0, "grounded_on_text_pages": 0}, "Grounding"),
    ("narrative not verbatim", {"narratives_not_verbatim": 1}, "Narratives"),
    ("narrative cross-ticker dup", {"cross_ticker_duplicates": 2}, "Narratives"),
    ("narrative boilerplate", {"boilerplate_hits": 1}, "Narratives"),
    ("narrative in-doc dup", {"in_doc_duplicates": 1}, "Narratives"),
    ("narratives required but none", {"narrative_count": 0}, "Narratives"),
    ("provenance", {"bad_provenance_count": 1}, "Provenance"),
    # 100 pages: 15% of 200k = 30k < the 50k floor, so the floor is the budget
    ("tokens over floor budget", {"routed_tokens": 50_001}, "Token efficiency"),
    # 600 pages: 15% of 1.2M = 180k > floor
    ("tokens over 15% budget", {"whole_book_est": 1_200_000, "routed_tokens": 180_001},
     "Token efficiency"),
    ("tokens missing", {"routed_tokens": None}, "Token efficiency"),
    ("wrong period", {"fiscal_period": "2025Q3"}, "Period correctness"),
    ("wrong period_end", {"period_end": "2024-12-31"}, "Period correctness"),
    ("pdf missing", {"pdf_path": None, "actual_page_count": None}, "Period correctness"),
    ("page count mismatch", {"actual_page_count": 99}, "Period correctness"),
    ("embeddings incomplete", {"pages_with_expected_embedding": 99}, "Embeddings"),
    ("pages not indexed", {"indexed_pages": 60, "pages_with_expected_embedding": 60}, "Embeddings"),
    ("embedding column missing", {"embedding_error": "column missing (025)"}, "Embeddings"),
]


@pytest.mark.parametrize(("case", "patch", "dimension"), FAILURES, ids=[f[0] for f in FAILURES])
def test_each_check_can_fail(case: str, patch: dict[str, Any], dimension: str) -> None:
    m = passing_metric()
    m.update(patch)
    ok, results, summary = evaluate_gate([m], False, "2025Q4")
    assert ok is False, case
    assert _failed(results) == {dimension}, case
    assert summary["documents_passed"] == 0


def test_document_lookup_error_fails() -> None:
    ok, results, _ = evaluate_gate([{"ticker": "XXXX", "error": "No document found"}], False, None)
    assert ok is False
    assert _failed(results) == {"Document lookup"}


def test_empty_window_fails() -> None:
    ok, _results, summary = evaluate_gate([], True, None)
    assert ok is False
    assert summary["error"] == "no documents to evaluate"


def test_aggregate_skips_recall_but_not_other_checks() -> None:
    m = passing_metric()
    m["mean_core_recall"] = 0.1
    ok, results, _ = evaluate_gate([m], True, None)
    assert ok is True
    assert "Router recall" not in {r.dimension for r in results}
    m["routed_tokens"] = None
    ok, results, _ = evaluate_gate([m], True, None)
    assert ok is False
    assert _failed(results) == {"Token efficiency"}


def test_quarterly_filing_depth_is_not_applicable_but_q4_always_annual() -> None:
    m = passing_metric()
    m.update(annual=False, fiscal_period="2025Q3", expected_period_end="2025-09-30",
             period_end="2025-09-30", distinct_concepts_count=3, segmented_facts_count=0)  # fmt: skip
    results = evaluate_document(m, is_aggregate=True)
    statuses = {r.dimension: r.status for r in results}
    assert statuses["Concept depth"] == "N/A"
    assert statuses["Segmented facts"] == "N/A"
    assert is_annual("FS_QUARTERLY", "2025Q4") is True  # mislabelled Q4 docs stay annual
    assert is_annual("FS_QUARTERLY", "2025Q2") is False
    assert is_annual("ANNUAL_REPORT", "2025Q4") is True


def test_contract_failure_fails_coverage_and_depth() -> None:
    m = passing_metric()
    m["contract_error"] = "ValueError: boom"
    ok, results, _ = evaluate_gate([m], False, "2025Q4")
    assert ok is False
    assert _failed(results) == {"KPI coverage", "Concept depth"}


def test_contract_depth_drops_only_verified_omissions() -> None:
    contract = {"a", "b", "c", "d", "e"}
    # d omitted and not found on any page: not extractable; e omitted but contradicted: a miss
    hit, extractable = gate.contract_depth(contract, {"a", "b", "x"}, {"d", "e"}, {"e"})
    assert (hit, extractable) == (2, 4)
    # an omission of a concept that was committed anyway does not shrink the denominator
    assert gate.contract_depth(contract, {"a", "d"}, {"d"}, set()) == (2, 5)


def test_legacy_depth_threshold_uses_full_ticker_baseline() -> None:
    depths = gate.load_sector_depth_minimums()
    assert depths["BANK"] == 60
    assert depths["CPO"] == 50 and depths["PLANTATION"] == 50
    assert depths["GENERIC"] == 40
    assert min(depths.values()) >= 40
    baseline = {"BMRI": {"distinct_concepts": 45, "documents": 40}, "LSIP": {"distinct_concepts": 20}}
    assert depth_threshold("BMRI", "BANK", depths, baseline)[0] == 90  # 2 x 45, not divided
    assert depth_threshold("LSIP", "CPO", depths, baseline)[0] == 50  # sector min wins
    thr, basis = depth_threshold("NEWCO", "UNKNOWN_SECTOR", depths, baseline)
    assert thr == 40
    assert "no baseline" in basis


def test_tokens_from_routed_logs() -> None:
    tokens, _ = tokens_from_routed_logs([{"chars": 8000, "images": 2}, {"chars": 4000, "images": 0}])
    assert tokens == 12000 // 4 + 2 * 1600
    assert tokens_from_routed_logs([])[0] is None
    # legacy ROUTED rows (before chars were logged) cannot be trusted
    assert tokens_from_routed_logs([{"chars": 100}, {"module": "BALANCE_SHEET"}])[0] is None


def test_omission_contradiction_search() -> None:
    terms = omission_search_terms(["Kas dan setara kas", "Cash and cash equivalents", "CASA", "Kas"])
    assert ("kas dan setara kas", False) in terms
    assert ("CASA", True) in terms
    assert all(t != "kas" for t, _ in terms)  # too short/ambiguous alone
    pages = {
        3: "Laporan posisi keuangan\nKas dan setara kas 4 1.234.567 987.654",
        7: "Kas dan setara kas akhir tahun disajikan pada Catatan 4",
        9: "Rasio CASA 2025 2024",
    }
    assert omission_contradictions(terms, pages) == [3]
    assert omission_contradictions(terms, {1: "Cash and cash equivalents (Note 4)  12,345,678"}) == [1]
    assert omission_contradictions(terms, {1: "nothing relevant 1.234.567"}) == []


class _FakeCursor:
    def __init__(self, present: set[tuple[str, str]]) -> None:
        self.present = present
        self._row: tuple[int] | None = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, _sql: str, params: tuple[str, str]) -> None:
        self._row = (1,) if params in self.present else None

    def fetchone(self) -> tuple[int] | None:
        return self._row


class _FakeConn:
    def __init__(self, present: set[tuple[str, str]]) -> None:
        self.present = present

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.present)


def test_missing_migration_columns_are_reported() -> None:
    none_applied = missing_columns(_FakeConn(set()))  # type: ignore[arg-type]
    assert any("financial_facts.grounding" in c and "026" in c for c in none_applied)
    assert any("document_pages.embedding_model" in c and "025" in c for c in none_applied)
    both = {("financial_facts", "grounding"), ("document_pages", "embedding_model")}
    assert missing_columns(_FakeConn(both)) == []  # type: ignore[arg-type]


def test_report_exit_code_and_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    bad = passing_metric("SYNTH")
    bad["segmented_facts_count"] = 5
    out = tmp_path / "gate.json"
    code = report([bad], is_aggregate=False, expected_period="2025Q4", out=out)
    assert code == 1
    printed = capsys.readouterr().out
    assert "GATE FAILED" in printed
    assert "FAIL" in printed
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["summary"]["all_passed"] is False
    assert saved["summary"]["per_document"][0]["failed_checks"] == ["Segmented facts"]

    assert report([passing_metric()], is_aggregate=False, expected_period="2025Q4") == 0
    assert "ALL CHECKS PASSED" in capsys.readouterr().out


def test_main_wires_since_and_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run_gate(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        seen.update(kwargs)
        return [passing_metric()], {}

    monkeypatch.setattr(gate, "run_gate", fake_run_gate)
    code = gate.main(["--aggregate", "--since", "2026-09-29T00:00:00"])
    assert code == 0
    assert seen["aggregate"] is True
    assert seen["since"] is not None and seen["since"].tzinfo is not None
    assert seen["tickers"] is None

    m = passing_metric()
    m["routed_tokens"] = None
    monkeypatch.setattr(gate, "run_gate", lambda **_kw: ([m], {}))
    assert gate.main(["--tickers", "BMRI"]) == 1


@pytest.mark.parametrize(
    ("whole_book_est", "tokens"),
    [(200_000, 50_000), (138_000, 31_724), (1_200_000, 180_000)],
    ids=["at floor", "short filing under floor", "long filing at 15%"],
)
def test_token_budget_floor_passes(whole_book_est: int, tokens: int) -> None:
    m = {**passing_metric(), "whole_book_est": whole_book_est, "routed_tokens": tokens}
    _ok, results, _summary = evaluate_gate([m], False, "2025Q4")
    assert "Token efficiency" not in _failed(results)


def test_token_budget_is_max_of_ratio_and_floor() -> None:
    assert gate.token_budget(138_000) == gate.TOKEN_BUDGET_FLOOR
    assert gate.token_budget(1_074_000) == 161_100
