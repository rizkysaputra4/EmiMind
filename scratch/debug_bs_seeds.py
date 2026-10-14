import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.retrieval.page_router import route_pages

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        rq = get_route_query("BALANCE_SHEET", "BANK")
        spans = await route_pages(conn, 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2', rq, top_k=3)
        print("Spans returned:")
        for s in spans:
            print(f"  Pages {s.pages}, seed {s.seed_page}, score {s.score:.4f}")

asyncio.run(main())
