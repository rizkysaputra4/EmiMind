import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from sqlalchemy import text

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        rq = get_route_query('BALANCE_SHEET', 'BANK')
        all_terms = list(rq.terms_id) + list(rq.terms_en)
        quoted_terms = [f'"{t}"' if " " in t.strip() else t.strip() for t in all_terms if t.strip()]
        web_query = " OR ".join(quoted_terms)
        res = await conn.execute(text("""
            SELECT page_index, ts_rank_cd(tsv, websearch_to_tsquery('simple', :q)) as r
            FROM document_pages
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
              AND page_index IN (22, 23, 24, 25, 26, 27, 28, 29)
            ORDER BY r DESC
        """), {"q": web_query})
        print("FTS rank values:")
        for r in res.mappings().all():
            print(f"P{r['page_index']}: {r['r']}")

asyncio.run(main())
