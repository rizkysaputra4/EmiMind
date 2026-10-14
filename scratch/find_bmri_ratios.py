import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_index, page_text
            FROM document_pages
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
              AND page_text ILIKE '%rasio kecukupan modal%'
            ORDER BY page_index
            LIMIT 5;
        """))
        for r in res.mappings().all():
            print(f"CAR found on p{r['page_index']}")

        res2 = await conn.execute(text("""
            SELECT page_index, page_text
            FROM document_pages
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
              AND (page_text ILIKE '%margin bunga bersih%' OR page_text ILIKE '%net interest margin%')
            ORDER BY page_index
            LIMIT 5;
        """))
        for r in res2.mappings().all():
            print(f"NIM found on p{r['page_index']}")

if __name__ == '__main__':
    asyncio.run(main())
