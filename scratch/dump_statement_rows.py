import asyncio
import json
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def dump_table(doc_id, page_idx, tbl_idx=0):
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_index, table_index, cells
            FROM document_page_tables
            WHERE doc_id = :doc_id AND page_index = :page AND table_index = :tbl;
        """), {"doc_id": doc_id, "page": page_idx, "tbl": tbl_idx})
        r = res.mappings().first()
        if not r:
            return
        cells = r["cells"] if isinstance(r["cells"], list) else json.loads(r["cells"])
        # organize cells by row
        rows = {}
        for c in cells:
            row_idx = c.get("row", 0)
            rows.setdefault(row_idx, []).append(c)
        for row_idx in sorted(rows.keys()):
            row_cells = sorted(rows[row_idx], key=lambda x: x.get("col", 0))
            line = " | ".join(f"[{c.get('col')}]{c.get('text', '')}(val={c.get('value')})" for c in row_cells)
            print(f"R{row_idx:02d}: {line}")

async def main():
    print("=== BMRI Page 23 (Assets End / Total Assets) ===")
    await dump_table("a7ccfea3-30b5-4e2d-b357-fb5648386eb2", 23, 0)
    print("\n=== BMRI Page 30 (Income Statement) ===")
    await dump_table("a7ccfea3-30b5-4e2d-b357-fb5648386eb2", 30, 0)
    print("\n=== LSIP Page 14 (Assets) ===")
    await dump_table("82e20a07-232e-45bc-9a7b-3b160e8c2ece", 14, 0)
    print("\n=== LSIP Page 15 (Liab & Equity) ===")
    await dump_table("82e20a07-232e-45bc-9a7b-3b160e8c2ece", 15, 0)
    print("\n=== LSIP Page 16 (Income Statement) ===")
    await dump_table("82e20a07-232e-45bc-9a7b-3b160e8c2ece", 16, 0)

if __name__ == "__main__":
    asyncio.run(main())
