import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text(
                "SELECT page_index FROM document_pages "
                "WHERE doc_id = :doc_id AND page_index >= 490 AND page_text ~* 'diragukan' "
                "ORDER BY page_index"
            ),
            {"doc_id": DOC_ID}
        )
        pages = [r[0] for r in res.fetchall()]
        print("Pages with diragukan:", pages)

asyncio.run(main())
