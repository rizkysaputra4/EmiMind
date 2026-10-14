import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.narrative.embedder import Embedder
from sqlalchemy import text
import numpy as np

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
        rq = get_route_query('CASH_BANKS', 'BANK')
        all_terms = list(rq.terms_id) + list(rq.terms_en)
        query_text = " ".join(all_terms)
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
        
        print("Top 15 ANN pages and sims:")
        for p, s in scored[:15]:
            print(f"  P{p}: {s:.4f}")
            
        p183_rank = next((i for i, (p, s) in enumerate(scored) if p == 183), None)
        p186_rank = next((i for i, (p, s) in enumerate(scored) if p == 186), None)
        print(f"P183 rank in ANN: {p183_rank}, P186 rank in ANN: {p186_rank}")

asyncio.run(main())
