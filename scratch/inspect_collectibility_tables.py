import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        for p in [507, 508, 509, 510]:
            res = await conn.execute(
                text("SELECT page_text FROM document_pages WHERE doc_id = :doc_id AND page_index = :page"),
                {"doc_id": DOC_ID, "page": p}
            )
            txt = res.scalar() or ""
            print(f"=== Page {p} ===")
            for l in txt.split("\n"):
                if any(w in l.lower() for w in ["total", "subtotal", "kurang lancar", "diragukan", "macet", "kolektibilitas", "non performing", "npl"]):
                    print(" ", l)

asyncio.run(main())
