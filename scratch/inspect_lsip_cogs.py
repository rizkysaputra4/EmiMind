import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine
import json

DOC_ID = "82e20a07-232e-45bc-9a7b-3b160e8c2ece"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT cells FROM document_page_tables WHERE doc_id = :doc_id AND page_index = 101 AND table_index = 2"),
            {"doc_id": DOC_ID}
        )
        row = res.first()
        if row:
            cells = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            for c in cells:
                print(f"R{c.get('row')} C{c.get('col')}: {c.get('text')}")

asyncio.run(main())
