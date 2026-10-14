import asyncio
import json
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT cells FROM document_page_tables
            WHERE doc_id = '82e20a07-232e-45bc-9a7b-3b160e8c2ece' AND page_index = 19 AND table_index = 0;
        """))
        cells = res.scalar()
        if isinstance(cells, str):
            cells = json.loads(cells)
        rows = {}
        for c in cells:
            rows.setdefault(c.get("row", 0), []).append(c)
        for r_idx in sorted(rows.keys()):
            row_cells = sorted(rows[r_idx], key=lambda x: x.get("col", 0))
            print(f"R{r_idx:02d}: " + " | ".join(f"[{c.get('col')}]{c.get('text', '')}(val={c.get('value')})" for c in row_cells))

if __name__ == '__main__':
    asyncio.run(main())
