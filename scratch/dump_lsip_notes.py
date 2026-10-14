import asyncio
import json
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def dump_pages(doc_id, pages):
    engine = get_engine()
    async with engine.connect() as conn:
        for p in pages:
            print(f"\n==================== LSIP PAGE {p} ====================")
            res = await conn.execute(text("""
                SELECT page_index, table_index, unit_hint, cells
                FROM document_page_tables
                WHERE doc_id = :doc_id AND page_index = :page
                ORDER BY table_index;
            """), {"doc_id": doc_id, "page": p})
            tbls = res.mappings().all()
            for t in tbls:
                cells = t["cells"] if isinstance(t["cells"], list) else json.loads(t["cells"])
                print(f"--- Table {t['table_index']} (cells: {len(cells)}, unit: {t['unit_hint']}) ---")
                rows = {}
                for c in cells:
                    rows.setdefault(c.get("row", 0), []).append(c)
                for r_idx in sorted(rows.keys())[:15]:
                    row_cells = sorted(rows[r_idx], key=lambda x: x.get("col", 0))
                    print(f"R{r_idx:02d}: " + " | ".join(f"[{c.get('col')}]{c.get('text', '')}(val={c.get('value')})" for c in row_cells))

async def main():
    await dump_pages("82e20a07-232e-45bc-9a7b-3b160e8c2ece", [63, 68, 80, 100, 101])

if __name__ == "__main__":
    asyncio.run(main())
