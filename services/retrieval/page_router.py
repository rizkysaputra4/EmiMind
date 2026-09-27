"""Semantic and Full-Text Search page router for financial document extraction (M9 Phase 3).

Combines:
1. Full-Text Search (ts_rank_cd + websearch_to_tsquery('simple', ...))
2. Dense ANN Search (embedding cosine distance) when embeddings exist
3. Reciprocal Rank Fusion (RRF: score = Σ 1 / (60 + rank))
4. Header continuation expansion and span merging
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.mcp.types import RouteQuery
from services.narrative.embedder import Embedder
from services.shared.logging import get_logger

log = get_logger(__name__)


@dataclass
class RoutedSpan:
    start_page: int
    end_page: int
    score: float = 0.0
    seed_page: int = 0
    pages: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.pages:
            self.pages = list(range(self.start_page, self.end_page + 1))


def rrf_fuse(ranked_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion over multiple ranked lists of page numbers.

    Formula: score(p) = Σ 1 / (k + rank_i(p)) where rank_i is 1-based.
    Returns: list of (page_number, score) sorted by score descending.
    """
    scores: dict[int, float] = {}
    for r_list in ranked_lists:
        for rank, page_num in enumerate(r_list, start=1):
            scores[page_num] = scores.get(page_num, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def is_continuation(prev_text: str, next_text: str) -> bool:
    """Detects if next_text continues a table or note from prev_text.

    Heuristics:
    - next page has '(lanjutan)' or '(continued)' in its header.
    - or same note number in header without introducing a new note heading.
    - returns False if next page introduces a new note or statement heading without '(lanjutan)'.
    """
    next_header = "\n".join(next_text.splitlines()[:8]).lower()
    prev_header = "\n".join(prev_text.splitlines()[:8]).lower()

    has_cont_marker = "(lanjutan)" in next_header or "(continued)" in next_header

    # Look for note numbers like "12. KREDIT", "Catatan 12", "Note 12", "12."
    prev_notes = re.findall(r"(?:catatan|note|^|\n)\s*(\d{1,3})\.\s*[a-z]", prev_header)
    next_notes = re.findall(r"(?:catatan|note|^|\n)\s*(\d{1,3})\.\s*[a-z]", next_header)

    if has_cont_marker:
        if prev_notes and next_notes:
            return bool(prev_notes[-1] == next_notes[0])
        return True

    # Check same note number without continuation marker:
    if prev_notes and next_notes:
        if prev_notes[-1] == next_notes[0] and len(next_notes) == 1:
            return True

    return False


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merges overlapping or touching page spans.

    Example:
        merge_spans([(5, 6), (6, 8)]) -> [(5, 8)]
    """
    if not spans:
        return []

    sorted_spans = sorted(spans, key=lambda s: (s[0], s[1]))
    merged: list[tuple[int, int]] = []

    for s_start, s_end in sorted_spans:
        if not merged:
            merged.append((s_start, s_end))
            continue
        prev_start, prev_end = merged[-1]
        if s_start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, s_end))
        else:
            merged.append((s_start, s_end))

    return merged


async def _check_has_pgvector(conn: AsyncConnection) -> bool:
    """Checks whether the PostgreSQL vector extension is installed and active."""
    res = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    return res.scalar() is not None


async def route_pages(
    conn: AsyncConnection,
    doc_id: str,
    route_query: RouteQuery,
    top_k: int = 3,
    embedder: Embedder | None = None,
) -> list[RoutedSpan]:
    """Routes a document to the most relevant page spans for a given RouteQuery."""
    # Set statement timeout to 5s
    await conn.execute(text("SET LOCAL statement_timeout = '5000ms'"))

    # 1. Fetch document pages and text map
    pages_res = await conn.execute(
        text(
            """
            SELECT page_index, page_text, embedding IS NOT NULL AS has_emb
            FROM document_pages
            WHERE doc_id = :doc_id
            ORDER BY page_index ASC
            """
        ),
        {"doc_id": doc_id},
    )
    pages_rows = pages_res.mappings().all()
    if not pages_rows:
        return []

    total_pages = len(pages_rows)
    page_text_map = {int(r["page_index"]): str(r["page_text"]) for r in pages_rows}
    all_have_emb = all(r["has_emb"] for r in pages_rows) and total_pages > 0

    all_terms = list(route_query.terms_id) + list(route_query.terms_en)
    if not all_terms:
        return []

    # 2. FTS Leg (websearch_to_tsquery with plainto_tsquery fallback)
    quoted_terms = [f'"{t}"' if " " in t.strip() else t.strip() for t in all_terms if t.strip()]
    web_query = " OR ".join(quoted_terms)
    fallback_query = " ".join(all_terms)

    fts_res = await conn.execute(
        text(
            """
            SELECT page_index,
                   ts_rank_cd(tsv, websearch_to_tsquery('simple', :q)) AS rank
            FROM document_pages
            WHERE doc_id = :doc_id
              AND tsv @@ websearch_to_tsquery('simple', :q)
            ORDER BY rank DESC
            LIMIT 40
            """
        ),
        {"doc_id": doc_id, "q": web_query},
    )
    fts_rows = [dict(r) for r in fts_res.mappings().all()]

    if not fts_rows:
        fts_fallback_res = await conn.execute(
            text(
                """
                SELECT page_index,
                       ts_rank_cd(tsv, plainto_tsquery('simple', :fallback_q)) AS rank
                FROM document_pages
                WHERE doc_id = :doc_id
                  AND tsv @@ plainto_tsquery('simple', :fallback_q)
                ORDER BY rank DESC
                LIMIT 40
                """
            ),
            {"doc_id": doc_id, "fallback_q": fallback_query},
        )
        fts_rows = [dict(r) for r in fts_fallback_res.mappings().all()]

    # Anchor pattern boost: if anchor patterns match, prioritize those pages
    if route_query.anchor_patterns:
        primary_anchors: list[int] = []
        cont_anchors: list[int] = []
        body_anchors: list[int] = []

        is_core_stmt = any(
            re.search(r"posisi\s+keuangan|laba\s+rugi|arus\s+kas|financial\s+position|profit\s+or\s+loss|cash\s+flows", pat, re.I)
            for pat in route_query.anchor_patterns
        )

        for p_idx, p_text in page_text_map.items():
            header = p_text[:1000]
            # Exclude TOC and auditor report pages
            if re.search(
                r"daftar\s+isi|table\s+of\s+contents|laporan\s+atas\s+reviu|report\s+on\s+review|auditor\s+independen|independent\s+auditor",
                header,
                re.I,
            ):
                continue

            if any(re.search(pat, header, re.I) for pat in route_query.anchor_patterns):
                if re.search(r"\(lanjutan\)|\(continued\)", header, re.I):
                    cont_anchors.append(p_idx)
                else:
                    primary_anchors.append(p_idx)
            elif not is_core_stmt and any(re.search(pat, p_text, re.I) for pat in route_query.anchor_patterns):
                body_anchors.append(p_idx)

        anchor_matches = primary_anchors + cont_anchors + body_anchors
        if anchor_matches:
            boosted_rows: list[dict[str, Any]] = []
            for am in anchor_matches:
                boosted_rows.append({"page_index": am, "rank": 10.0})
            for r in fts_rows:
                if int(r["page_index"]) not in set(anchor_matches):
                    boosted_rows.append(r)
            fts_rows = boosted_rows

    fts_ranked_pages = [int(r["page_index"]) for r in fts_rows]

    # 3. ANN Leg (skipped when embeddings are NULL)
    ann_ranked_pages: list[int] = []
    if all_have_emb:
        emb_inst = embedder or Embedder()
        query_text = " ".join(all_terms)
        q_vecs = await emb_inst.embed([query_text])
        q_vec = q_vecs[0] if q_vecs else [0.0] * 1024

        has_pgvector = await _check_has_pgvector(conn)
        if has_pgvector:
            q_vec_list = [float(v) for v in q_vec]
            ann_res = await conn.execute(
                text(
                    """
                    SELECT page_index,
                           (embedding <=> :q_vec::vector) AS dist
                    FROM document_pages
                    WHERE doc_id = :doc_id AND embedding IS NOT NULL
                    ORDER BY dist ASC
                    LIMIT 40
                    """
                ),
                {"doc_id": doc_id, "q_vec": str(q_vec_list)},
            )
            ann_ranked_pages = [int(r["page_index"]) for r in ann_res.mappings().all()]
        else:
            # Fallback ANN computation via numpy cosine similarity
            emb_res = await conn.execute(
                text(
                    """
                    SELECT page_index, embedding
                    FROM document_pages
                    WHERE doc_id = :doc_id AND embedding IS NOT NULL
                    """
                ),
                {"doc_id": doc_id},
            )
            rows = [dict(r) for r in emb_res.mappings().all()]
            if rows:
                q_norm = np.linalg.norm(q_vec) + 1e-9
                scored: list[tuple[int, float]] = []
                for r in rows:
                    p_emb = np.array(r["embedding"], dtype=float)
                    sim = float(np.dot(p_emb, q_vec) / ((np.linalg.norm(p_emb) + 1e-9) * q_norm))
                    scored.append((int(r["page_index"]), sim))
                scored.sort(key=lambda s: -s[1])
                ann_ranked_pages = [p for p, _ in scored[:40]]

    # 4. RRF Fusion
    ranked_lists: list[list[int]] = []
    if fts_ranked_pages:
        ranked_lists.append(fts_ranked_pages)
    if ann_ranked_pages:
        ranked_lists.append(ann_ranked_pages)

    if not ranked_lists:
        return []

    fused_scores = rrf_fuse(ranked_lists)
    top_seeds = fused_scores[:top_k]

    # 5. Span Expansion and Continuation
    raw_spans: list[tuple[int, int, float, int]] = []
    for seed_page, seed_score in top_seeds:
        start = max(1, seed_page - 1)
        end = min(total_pages, seed_page + 1)

        curr = end
        while curr < total_pages and (curr + 1 - start + 1) <= route_query.max_pages:
            prev_p_text = page_text_map.get(curr, "")
            next_p_text = page_text_map.get(curr + 1, "")
            if is_continuation(prev_p_text, next_p_text):
                end = curr + 1
                curr += 1
            else:
                break

        if (end - start + 1) > route_query.max_pages:
            end = start + route_query.max_pages - 1

        raw_spans.append((start, end, seed_score, seed_page))

    # 6. Merge overlapping spans
    span_ranges = [(s[0], s[1]) for s in raw_spans]
    merged_ranges = merge_spans(span_ranges)

    routed_spans: list[RoutedSpan] = []
    for m_start, m_end in merged_ranges:
        # Pick the highest seed score belonging to this merged span
        matching_scores = [
            (s[2], s[3])
            for s in raw_spans
            if not (s[1] < m_start or s[0] > m_end)
        ]
        best_score, best_seed = max(matching_scores, key=lambda x: x[0]) if matching_scores else (0.0, m_start)

        routed_spans.append(
            RoutedSpan(
                start_page=m_start,
                end_page=m_end,
                score=best_score,
                seed_page=best_seed,
            )
        )

    return routed_spans
