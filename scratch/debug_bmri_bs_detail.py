import asyncio
import selectors
import psycopg
from services.mcp.contracts import get_route_query
from services.retrieval.page_router import route_pages

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    conn = await psycopg.AsyncConnection.connect("postgresql://postgres:postgres@localhost:5432/emimind")
    rq = get_route_query("BALANCE_SHEET", "BANK")
    print("RouteQuery max_pages:", rq.max_pages if rq else None)
    
    # Check FTS query directly
    async with conn.cursor() as cur:
        q_fts = " | ".join(f'"{t}"' for t in rq.terms_id + rq.terms_en)
        await cur.execute("""
            SELECT page_index, ts_rank_cd(tsv, websearch_to_tsquery('simple', %s)) as r
            FROM document_pages
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
              AND page_index BETWEEN 20 AND 32
            ORDER BY page_index
        """, (q_fts,))
        for row in await cur.fetchall():
            print(f"P{row[0]}: ts_rank = {row[1]}")

    spans = await route_pages(conn, 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2', rq, top_k=3)
    print("Spans:", spans)
    await conn.close()

asyncio.run(main())
