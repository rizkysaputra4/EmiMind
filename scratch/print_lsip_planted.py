import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_index, page_text
            FROM document_pages
            WHERE doc_id = '82e20a07-232e-45bc-9a7b-3b160e8c2ece' AND page_index IN (68, 69, 80)
            ORDER BY page_index;
        """))
        for r in res.mappings().all():
            print(f"=== Page {r['page_index']} ===")
            for l in r['page_text'].splitlines():
                if any(k in l.lower() for k in ['hektar', 'hectare', 'sawit', 'kelapa', 'tanaman', 'menghasilkan', 'mature', 'immature', 'cpo', 'produksi', 'ton']):
                    print(l)

if __name__ == '__main__':
    asyncio.run(main())
