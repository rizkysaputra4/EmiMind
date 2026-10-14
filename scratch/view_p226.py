import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT page_text FROM document_pages WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index = 226")
        )
        print(res.scalar()[:2500])

asyncio.run(main())
