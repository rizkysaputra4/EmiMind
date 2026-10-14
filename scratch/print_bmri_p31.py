import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_text
            FROM document_pages
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index = 31;
        """))
        txt = res.scalar()
        lines = txt.splitlines()
        for i, l in enumerate(lines):
            if 'LABA' in l or 'NET' in l or '61.' in l:
                print(f"{i}: {l}")

if __name__ == '__main__':
    asyncio.run(main())
