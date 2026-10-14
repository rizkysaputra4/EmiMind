import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from sqlalchemy import text
import re

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        rq = get_route_query('CASH_BANKS', 'BANK')
        print("Terms:", rq.terms_id, rq.terms_en)
        print("Anchors:", rq.anchor_patterns)
        
        pages_res = await conn.execute(text("SELECT page_index, page_text FROM document_pages WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index BETWEEN 182 AND 192 ORDER BY page_index ASC"))
        for r in pages_res.mappings().all():
            p_idx = r["page_index"]
            header = r["page_text"][:1000]
            matched = [pat for pat in rq.anchor_patterns if re.search(pat, header, re.I)]
            print(f"P{p_idx}: matched anchors -> {matched}")

asyncio.run(main())
