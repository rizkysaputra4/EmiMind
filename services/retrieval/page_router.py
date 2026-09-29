"""Hybrid page router for financial document extraction (M9 Phase 3).

Three ranked lists are fused with Reciprocal Rank Fusion (score = sum 1 / (60 + rank)):
  1. Full-text search: ts_rank_cd over OR-ed plainto_tsquery('simple', term) (ID + EN terms).
  2. Dense ANN: cosine similarity between the bge-m3 query vector and the page vectors
     (pgvector `<=>` when installed, otherwise numpy over the document's vectors). Only pages
     embedded by the same model as the query embedder take part. If the query cannot be
     embedded, EmbeddingUnavailableError is raised; the router never falls back silently.
  3. Anchors: pages whose note heading / statement title matches an anchor pattern
     (heading starts first, then "(lanjutan)/(continued)" pages).

Pages are then taken seed by seed in fused order, each seed extended over its continuation
pages, until the module's total page budget (`RouteQuery.max_pages`) is spent. Seeds after
the first must score at least SEED_SCORE_RATIO x the best fused score, so a module whose
answer is one page is not padded with weak matches.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.mcp.types import RouteQuery
from services.narrative.embedder import Embedder
from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger(__name__)

RRF_K = 60
LEG_DEPTH = 40  # pages taken from each ranked list
SEED_SCORE_RATIO = 0.7  # extra seeds must match (about) as many legs as the best page
STATEMENT_TIMEOUT = "5000ms"
_HEADER_LINES = 15
_HEADING_SCAN_LINES = 40

_CONT_MARKER = re.compile(r"\((?:lanjutan|continued)\)", re.I)
_NOTE_HEADING = re.compile(r"^\s*(?:catatan\s+|note\s+)?(\d{1,3}[a-z]?)\.\s+([A-Za-z].{2,})$", re.I)
_TOC_OR_AUDIT = re.compile(
    r"daftar\s+isi|table\s+of\s+contents|laporan\s+(?:atas\s+)?reviu|report\s+on\s+(?:the\s+)?review"
    r"|laporan\s+auditor\s+independen|independent\s+auditor",
    re.I,
)
_NOTES_HEADER = re.compile(
    r"catatan\s+atas\s+laporan|notes\s+to\s+(?:the\s+)?(?:interim\s+)?(?:consolidated\s+)?"
    r"(?:interim\s+)?financial",
    re.I,
)
_CORE_TITLE = re.compile(
    r"laporan\s+posisi\s+keuangan|statement\s+of\s+financial\s+position|laporan\s+laba\s+rugi"
    r"|statement\s+of\s+profit\s+or\s+loss|laporan\s+arus\s+kas|statement\s+of\s+cash\s+flows"
    r"|laporan\s+perubahan\s+ekuitas|statement\s+of\s+changes\s+in\s+equity",
    re.I,
)
_POLICY_HEADING = re.compile(
    r"kebijakan\s+akuntansi|accounting\s+polic|pertimbangan,?\s+estimasi|judgements?,?\s+estimates",
    re.I,
)


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


# ---------------------------------------------------------------------------------------
# Pure helpers (unit-tested without a DB)
# ---------------------------------------------------------------------------------------


def rrf_fuse(ranked_lists: Sequence[Sequence[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """score(p) = sum_i 1 / (k + rank_i(p)), rank 1-based; sorted by score desc, page asc."""
    scores: dict[int, float] = {}
    for r_list in ranked_lists:
        for rank, page_num in enumerate(dict.fromkeys(r_list), start=1):
            scores[page_num] = scores.get(page_num, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def _lines(page_text: str, limit: int | None = None) -> list[str]:
    out = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    return out[:limit] if limit else out


def _looks_like_heading(title: str) -> bool:
    """Upper-case ('KAS DAN SETARA KAS') or short Title Case ('Kas dan Setara Kas') text.

    Numbered sentences, list items and table rows ('4. Kas 3,601,905') are rejected.
    """
    letters = [c for c in title if c.isalpha()]
    if len(letters) < 4:
        return False
    if sum(c.isupper() for c in letters) / len(letters) >= 0.8:
        return True
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]*", title) if len(w) > 3]
    return (
        len(title) <= 70
        and not re.search(r"\d", title)
        and bool(words)
        and sum(w[0].isupper() for w in words) / len(words) >= 0.8
    )


def note_headings(page_text: str, limit: int | None = None) -> list[tuple[str, str, bool]]:
    """(note number, heading text, continued?) for lines like '5. KAS DAN SETARA KAS'.

    Bilingual headings often wrap, so the continuation marker '(lanjutan)/(continued)' is
    looked for on the heading line and the line after it.
    """
    lines = _lines(page_text, limit)
    heads: list[tuple[str, str, bool]] = []
    for i, ln in enumerate(lines):
        m = _NOTE_HEADING.match(ln)
        if not m:
            continue
        if not _looks_like_heading(_CONT_MARKER.sub("", m.group(2))):
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        cont = bool(_CONT_MARKER.search(ln)) or (
            bool(_CONT_MARKER.search(nxt)) and not _NOTE_HEADING.match(nxt)
        )
        heads.append((m.group(1).lower(), f"{ln} {nxt}" if nxt else ln, cont))
    return heads


def statement_title(page_text: str) -> str | None:
    """Normalised primary-statement title in the page header ('laporan arus kas'), if any."""
    header = " ".join(_lines(page_text, _HEADER_LINES))
    if _NOTES_HEADER.search(header):
        return None
    m = _CORE_TITLE.search(header)
    return re.sub(r"\s+", " ", m.group(0).lower()) if m else None


def is_continuation(prev_text: str, next_text: str) -> bool:
    """True if next_text continues the note/statement running at the end of prev_text.

    - The next page's first note heading has the same number as prev's last one → True;
      a different number (a new note) → False.
    - No note heading on the next page: True when its header carries '(lanjutan)' /
      '(continued)', or when both pages carry the same primary-statement title in the header
      (filers that repeat 'LAPORAN POSISI KEUANGAN' on every page without a marker).
    """
    prev_heads = note_headings(prev_text)
    next_heads = note_headings(next_text, _HEADING_SCAN_LINES)
    if next_heads:
        return bool(prev_heads) and next_heads[0][0] == prev_heads[-1][0]
    next_header = "\n".join(_lines(next_text, 25))
    if _CONT_MARKER.search(next_header):
        return True
    title = statement_title(next_text)
    return title is not None and title == statement_title(prev_text)


def merge_spans(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merges overlapping or touching page spans: [(5,6),(7,8)] -> [(5,8)]."""
    merged: list[tuple[int, int]] = []
    for s_start, s_end in sorted(spans):
        if merged and s_start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], s_end))
        else:
            merged.append((s_start, s_end))
    return merged


