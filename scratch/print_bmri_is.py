import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_index, page_text
            FROM document_pages
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index IN (30, 31, 32)
            ORDER BY page_index;
        """))
        for r in res.mappings().all():
            print(f"=== Page {r['page_index']} ===")
            for l in r['page_text'].splitlines():
                if any(k in l.lower() for k in ['pendapatan', 'bunga', 'laba', 'beban', 'interest', 'profit', 'revenue']):
                    print(l[:100])

if __name__ == '__main__':
    asyncio.run(main())
