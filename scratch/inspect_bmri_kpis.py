import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        for p in [503, 504, 505, 506]:
            res = await conn.execute(
                text("SELECT page_text FROM document_pages WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index = :page"),
                {"page": p}
            )
            txt = res.scalar() or ""
            print(f"=== Page {p} ({len(txt)} chars) ===")
            for line in txt.split("\n"):
                if any(w in line.lower() for w in ["car", "kewajiban penyediaan", "nim", "npl", "bopo", "lar", "cost of credit", "roa", "cost to income", "rasio"]):
                    print(" ", line)

asyncio.run(main())