def is_core_statement_query(route_query: RouteQuery) -> bool:
    """A primary-statement module: a statement title among its anchors or search terms."""
    return any(
        _CORE_TITLE.search(p)
        for p in (*route_query.anchor_patterns, *route_query.terms_id, *route_query.terms_en)
    )


def excluded_pages(page_texts: dict[int, str], core_query: bool) -> set[int]:
    """TOC / auditor pages always; for note queries also core statements and policy notes."""
    out: set[int] = set()
    for p_idx, p_text in page_texts.items():
        top = "\n".join(_lines(p_text, _HEADER_LINES))
        if _TOC_OR_AUDIT.search(top):
            out.add(p_idx)
            continue
        if core_query:
            continue
        if _CORE_TITLE.search(top) and not _NOTES_HEADER.search(top):
            out.add(p_idx)
            continue
        heads = note_headings(p_text, _HEADING_SCAN_LINES)
        if len(heads) == 1 and _POLICY_HEADING.search(heads[0][1]):
            out.add(p_idx)
    return out


def anchor_ranking(
    page_texts: dict[int, str], anchor_patterns: Sequence[str], exclude: set[int]
) -> tuple[list[int], set[int]]:
    """(ranked anchor pages, pages where a matching heading starts).

    A heading is a numbered note heading anywhere on the page, or, on a non-notes page
    without note headings, a statement title in the page header. Pages where the heading
    starts rank first, then '(lanjutan)' pages; each group keeps document order.
    """
    if not anchor_patterns:
        return [], set()
    compiled = [re.compile(p, re.I) for p in anchor_patterns]
    starts: list[int] = []
    conts: list[int] = []
    for p_idx in sorted(page_texts):
        if p_idx in exclude:
            continue
        p_text = page_texts[p_idx]
        heads = note_headings(p_text)
        hit_start = hit_cont = False
        for _num, heading, cont in heads:
            if any(c.search(heading) for c in compiled):
                hit_cont = hit_cont or cont
                hit_start = hit_start or not cont
        header = " ".join(_lines(p_text, _HEADER_LINES))
        if not heads and not _NOTES_HEADER.search(header):
            if any(c.search(header) for c in compiled):
                if _CONT_MARKER.search(header):
                    hit_cont = True
                else:
                    hit_start = True
        if hit_start:
            starts.append(p_idx)
        elif hit_cont:
            conts.append(p_idx)
    return starts + conts, set(starts)


