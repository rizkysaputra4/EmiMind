import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT page_text FROM document_pages WHERE doc_id = :doc_id AND page_index = 35"),
            {"doc_id": DOC_ID}
        )
        txt = res.scalar() or ""
        for line in txt.split("\n"):
            if "penyusutan" in line.lower() or "amortisasi" in line.lower():
                print(line)

asyncio.run(main())
