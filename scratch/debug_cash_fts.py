import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.retrieval.page_router import rrf_fuse
from sqlalchemy import text
import numpy as np

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        rq = get_route_query('CASH_BANKS', 'BANK')
        all_terms = list(rq.terms_id) + list(rq.terms_en)
        quoted_terms = [f'"{t}"' if " " in t.strip() else t.strip() for t in all_terms if t.strip()]
        web_query = " OR ".join(quoted_terms)
        
        fts_res = await conn.execute(text("""
            SELECT page_index, ts_rank_cd(tsv, websearch_to_tsquery('simple', :q)) AS rank
            FROM document_pages
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
              AND tsv @@ websearch_to_tsquery('simple', :q)
            ORDER BY rank DESC LIMIT 40
        """), {"q": web_query})
        fts_pages = [r["page_index"] for r in fts_res.mappings().all()]
        print("P183 in FTS top 40?", 183 in fts_pages, "rank:", fts_pages.index(183) if 183 in fts_pages else None)
        print("P184 in FTS top 40?", 184 in fts_pages, "rank:", fts_pages.index(184) if 184 in fts_pages else None)
        print("P186 in FTS top 40?", 186 in fts_pages, "rank:", fts_pages.index(186) if 186 in fts_pages else None)
        print("P189 in FTS top 40?", 189 in fts_pages, "rank:", fts_pages.index(189) if 189 in fts_pages else None)

asyncio.run(main())