def select_pages(
    fused: Sequence[tuple[int, float]],
    page_texts: dict[int, str],
    budget: int,
    top_k: int = 3,
    seed_ratio: float = SEED_SCORE_RATIO,
    heading_starts: set[int] | None = None,
    statement_mode: bool = False,
    exclude: set[int] | None = None,
) -> list[tuple[int, list[int], float]]:
    """Greedy seeds in fused order → (seed, pages, score); total pages <= budget.

    Each seed is extended over its continuation pages: forward always; backward to the
    statement's first page in statement_mode, otherwise by one page (the spec's ±1, applied
    only across a real continuation) when the seed is not itself where a matching heading
    starts. Covered seeds are skipped; seeds after the first need score >= seed_ratio * best.
    """
    if not fused or budget <= 0:
        return []
    starts = heading_starts or set()
    best = fused[0][1]
    chosen: set[int] = set()
    units: list[tuple[int, list[int], float]] = []
    last_page = max(page_texts) if page_texts else 0
    max_back = budget if statement_mode else 1
    skip = exclude or set()
    for seed, score in fused:
        if len(units) >= top_k or len(chosen) >= budget:
            break
        if seed in chosen:
            continue
        if units and score < seed_ratio * best:
            break
        pages = [seed]
        room = budget - len(chosen)
        cur = seed
        while (
            len(pages) < room
            and len(pages) - 1 < max_back
            and (statement_mode or seed not in starts)
            and cur - 1 in page_texts
            and cur - 1 not in chosen
            and cur - 1 not in skip
            and is_continuation(page_texts[cur - 1], page_texts.get(cur, ""))
        ):
            cur -= 1
            pages.insert(0, cur)
        nxt = seed + 1
        while (
            nxt <= last_page
            and len(pages) < room
            and nxt not in chosen
            and nxt not in skip
            and is_continuation(page_texts.get(nxt - 1, ""), page_texts.get(nxt, ""))
        ):
            pages.append(nxt)
            nxt += 1
        chosen.update(pages)
        units.append((seed, pages, score))
    return units


def cosine_top(
    query_vec: Sequence[float], page_vectors: dict[int, Sequence[float]], limit: int = LEG_DEPTH
) -> list[int]:
    """Pages by cosine similarity to query_vec (numpy; used when pgvector is absent)."""
    if not page_vectors:
        return []
    idx = list(page_vectors)
    mat = np.asarray([page_vectors[i] for i in idx], dtype=np.float32)
    q = np.asarray(query_vec, dtype=np.float32)
    denom = np.linalg.norm(mat, axis=1) * (np.linalg.norm(q) or 1.0)
    sims = (mat @ q) / np.where(denom == 0, 1.0, denom)
    order = np.argsort(-sims, kind="stable")[:limit]
    return [idx[i] for i in order]


# ---------------------------------------------------------------------------------------
# Legs that need the database
# ---------------------------------------------------------------------------------------


def fts_query_sql(n_terms: int) -> str:
    """tsquery ORing plainto_tsquery(term_i): every word of a term, in any order/position.

    Phrase (adjacency) matching is deliberately not required: bilingual two-column pages
    interleave the Indonesian and English lines, so "pendapatan dari kontrak dengan
    pelanggan" is rarely contiguous in the text layer. ts_rank_cd still rewards proximity.
    """
    return " || ".join(f"plainto_tsquery('simple', :t{i})" for i in range(n_terms))


async def _fts_ranking(conn: AsyncConnection, doc_id: str, terms: list[str]) -> list[int]:
    clean = [t.strip() for t in terms if t.strip()]
    if not clean:
        return []
    params: dict[str, object] = {f"t{i}": t for i, t in enumerate(clean)}
    params.update({"doc_id": doc_id, "lim": LEG_DEPTH})
    res = await conn.execute(
        text(
            f"""
            WITH q AS (SELECT {fts_query_sql(len(clean))} AS tsq)
            SELECT page_index, ts_rank_cd(tsv, q.tsq) AS rank
            FROM document_pages, q
            WHERE doc_id = :doc_id AND tsv @@ q.tsq
            ORDER BY rank DESC, page_index ASC
            LIMIT :lim
            """
        ),
        params,
    )
    return [int(r["page_index"]) for r in res.mappings().all()]


async def _has_pgvector(conn: AsyncConnection) -> bool:
    res = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    return res.scalar() is not None


