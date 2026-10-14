import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT page_text FROM document_pages WHERE doc_id = :doc_id AND page_index = 389"),
            {"doc_id": DOC_ID}
        )
        print(res.scalar()[-1500:])

asyncio.run(main())
