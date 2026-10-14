import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.retrieval.page_router import route_pages

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
        rq = get_route_query('CASH_BANKS', 'BANK')
        
        # What if ann_ranked_pages is empty?
        # Let's test route_pages with a mock embedder that returns [] or with embeddings skipped
        from unittest.mock import AsyncMock
        mock_emb = AsyncMock()
        mock_emb.embed = AsyncMock(return_value=[])
        
        spans = await route_pages(conn, doc_id, rq, top_k=3, embedder=mock_emb)
        print("CASH_BANKS without ANN:", [s.pages for s in spans])

asyncio.run(main())
