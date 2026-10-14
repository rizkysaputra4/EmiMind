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
            WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index = 24;
        """))
        for r in res.mappings().all():
            cells = r['cells'] if isinstance(r['cells'], list) else json.loads(r['cells'])
            print(f"Page 24 Tbl {r['table_index']}: {len(cells)} cells")
            rows = {}
            for c in cells:
                rows.setdefault(c.get('row', 0), []).append(c)
            for r_idx in sorted(rows.keys()):
                print(f"R{r_idx}: {[c.get('text') for c in rows[r_idx]]}")

if __name__ == '__main__':
    asyncio.run(main())
