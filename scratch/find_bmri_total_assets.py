import asyncio
import json
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_index, table_index, cells
            FROM document_page_tables
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index BETWEEN 20 AND 30
            ORDER BY page_index;
        """))
        for r in res.mappings().all():
            cells = r['cells'] if isinstance(r['cells'], list) else json.loads(r['cells'])
            for c in cells:
                t = str(c.get('text', '')).lower()
                if 'total aset' in t or 'total assets' in t or 'jumlah aset' in t or 'total liabilitas' in t or 'total ekuitas' in t:
                    print(f"p{r['page_index']} tbl{r['table_index']}: row={c.get('row')} col={c.get('col')} text={c.get('text')} val={c.get('value')}")

if __name__ == '__main__':
    asyncio.run(main())
