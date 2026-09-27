"""Unit tests for Deep Extraction Acceptance Gate (M9.6.2)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from eval.deep_extraction_gate import (
    evaluate_gate,
)


def _build_passing_metric(ticker: str = "TEST") -> dict[str, Any]:
    """Helper creating a synthetic metric dict where all 9 gate checks pass."""
    return {
        "ticker": ticker,
        "period": "2025Q4",
        "period_end": "2025-12-31",
        "doc_id": "test-doc-uuid",
        "page_count": 100,
        "actual_page_count": 100,
        "pdf_path": "incoming_reports/processed/test.pdf",
        "sector": "BANK",
        "mean_core_recall": 1.0,
        "mean_notes_recall": 0.95,
        "mandatory_kpis_count": 10,
        "missing_kpis": [],
        "kpi_coverage_ratio": 1.0,
        "distinct_concepts_count": 50,
        "depth_threshold": 40,
        "segmented_facts_count": 30,
        "total_facts_on_text_pages": 40,
        "grounded_facts_count": 40,
        "grounding_ratio": 1.0,
        "cross_ticker_duplicates": 0,
        "boilerplate_hits": 0,
        "bad_provenance_count": 0,
        "input_tokens": 15000,
        "whole_book_est": 200000,
        "token_ratio": 0.075,
    }


def test_evaluate_gate_all_pass() -> None:
    metrics = [_build_passing_metric("BMRI"), _build_passing_metric("LSIP")]
    all_passed, results, summary = evaluate_gate(metrics)

    assert all_passed is True
    assert summary["all_passed"] is True
    assert summary["failed_checks"] == 0
    assert summary["passed_checks"] == len(results)
    for r in results:
        assert r.status == "PASS"


def test_evaluate_gate_fails_on_router_recall() -> None:
    bad_metric = _build_passing_metric("FAIL_RECALL")
    bad_metric["mean_core_recall"] = 0.85  # < 0.90 threshold

    all_passed, results, summary = evaluate_gate([bad_metric])
    assert all_passed is False
    assert summary["all_passed"] is False

    failing = [r for r in results if r.status == "FAIL"]
    assert len(failing) == 1
    assert "Router recall" in failing[0].dimension


def test_evaluate_gate_aggregate_skips_router_recall() -> None:
    bad_metric = _build_passing_metric("FAIL_RECALL")
    bad_metric["mean_core_recall"] = 0.50

    # In aggregate mode, router recall is not evaluated
    all_passed, results, _summary = evaluate_gate([bad_metric], is_aggregate=True)
    assert all_passed is True
    assert all(r.status == "PASS" for r in results)
    assert not any("Router recall" in r.dimension for r in results)


def test_evaluate_gate_fails_on_sector_kpis() -> None:
    bad_metric = _build_passing_metric("FAIL_KPI")
    bad_metric["missing_kpis"] = ["idx:CapitalAdequacyRatio"]
    bad_metric["kpi_coverage_ratio"] = 0.90

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Sector KPI coverage" in r.dimension for r in failing)


def test_evaluate_gate_fails_on_concept_depth() -> None:
    bad_metric = _build_passing_metric("FAIL_DEPTH")
    bad_metric["distinct_concepts_count"] = 25
    bad_metric["depth_threshold"] = 40  # 25 < 40

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Concept depth" in r.dimension for r in failing)


def test_evaluate_gate_fails_on_segmented_facts() -> None:
    bad_metric = _build_passing_metric("FAIL_SEG")
    bad_metric["segmented_facts_count"] = 12  # < 25

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Segmented facts" in r.dimension for r in failing)


def test_evaluate_gate_fails_on_numeric_grounding() -> None:
    bad_metric = _build_passing_metric("FAIL_GROUND")
    bad_metric["grounding_ratio"] = 0.95  # < 1.0

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Numeric grounding" in r.dimension for r in failing)


def test_evaluate_gate_fails_on_narrative_genuineness() -> None:
    bad_metric = _build_passing_metric("FAIL_NARR")
    bad_metric["boilerplate_hits"] = 1

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Narrative genuineness" in r.dimension for r in failing)


def test_evaluate_gate_fails_on_provenance() -> None:
    bad_metric = _build_passing_metric("FAIL_PROV")
    bad_metric["bad_provenance_count"] = 2

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Provenance" in r.dimension for r in failing)


def test_evaluate_gate_fails_on_token_efficiency() -> None:
    bad_metric = _build_passing_metric("FAIL_TOKEN")
    bad_metric["token_ratio"] = 0.22  # > 15%

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Token efficiency" in r.dimension for r in failing)


def test_evaluate_gate_fails_on_period_correctness() -> None:
    bad_metric = _build_passing_metric("FAIL_PERIOD")
    bad_metric["page_count"] = 100
    bad_metric["actual_page_count"] = 120  # Mismatch

    all_passed, results, _summary = evaluate_gate([bad_metric])
    assert all_passed is False
    failing = [r for r in results if r.status == "FAIL"]
    assert any("Period correctness" in r.dimension for r in failing)


def test_cli_failure_exits_1(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves the CLI exits code 1 and prints FAIL when a check fails."""
    from eval.deep_extraction_gate import main

    bad_metric = _build_passing_metric("SYNTHETIC_FAIL")
    bad_metric["segmented_facts_count"] = 5  # Failure

    monkeypatch.setattr("eval.deep_extraction_gate._dsn", lambda: "postgresql://fake")
    monkeypatch.setattr(
        "eval.deep_extraction_gate.collect_metrics_for_ticker",
        lambda **kwargs: bad_metric,
    )
    monkeypatch.setattr("psycopg.connect", MagicMock())
    monkeypatch.setattr("sys.argv", ["deep_extraction_gate.py", "--tickers", "SYNTHETIC_FAIL"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.out
    assert "GATE FAILED" in captured.out


def test_cli_success_exits_0(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Proves the CLI exits code 0 and writes JSON output when all pass."""
    from eval.deep_extraction_gate import main

    good_metric = _build_passing_metric("SYNTHETIC_PASS")
    out_file = tmp_path / "test_gate_out.json"

    monkeypatch.setattr("eval.deep_extraction_gate._dsn", lambda: "postgresql://fake")
    monkeypatch.setattr(
        "eval.deep_extraction_gate.collect_metrics_for_ticker",
        lambda **kwargs: good_metric,
    )
    monkeypatch.setattr("psycopg.connect", MagicMock())
    monkeypatch.setattr(
        "sys.argv",
        ["deep_extraction_gate.py", "--tickers", "SYNTHETIC_PASS", "--out", str(out_file)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "ALL CHECKS PASSED" in captured.out
    assert out_file.exists()
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["summary"]["all_passed"] is True
