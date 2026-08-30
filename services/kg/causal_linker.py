"""LLM-assisted causal relationship extraction from management discussion sections."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.kg.types import CausalTriple, LinkReport
from services.llm.factory import get_llm
from services.llm.types import Message, TextBlock, ToolDef
from services.shared.logging import get_logger

log = get_logger("kg.causal_linker")

CAUSAL_REGEX = re.compile(
    r"(?:karena|because|due\s+to|didorong\s+oleh|driven\s+by|attributable\s+to|"
    r"disebabkan\s+oleh|seiring\s+dengan|dipengaruhi\s+oleh|resulting\s+from|faktor|drivers)",
    re.IGNORECASE,
)

CAUSAL_TOOL = ToolDef(
    name="CausalExtraction",
    description="Extracts causal relationships (effect -> cause) from narrative disclosures.",
    parameters_schema={
        "type": "object",
        "properties": {
            "triples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "integer", "description": "ID of the chunk"},
                        "effect_metric": {
                            "type": "string",
                            "description": "Financial metric or outcome affected",
                        },
                        "cause_metric_or_phrase": {
                            "type": "string",
                            "description": "Driver or underlying cause phrase",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down", "flat", "increase", "decrease"],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.5,
                            "maximum": 0.8,
                            "description": "Confidence score bounded between 0.50 and 0.80",
                        },
                    },
                    "required": [
                        "chunk_id",
                        "effect_metric",
                        "cause_metric_or_phrase",
                        "direction",
                        "confidence",
                    ],
                },
            }
        },
        "required": ["triples"],
    },
)


def _heuristic_causal_extract(chunk_id: int, text_content: str) -> list[CausalTriple]:
    """Deterministic fallback causal extractor when LLM is offline or in fake mode."""
    results: list[CausalTriple] = []
    t_lower = text_content.lower()

    if ("kredit" in t_lower or "loan" in t_lower) and any(
        w in t_lower for w in ["korporasi", "corporate", "wholesale", "komersial"]
    ):
        results.append(
            CausalTriple(
                effect_metric="idx:LoansAndAdvances",
                cause_metric_or_phrase="Corporate and wholesale loan expansion",
                direction="increase",
                confidence=0.75,
            )
        )
    if ("laba" in t_lower or "profit" in t_lower) and any(
        w in t_lower for w in ["bunga", "interest", "pendapatan"]
    ):
        results.append(
            CausalTriple(
                effect_metric="net_profit",
                cause_metric_or_phrase="Net Interest Income growth and credit cost discipline",
                direction="increase",
                confidence=0.75,
            )
        )
    if "nim" in t_lower and any(w in t_lower for w in ["casa", "dana murah", "giro"]):
        results.append(
            CausalTriple(
                effect_metric="bank.nim",
                cause_metric_or_phrase="High CASA ratio lowering blended cost of funds",
                direction="increase",
                confidence=0.70,
            )
        )
    if ("biaya" in t_lower or "cost" in t_lower or "cir" in t_lower) and any(
        w in t_lower for w in ["digital", "otomasi", "efisiensi"]
    ):
        results.append(
            CausalTriple(
                effect_metric="bank.cir",
                cause_metric_or_phrase="Digital channel migration reducing operating costs",
                direction="decrease",
                confidence=0.70,
            )
        )
    if ("produksi" in t_lower or "production" in t_lower) and any(
        w in t_lower for w in ["cuaca", "weather", "hujan"]
    ):
        results.append(
            CausalTriple(
                effect_metric="mining.production",
                cause_metric_or_phrase="Weather conditions and equipment availability",
                direction="flat",
                confidence=0.65,
            )
        )

    return results


async def _extract_triples_for_batch(batch: list[dict[str, Any]]) -> list[tuple[int, CausalTriple]]:
    """Extracts causal triples for a chunk batch using LLM or heuristic fallback."""
    batch_prompt = "Extract causal relationships (effect -> cause) from disclosures:\n\n"
    for chunk in batch:
        c_text = chunk["text_en"] or chunk["text_original"] or ""
        batch_prompt += f"--- Chunk {chunk['id']} (p.{chunk['source_page']}) ---\n{c_text}\n\n"

    client = get_llm("reasoner")
    extracted_triples: list[tuple[int, CausalTriple]] = []

    try:
        resp = await client.complete(
            system=[
                TextBlock(
                    text="Extract causal graphs. Confidence must be strictly between 0.50 and 0.80."
                )
            ],
            messages=[Message(role="user", blocks=[TextBlock(text=batch_prompt)])],
            tools=[CAUSAL_TOOL],
            force_tool="CausalExtraction",
        )
        for tc in resp.tool_calls:
            if tc.name == "CausalExtraction":
                for item in tc.arguments.get("triples", []):
                    conf = min(0.80, max(0.50, float(item.get("confidence", 0.70))))
                    extracted_triples.append(
                        (
                            int(item["chunk_id"]),
                            CausalTriple(
                                effect_metric=item["effect_metric"],
                                cause_metric_or_phrase=item["cause_metric_or_phrase"],
                                direction=item.get("direction", "up"),
                                confidence=conf,
                            ),
                        )
                    )
    except Exception as e:
        log.warning("LLM causal extraction failed, using heuristics", error=str(e))

    if not extracted_triples:
        for chunk in batch:
            c_text = chunk["text_en"] or chunk["text_original"] or ""
            for h in _heuristic_causal_extract(chunk["id"], c_text):
                extracted_triples.append((chunk["id"], h))

    return extracted_triples


async def link_causes_for_doc(
    conn: AsyncConnection,
    doc_id: UUID,
) -> LinkReport:
    """Extracts causal triples and persists CLAIM/METRIC nodes & CAUSED_BY edges."""
    report = LinkReport(doc_id=doc_id)

    d_res = await conn.execute(
        text("SELECT ticker, fiscal_period FROM documents WHERE id = :id"),
        {"id": str(doc_id)},
    )
    doc = d_res.mappings().first()
    if not doc:
        return report

    ticker = doc["ticker"]
    period = doc["fiscal_period"]

    nc_res = await conn.execute(
        text(
            """
            SELECT id, section, text_original, text_en, source_page
            FROM narrative_chunks
            WHERE source_doc_id = :doc_id
            ORDER BY id ASC;
            """
        ),
        {"doc_id": str(doc_id)},
    )
    all_chunks = nc_res.mappings().all()

    candidate_chunks: list[dict[str, Any]] = [
        dict(c) for c in all_chunks if CAUSAL_REGEX.search(c["text_en"] or c["text_original"] or "")
    ]
    if not candidate_chunks:
        candidate_chunks = [dict(c) for c in all_chunks[:5]]

    report.chunks_analyzed = len(candidate_chunks)
    if not candidate_chunks:
        return report

    batch_size = 10
    max_batches = 5
    batches = [
        candidate_chunks[i : i + batch_size] for i in range(0, len(candidate_chunks), batch_size)
    ][:max_batches]

    for batch in batches:
        triples = await _extract_triples_for_batch(batch)
        for chunk_id, triple in triples:
            claim_payload = {
                "metric": triple.effect_metric,
                "statement": triple.cause_metric_or_phrase,
                "direction": triple.direction,
            }
            claim_src_ref = {"doc_id": str(doc_id), "chunk_id": chunk_id}

            claim_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_nodes (
                        node_type, ticker, fiscal_period, payload, source_ref, created_at
                    )
                    VALUES (
                        'CLAIM', :ticker, :period,
                        CAST(:payload AS jsonb), CAST(:source_ref AS jsonb), now()
                    )
                    RETURNING id;
                    """
                ),
                {
                    "ticker": ticker,
                    "period": period,
                    "payload": json.dumps(claim_payload),
                    "source_ref": json.dumps(claim_src_ref),
                },
            )
            claim_node_id = claim_res.scalar_one()

            metric_payload = {
                "name": triple.cause_metric_or_phrase,
                "category": "DRIVER",
            }
            metric_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_nodes (
                        node_type, ticker, fiscal_period, payload, source_ref, created_at
                    )
                    VALUES (
                        'METRIC', :ticker, :period,
                        CAST(:payload AS jsonb), CAST(:source_ref AS jsonb), now()
                    )
                    RETURNING id;
                    """
                ),
                {
                    "ticker": ticker,
                    "period": period,
                    "payload": json.dumps(metric_payload),
                    "source_ref": json.dumps(claim_src_ref),
                },
            )
            metric_node_id = metric_res.scalar_one()

            edge_payload = {
                "effect": triple.effect_metric,
                "driver": triple.cause_metric_or_phrase,
                "direction": triple.direction,
            }
            edge_res = await conn.execute(
                text(
                    """
                    INSERT INTO kg_edges (
                        src_id, dst_id, edge_type, confidence, payload, created_at
                    )
                    VALUES (:src, :dst, 'CAUSED_BY', :conf, CAST(:payload AS jsonb), now())
                    RETURNING id;
                    """
                ),
                {
                    "src": claim_node_id,
                    "dst": metric_node_id,
                    "conf": triple.confidence,
                    "payload": json.dumps(edge_payload),
                },
            )
            report.edges_created.append(edge_res.scalar_one())

    return report
