import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_text FROM document_pages
            WHERE doc_id = '82e20a07-232e-45bc-9a7b-3b160e8c2ece' AND page_index = 64;
        """))
        print(res.scalar())

if __name__ == '__main__':
    asyncio.run(main())
