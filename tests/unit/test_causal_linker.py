"""Unit tests for causal factor attribution extraction."""

from __future__ import annotations

from services.kg.causal_linker import _heuristic_causal_extract


def test_heuristic_causal_extraction_banking() -> None:
    text = "Pertumbuhan kredit korporasi dan komersial mendorong ekspansi aset dan laba bersih."
    triples = _heuristic_causal_extract(chunk_id=1, text_content=text)
    assert len(triples) >= 1
    assert any(t.effect_metric == "idx:LoansAndAdvances" for t in triples)
    for t in triples:
        assert 0.50 <= t.confidence <= 0.80


def test_heuristic_causal_extraction_nim() -> None:
    text = "NIM didorong oleh rasio CASA dana murah yang stabil di atas 70%."
    triples = _heuristic_causal_extract(chunk_id=2, text_content=text)
    assert len(triples) >= 1
    assert triples[0].effect_metric == "bank.nim"
    assert "CASA" in triples[0].cause_metric_or_phrase
    assert 0.50 <= triples[0].confidence <= 0.80
