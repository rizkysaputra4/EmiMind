"""Prometheus observability metrics and telemetry instrumentation."""

from __future__ import annotations

import time
from typing import Any

from services.shared.logging import get_logger

log = get_logger("shared.metrics")


class MetricsCollector:
    """In-memory and Prometheus metrics recorder for latency, token counts, and worker health."""

    def __init__(self) -> None:
        self.turn_latencies: list[dict[str, Any]] = []
        self.token_counts: dict[str, int] = {}
        self.llm_costs: dict[str, float] = {}
        self.citation_reports_count: int = 0

    def record_turn_latency(self, intent: str, phase: str, latency_seconds: float) -> None:
        self.turn_latencies.append(
            {"intent": intent, "phase": phase, "latency": latency_seconds, "ts": time.time()}
        )
        if len(self.turn_latencies) > 1000:
            self.turn_latencies = self.turn_latencies[-500:]

    def record_tokens(self, intent: str, bucket: str, tokens: int) -> None:
        key = f"{intent}:{bucket}"
        self.token_counts[key] = self.token_counts.get(key, 0) + tokens

    def record_llm_cost(self, model: str, cost_usd: float) -> None:
        self.llm_costs[model] = self.llm_costs.get(model, 0.0) + cost_usd

    def record_citation_report(self) -> None:
        self.citation_reports_count += 1

    def generate_prometheus_text(self) -> str:
        """Emits standard Prometheus text-based exposition format."""
        lines: list[str] = [
            "# HELP emi_turn_latency_seconds End-to-end and phase latency in seconds",
            "# TYPE emi_turn_latency_seconds summary",
        ]
        if self.turn_latencies:
            avg_lat = sum(x["latency"] for x in self.turn_latencies) / len(self.turn_latencies)
            lines.append(
                f"emi_turn_latency_seconds_sum {sum(x['latency'] for x in self.turn_latencies):.4f}"
            )
            lines.append(f"emi_turn_latency_seconds_count {len(self.turn_latencies)}")
            lines.append(f"emi_turn_latency_seconds_avg {avg_lat:.4f}")

        lines.extend(
            [
                "# HELP emi_prompt_tokens Total prompt and evidence tokens processed",
                "# TYPE emi_prompt_tokens counter",
            ]
        )
        for key, count in self.token_counts.items():
            intent, bucket = key.split(":", 1)
            lines.append(f'emi_prompt_tokens{{intent="{intent}",bucket="{bucket}"}} {count}')

        lines.extend(
            [
                "# HELP emi_llm_cost_usd Cumulative estimated LLM token expenditure in USD",
                "# TYPE emi_llm_cost_usd counter",
            ]
        )
        for model, cost in self.llm_costs.items():
            lines.append(f'emi_llm_cost_usd{{model="{model}"}} {cost:.6f}')

        lines.extend(
            [
                "# HELP emi_citation_reports_total Total human citation accuracy reports submitted",
                "# TYPE emi_citation_reports_total counter",
                f"emi_citation_reports_total {self.citation_reports_count}",
            ]
        )

        return "\n".join(lines) + "\n"


METRICS = MetricsCollector()
