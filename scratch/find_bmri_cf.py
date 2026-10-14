import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text(
                "SELECT page_index, page_text FROM document_pages "
                "WHERE doc_id = :doc_id AND page_text ILIKE '%LAPORAN ARUS KAS%' "
                "ORDER BY page_index LIMIT 10"
            ),
            {"doc_id": DOC_ID}
        )
        for r in res.fetchall():
            print(f"Page {r[0]}: {r[1][:100]}...")

asyncio.run(main())
