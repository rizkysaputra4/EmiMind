"""Deterministic fake LLM client for offline unit/integration tests and CI."""

from __future__ import annotations

import re

from services.llm.types import (
    Capabilities,
    LLMClient,
    LLMResponse,
    Message,
    TextBlock,
    ToolCall,
    ToolDef,
    Usage,
)


class FakeLLMClient(LLMClient):
    """Deterministic scriptable fake client for unit and integration testing."""

    provider_id = "fake"

    def __init__(
        self,
        model: str = "fake-reasoner",
        api_key: str = "fake",
        base_url: str | None = None,
        max_output_tokens: int = 1024,
        timeout_s: int = 30,
        scripted_responses: dict[str, LLMResponse] | None = None,
    ) -> None:
        self.model = model
        self.capabilities = Capabilities(
            prompt_caching=True,
            tool_use=True,
            structured_json=True,
            vision=False,
            max_context_tokens=128_000,
            supports_system_message=True,
        )
        self.scripted_responses = scripted_responses or {}

    async def complete(
        self,
        system: list[TextBlock],
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        force_tool: str | None = None,
        max_output_tokens: int = 1024,
        temperature: float = 0.2,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        # 1. Extract prompt text
        user_text = ""
        for m in messages:
            for b in m.blocks:
                if isinstance(b, TextBlock):
                    user_text += " " + b.text
        user_text = user_text.lower()

        # 2. Check for tool forced structured output (e.g. classifier)
        if force_tool == "QueryClassification" or (
            tools and any(t.name == "QueryClassification" for t in tools)
        ):
            # Determine ticker from user text
            tickers = []
            for t in [
                "bmri",
                "bbri",
                "bbca",
                "bbni",
                "adro",
                "ptba",
                "itmg",
                "hrum",
                "indy",
                "bumi",
            ]:
                if t in user_text:
                    tickers.append(t.upper())
            if not tickers:
                tickers = ["BMRI"]

            # Determine intent
            intent = "FACT_LOOKUP"
            if any(
                k in user_text for k in ["why", "kenapa", "mengapa", "driver", "faktor", "analisis"]
            ):
                intent = "EXPLANATION"
            elif any(
                k in user_text
                for k in ["tren", "trend", "historis", "pertumbuhan", "cagr", "yoy", "qoq"]
            ):
                intent = "TREND"
            elif any(k in user_text for k in ["compare", "bandingkan", "peer", "vs", "komparasi"]):
                intent = "COMPARE_PEERS"
            elif any(k in user_text for k in ["screen", "cari", "filter", "ranking"]):
                intent = "SCREEN"
            elif any(k in user_text for k in ["target", "guidance", "panduan", "proyeksi"]):
                intent = "GUIDANCE_CHECK"

            # Determine periods
            periods = ["2024Q4"]
            for m_per in re.findall(r"\b20\d\d[qh][1-4]\b", user_text, re.IGNORECASE):
                periods.append(m_per.upper())

            # Determine concepts
            concepts = []
            if any(k in user_text for k in ["laba", "profit", "net profit"]):
                concepts.append("net_profit")
            if any(k in user_text for k in ["pendapatan", "revenue", "sales"]):
                concepts.append("revenue")
            if any(k in user_text for k in ["nim", "net interest margin", "bunga"]):
                concepts.append("idx:NetInterestIncome")
            if any(k in user_text for k in ["npl", "kredit macet", "non performing"]):
                concepts.append("idx:NonPerformingLoans")
            if any(k in user_text for k in ["kredit", "pinjaman", "loans"]):
                concepts.append("idx:LoansAndAdvances")

            args = {
                "intent": intent,
                "tickers": tickers,
                "periods": list(set(periods)),
                "concepts": concepts or ["net_profit"],
                "is_drill": "drill" in user_text or "q3" in user_text,
                "references_prior_claim": False,
            }

            return LLMResponse(
                text="",
                stop_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="call_fake_classifier_001",
                        name="QueryClassification",
                        arguments=args,
                    )
                ],
                usage=Usage(input_tokens=150, output_tokens=50, cost_usd=0.0),
            )

        # 3. Default text response with rich context-grounded points and valid inline citations
        ticker = "BMRI"
        for t in ["BMRI", "BBRI", "BBCA", "BBNI", "ADRO", "PTBA", "ITMG", "HRUM", "INDY", "BUMI"]:
            if t.lower() in user_text:
                ticker = t
                break

        bullets = [
            f"- Net Interest Income reached IDR 72.30 Trillion [{ticker}-FS-2024Q4#p1], supporting resilient net interest margin.",
            f"- Loan growth was driven by corporate loans, wholesale banking, and commercial expansion [{ticker}-FS-2024Q4#p1].",
            f"- Asset quality remained healthy through prudent underwriting and disciplined credit restructuring, keeping NPL ratio low [{ticker}-FS-2024Q4#p2].",
            f"- Low funding costs were supported by current accounts and savings accounts with a strong CASA ratio [{ticker}-FS-2024Q4#p1].",
            f"- Operating expenses and cost to income ratio (CIR) improved via digital automation and operating discipline [{ticker}-FS-2024Q4#p2].",
        ]

        # Coal specific additions
        if ticker in ("ADRO", "PTBA", "ITMG", "HRUM", "INDY", "BUMI"):
            bullets = [
                f"- Average selling price (ASP) and thermal coal benchmark movements shaped realization [{ticker}-FS-2024Q4#p1].",
                f"- Cash cost per ton was managed via strip ratio optimization and fuel efficiency [{ticker}-FS-2024Q4#p1].",
                f"- Capital expenditure and railway logistics supported stable export and domestic DMO volumes [{ticker}-FS-2024Q4#p2].",
            ]

        bullets_str = "\n".join(bullets)
        response_text = (
            f"Based on reported audited financial disclosures for {ticker} (2024Q4):\n\n"
            f"{bullets_str}\n\n"
            f"_Disclaimer: EmiMind is an AI financial research assistant. Information provided is for informational purposes only and does not constitute financial, investment, or legal advice._"
        )

        return LLMResponse(
            text=response_text,
            stop_reason="end_turn",
            tool_calls=[],
            usage=Usage(input_tokens=450, output_tokens=150, cost_usd=0.001),
        )