async def _ann_ranking(
    conn: AsyncConnection, doc_id: str, route_query: RouteQuery, embedder: Embedder
) -> list[int]:
    """Cosine ranking of the document's pages embedded with embedder.model_id."""
    model_id = embedder.model_id
    cnt = await conn.execute(
        text(
            "SELECT count(*) FROM document_pages "
            "WHERE doc_id = :doc_id AND embedding IS NOT NULL AND embedding_model = :model"
        ),
        {"doc_id": doc_id, "model": model_id},
    )
    n_vecs = int(cnt.scalar() or 0)
    if n_vecs == 0:
        return []

    query_text = "; ".join([*route_query.terms_id, *route_query.terms_en])
    # EmbeddingUnavailableError propagates: routing on FTS + anchors alone would silently
    # degrade recall on bilingual / Indonesian-only filings, so the caller must see it.
    q_vec = (await embedder.embed([query_text]))[0]

    if await _has_pgvector(conn):
        res = await conn.execute(
            text(
                """
                SELECT page_index
                FROM document_pages
                WHERE doc_id = :doc_id AND embedding IS NOT NULL AND embedding_model = :model
                ORDER BY embedding <=> CAST(:q_vec AS halfvec(1024)) ASC
                LIMIT :lim
                """
            ),
            {
                "doc_id": doc_id,
                "model": model_id,
                "q_vec": "[" + ",".join(repr(float(v)) for v in q_vec) + "]",
                "lim": LEG_DEPTH,
            },
        )
        return [int(r["page_index"]) for r in res.mappings().all()]

    max_pages = int(get_settings().router_ann_max_pages)
    if n_vecs > max_pages:
        log.warning(
            "ANN leg skipped: too many pages for in-Python cosine",
            doc_id=doc_id,
            pages=n_vecs,
            limit=max_pages,
        )
        return []
    res = await conn.execute(
        text(
            "SELECT page_index, embedding FROM document_pages "
            "WHERE doc_id = :doc_id AND embedding IS NOT NULL AND embedding_model = :model"
        ),
        {"doc_id": doc_id, "model": model_id},
    )
    vectors = {int(r["page_index"]): r["embedding"] for r in res.mappings().all()}
    return cosine_top(q_vec, vectors)


async def route_pages(
    conn: AsyncConnection,
    doc_id: str,
    route_query: RouteQuery,
    top_k: int = 3,
    embedder: Embedder | None = None,
    *,
    use_ann: bool = True,
) -> list[RoutedSpan]:
    """Routes a document to at most `route_query.max_pages` pages for one module."""
    await conn.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))

    pages_res = await conn.execute(
        text(
            "SELECT page_index, page_text FROM document_pages "
            "WHERE doc_id = :doc_id ORDER BY page_index ASC"
        ),
        {"doc_id": doc_id},
    )
    page_texts = {int(r["page_index"]): str(r["page_text"] or "") for r in pages_res.mappings()}
    terms = [*route_query.terms_id, *route_query.terms_en]
    if not page_texts or not terms:
        return []

    exclude = excluded_pages(page_texts, is_core_statement_query(route_query))
    fts = [p for p in await _fts_ranking(conn, doc_id, terms) if p not in exclude]
    ann: list[int] = []
    if use_ann:
        ann_all = await _ann_ranking(conn, doc_id, route_query, embedder or Embedder())
        ann = [p for p in ann_all if p not in exclude]
    anchors, heading_starts = anchor_ranking(page_texts, route_query.anchor_patterns, exclude)

    fused = rrf_fuse([lst for lst in (fts, ann, anchors) if lst])
    # a primary statement is one contiguous block: a single seed plus its continuation
    core = is_core_statement_query(route_query)
    units = select_pages(
        fused,
        page_texts,
        route_query.max_pages,
        top_k=1 if core else top_k,
        heading_starts=heading_starts,
        statement_mode=core,
        exclude=exclude,
    )
    if not units:
        return []

    page_score: dict[int, tuple[float, int]] = {}
    for seed, pages, score in units:
        for p in pages:
            if p not in page_score or score > page_score[p][0]:
                page_score[p] = (score, seed)

    spans: list[RoutedSpan] = []
    for start, end in merge_spans([(p, p) for p in page_score]):
        members = [p for p in range(start, end + 1) if p in page_score]
        score, seed = max(page_score[p] for p in members)
        spans.append(
            RoutedSpan(start_page=start, end_page=end, score=score, seed_page=seed, pages=members)
        )
    spans.sort(key=lambda s: (-s.score, s.start_page))
    log.debug(
        "routed",
        doc_id=doc_id,
        legs={"fts": len(fts), "ann": len(ann), "anchors": len(anchors)},
        pages=[s.pages for s in spans],
    )
    return spans
