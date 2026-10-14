import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text(
                "SELECT page_index, substring(page_text from '(?i).{0,40}penyusutan.{0,40}') "
                "FROM document_pages WHERE doc_id = :doc_id AND page_text ~* 'beban penyusutan' LIMIT 5"
            ),
            {"doc_id": DOC_ID}
        )
        for r in res.fetchall():
            print(f"Page {r[0]}: {r[1]}")

asyncio.run(main())
