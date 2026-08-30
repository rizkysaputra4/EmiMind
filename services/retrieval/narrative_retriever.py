"""Hybrid ANN + Full-Text Search + Cross-Encoder Reranking retriever for narrative memory (L4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.narrative.embedder import Embedder
from services.narrative.reranker import Reranker
from services.shared.logging import get_logger
from services.shared.types import FiscalPeriod, Ticker

log = get_logger(__name__)


class NarrativeFilters(BaseModel):
    tickers: list[Ticker]
    periods: list[FiscalPeriod] | None = None
    sections: list[str] | None = None


class NarrativeHit(BaseModel):
    chunk_id: int
    ticker: str
    fiscal_period: str | None
    section: str
    source_page: int
    text_original: str
    text_en: str | None
    rerank_score: float
    citation: str


async def retrieve_narrative(
    conn: AsyncConnection,
    query: str,
    filters: NarrativeFilters,
    top_k: int = 6,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> list[NarrativeHit]:
    """Executes hybrid ANN + FTS search over narrative_chunks and reranks candidates."""
    if not filters.tickers:
        return []

    embedder_inst = embedder or Embedder()
    reranker_inst = reranker or Reranker()

    # 1. Base filter clauses
    conditions = ["ticker = ANY(:tickers)"]
    params: dict[str, Any] = {"tickers": [str(t) for t in filters.tickers]}

    if filters.periods:
        conditions.append("fiscal_period = ANY(:periods)")
        params["periods"] = [str(p) for p in filters.periods]

    if filters.sections:
        conditions.append("section = ANY(:sections)")
        params["sections"] = filters.sections

    base_where = " AND ".join(conditions)

    # 2. Check if pgvector is enabled
    has_vec_res = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    has_vector = has_vec_res.first() is not None

    candidates_by_id: dict[int, dict[str, Any]] = {}

    # 3. ANN Top-40 retrieval
    if has_vector:
        try:
            query_embs = await embedder_inst.embed([query])
            if query_embs:
                vec_str = f"[{','.join(str(x) for x in query_embs[0])}]"
                ann_sql = f"""
                SELECT id, ticker, fiscal_period, section, source_page,
                       text_original, text_en, (embedding <=> CAST(:q_vec AS halfvec(1024))) AS ann_dist
                FROM narrative_chunks
                WHERE {base_where} AND embedding IS NOT NULL
                ORDER BY ann_dist ASC
                LIMIT 40;
                """
                ann_params = {**params, "q_vec": vec_str}
                ann_res = await conn.execute(text(ann_sql), ann_params)
                for r in ann_res.mappings():
                    candidates_by_id[r["id"]] = dict(r)
        except Exception as e:
            log.warning("ANN retrieval step failed", error=str(e))

    # 4. FTS Top-40 retrieval
    try:
        fts_sql = f"""
        SELECT id, ticker, fiscal_period, section, source_page,
               text_original, text_en,
               ts_rank_cd(tsv, plainto_tsquery('simple', :query)) AS fts_score
        FROM narrative_chunks
        WHERE {base_where} AND (
            tsv @@ plainto_tsquery('simple', :query) OR
            text_original ILIKE :query_pattern OR
            coalesce(text_en, '') ILIKE :query_pattern
        )
        ORDER BY fts_score DESC
        LIMIT 40;
        """
        fts_params = {**params, "query": query, "query_pattern": f"%{query}%"}
        fts_res = await conn.execute(text(fts_sql), fts_params)
        for r in fts_res.mappings():
            candidates_by_id[r["id"]] = dict(r)
    except Exception as e:
        log.warning("FTS retrieval step failed", error=str(e))

    # Fallback to recent chunks if no hits found
    if not candidates_by_id:
        fallback_sql = f"""
        SELECT id, ticker, fiscal_period, section, source_page, text_original, text_en
        FROM narrative_chunks
        WHERE {base_where}
        ORDER BY extracted_at DESC
        LIMIT 20;
        """
        fb_res = await conn.execute(text(fallback_sql), params)
        for r in fb_res.mappings():
            candidates_by_id[r["id"]] = dict(r)

    if not candidates_by_id:
        return []

    candidate_list = list(candidates_by_id.values())
    texts_for_rerank = [
        c["text_en"] if c.get("text_en") else c["text_original"] for c in candidate_list
    ]

    # 5. Cross-Encoder Rerank
    scores = await reranker_inst.rerank(query, texts_for_rerank)

    # 6. Assemble NarrativeHits
    hits: list[NarrativeHit] = []
    for cand, score in zip(candidate_list, scores, strict=False):
        t_name = cand["ticker"]
        p_name = cand.get("fiscal_period") or "UNKNOWN"
        page = cand["source_page"]
        citation = f"[{t_name}-FS-{p_name}#p{page}]"

        hits.append(
            NarrativeHit(
                chunk_id=cand["id"],
                ticker=t_name,
                fiscal_period=cand.get("fiscal_period"),
                section=cand["section"],
                source_page=page,
                text_original=cand["text_original"],
                text_en=cand.get("text_en"),
                rerank_score=float(score),
                citation=citation,
            )
        )

    # Sort descending by rerank score
    hits.sort(key=lambda h: h.rerank_score, reverse=True)
    return hits[:top_k]
