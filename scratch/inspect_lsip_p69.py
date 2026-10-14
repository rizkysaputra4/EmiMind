import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "82e20a07-232e-45bc-9a7b-3b160e8c2ece"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT page_text FROM document_pages WHERE doc_id = :doc_id AND page_index = 69"),
            {"doc_id": DOC_ID}
        )
        print(res.scalar()[:2000])

asyncio.run(main())
