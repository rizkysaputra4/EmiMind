import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.retrieval.page_router import rrf_fuse
from sqlalchemy import text
import re
import numpy as np

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
        rq = get_route_query('CASH_BANKS', 'BANK')

        # 1. Page text map
        pages_res = await conn.execute(text("SELECT page_index, page_text FROM document_pages WHERE doc_id = :doc_id ORDER BY page_index ASC"), {"doc_id": doc_id})
        page_text_map = {int(r["page_index"]): str(r["page_text"]) for r in pages_res.mappings().all()}

        # 2. FTS Leg
        all_terms = list(rq.terms_id) + list(rq.terms_en)
        quoted_terms = [f'"{t}"' if " " in t.strip() else t.strip() for t in all_terms if t.strip()]
        web_query = " OR ".join(quoted_terms)

        fts_res = await conn.execute(text("""
            SELECT page_index, ts_rank_cd(tsv, websearch_to_tsquery('simple', :q)) AS rank
            FROM document_pages
            WHERE doc_id = :doc_id AND tsv @@ websearch_to_tsquery('simple', :q)
            ORDER BY rank DESC LIMIT 40
        """), {"doc_id": doc_id, "q": web_query})
        fts_rows = [dict(r) for r in fts_res.mappings().all()]

        # Check excluded pages
        is_core_stmt = any(re.search(r"posisi\s+keuangan|laba\s+rugi|arus\s+kas|financial\s+position|profit\s+or\s+loss|cash\s+flows", pat, re.I) for pat in rq.anchor_patterns)
        excluded_pages = set()
        for p_idx, p_text in page_text_map.items():
            header = p_text[:1000]
            if re.search(r"daftar\s+isi|table\s+of\s+contents|laporan\s+atas\s+reviu|report\s+on\s+review|auditor\s+independen|independent\s+auditor", header, re.I):
                excluded_pages.add(p_idx)
            if not is_core_stmt and re.search(r"laporan\s+posisi\s+keuangan|statement\s+of\s+financial\s+position|laporan\s+laba\s+rugi|statement\s+of\s+profit\s+or\s+loss|laporan\s+arus\s+kas|statement\s+of\s+cash\s+flows|laporan\s+perubahan\s+ekuitas|statement\s+of\s+changes\s+in\s+equity|kebijakan\s+akuntansi|accounting\s+polic", header, re.I):
                excluded_pages.add(p_idx)

        print("P183 excluded?", 183 in excluded_pages)
        print("P184 excluded?", 184 in excluded_pages)
        print("P185 excluded?", 185 in excluded_pages)

        # Check anchors
        primary_anchors = []
        cont_anchors = []
        body_anchors = []
        for p_idx, p_text in page_text_map.items():
            if p_idx in excluded_pages:
                continue
            header = p_text[:1000]
            if any(re.search(pat, header, re.I) for pat in rq.anchor_patterns):
                if re.search(r"\(lanjutan\)|\(continued\)", header, re.I):
                    cont_anchors.append(p_idx)
                else:
                    primary_anchors.append(p_idx)
            elif not is_core_stmt and any(re.search(pat, p_text, re.I) for pat in rq.anchor_patterns):
                body_anchors.append(p_idx)

        print("Primary anchors:", primary_anchors)
        print("Cont anchors:", cont_anchors)
        print("Body anchors count:", len(body_anchors))
        
        anchor_matches = primary_anchors + cont_anchors + body_anchors
        boosted_rows = []
        for am in anchor_matches:
            boosted_rows.append({"page_index": am, "rank": 10.0})
        for r in fts_rows:
            if int(r["page_index"]) not in set(anchor_matches):
                boosted_rows.append(r)
        fts_rows = boosted_rows
        fts_ranked_pages = [int(r["page_index"]) for r in fts_rows]

        # ANN leg
        query_text = " ".join(all_terms)
        from services.narrative.embedder import Embedder
        emb_inst = Embedder()
        q_vec = (await emb_inst.embed([query_text]))[0]
        
        emb_res = await conn.execute(text("SELECT page_index, embedding FROM document_pages WHERE doc_id = :doc_id"), {"doc_id": doc_id})
        rows = [dict(r) for r in emb_res.mappings().all()]
        q_norm = np.linalg.norm(q_vec) + 1e-9
        scored = []
        for r in rows:
            p_emb = np.array(r["embedding"], dtype=float)
            sim = float(np.dot(p_emb, q_vec) / ((np.linalg.norm(p_emb) + 1e-9) * q_norm))
            scored.append((int(r["page_index"]), sim))
        scored.sort(key=lambda s: -s[1])
        ann_ranked_pages = [p for p, _ in scored[:40]]

        fused = rrf_fuse([fts_ranked_pages, ann_ranked_pages])
        print("Top 10 fused seeds:")
        for page, score in fused[:10]:
            f_rank = fts_ranked_pages.index(page) if page in fts_ranked_pages else -1
            a_rank = ann_ranked_pages.index(page) if page in ann_ranked_pages else -1
            print(f"  P{page}: score={score:.4f}, fts_rank={f_rank}, ann_rank={a_rank}")

asyncio.run(main())
