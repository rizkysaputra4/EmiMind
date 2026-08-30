"""Unit tests for Prometheus metrics collection and exposition formatting."""

from __future__ import annotations

from services.shared.metrics import MetricsCollector


def test_metrics_collection_and_formatting() -> None:
    collector = MetricsCollector()
    collector.record_turn_latency("FACT_LOOKUP", "complete", 0.45)
    collector.record_tokens("FACT_LOOKUP", "facts", 120)
    collector.record_llm_cost("deepseek-reasoner", 0.00045)
    collector.record_citation_report()

    text_out = collector.generate_prometheus_text()

    assert "emi_turn_latency_seconds_count 1" in text_out
    assert 'emi_prompt_tokens{intent="FACT_LOOKUP",bucket="facts"} 120' in text_out
    assert 'emi_llm_cost_usd{model="deepseek-reasoner"}' in text_out
    assert "emi_citation_reports_total 1" in text_out
