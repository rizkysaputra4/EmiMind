import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text(
                "SELECT page_index FROM document_pages "
                "WHERE doc_id = :doc_id AND page_text ~* '50\\. BEBAN UMUM DAN ADMINISTRASI' LIMIT 1"
            ),
            {"doc_id": DOC_ID}
        )
        p = res.scalar()
        print("Note 50 page:", p)
        if p:
            res_txt = await conn.execute(
                text("SELECT page_text FROM document_pages WHERE doc_id = :doc_id AND page_index = :page"),
                {"doc_id": DOC_ID, "page": p}
            )
            print(res_txt.scalar()[:2000])

asyncio.run(main())
