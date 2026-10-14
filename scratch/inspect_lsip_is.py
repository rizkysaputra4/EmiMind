import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine
import json

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text(
                "SELECT cells FROM document_page_tables "
                "WHERE doc_id = '82e20a07-232e-45bc-9a7b-3b160e8c2ece' AND page_index = 16"
            )
        )
        row = res.first()
        if row:
            cells = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            for c in cells:
                if c.get("col") == 0:
                    print(f"Row {c.get('row')}: {c.get('text')}")

asyncio.run(main())
