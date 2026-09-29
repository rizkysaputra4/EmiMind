"""Unit tests for eval/router_recall.py scoring (M9.3.4 remediation). No database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.router_recall import gold_pages, load_gold_datasets, miss_notes, score_module, summarize


def _row(module: str, typ: str, gold: list[int], returned: list[int], ticker: str = "LSIP") -> dict[str, Any]:
    return {"ticker": ticker, "module": module, "type": typ, "doc_id": "d", "gold_file": "g.yaml",
            **score_module(gold, returned)}  # fmt: skip


def test_score_module_recall_and_precision() -> None:
    s = score_module([100, 101], [100, 101, 102, 103])
    assert s["recall"] == 1.0
    assert s["precision"] == 0.5
    assert s["pages_returned"] == 4
    assert s["missed"] == []
    s = score_module([507, 512, 513], [224, 225, 226])
    assert s["recall"] == 0.0 and s["precision"] == 0.0
    assert s["missed"] == [507, 512, 513]
    assert score_module([5], [])["precision"] == 0.0


def test_summary_thresholds_and_precision_gate() -> None:
    good = [_row("BALANCE_SHEET", "core", [14, 15], [14, 15]),
            _row("CASH_BANKS", "notes", [63, 64], [63, 64, 65])]  # fmt: skip
    s = summarize(good, [])
    assert s["thresholds_met"] is True
    assert s["mean_pages_per_module"] == 2.5
    assert s["per_ticker"]["LSIP"]["modules"] == 2

    # recall perfect but 13 pages for 1 gold page -> mean precision 0.08 fails the eval
    wide = [_row("COGS_BREAKDOWN", "notes", [101], list(range(95, 108)))]
    s = summarize(wide, [])
    assert s["thresholds_met"] is False
    assert any("precision" in r for r in s["fail_reasons"])

    low_core = [_row("CASH_FLOW", "core", [35, 36, 37, 38], [37, 38])]
    assert summarize(low_core, [])["thresholds_met"] is False


def test_missing_document_or_module_fails() -> None:
    good = [_row("BALANCE_SHEET", "core", [3, 4], [3, 4])]
    s = summarize(good, [{"gold_file": "AALI_2021Q1.yaml", "reason": "gold document not in documents"}])
    assert s["thresholds_met"] is False
    assert s["failures"] == 1
    assert summarize([], [])["thresholds_met"] is False


def test_notes_list_real_misses() -> None:
    rows = [_row("BANK_LOAN_QUALITY_NPL", "notes", [507, 512, 513], [224, 225, 226], "BMRI")]
    notes = miss_notes(rows, [{"gold_file": "AALI_2021Q1.yaml", "reason": "gold document not in documents"}])
    assert any("AALI_2021Q1.yaml" in n for n in notes)
    assert any("missed gold pages [507, 512, 513]" in n for n in notes)


def test_heldout_gold_files_carry_file_and_sha256() -> None:
    gold_dir = Path(__file__).resolve().parents[2] / "eval" / "router_gold" / "heldout"
    sets = load_gold_datasets(gold_dir)
    assert len(sets) >= 3
    for _name, data in sets:
        assert data.get("file")
        assert len(str(data.get("sha256", ""))) == 64
        assert all(gold_pages(v) for v in data["modules"].values())
