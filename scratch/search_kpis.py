import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        for term in ["marjin bunga bersih", "net interest margin", "bopo", "cost of credit", "lar", "loan at risk", "kolektibilitas"]:
            res = await conn.execute(
                text(
                    "SELECT page_index, substring(page_text from '(?i).{0,50}' || :t || '.{0,50}') "
                    "FROM document_pages WHERE doc_id = :doc_id AND page_text ~* :t LIMIT 3"
                ),
                {"doc_id": DOC_ID, "t": term}
            )
            rows = res.fetchall()
            print(f"\n--- Term: '{term}' ({len(rows)} matches) ---")
            for r in rows:
                print(f"  Page {r[0]}: {r[1]}")

asyncio.run(main())
