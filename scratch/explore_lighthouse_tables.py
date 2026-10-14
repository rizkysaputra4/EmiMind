import asyncio
import json
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def inspect_pages(doc_id, page_indices):
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT page_index, table_index, extraction_method, unit_hint, cells
            FROM document_page_tables
            WHERE doc_id = :doc_id AND page_index = ANY(:pages)
            ORDER BY page_index, table_index;
        """), {"doc_id": doc_id, "pages": page_indices})
        rows = [dict(r) for r in res.mappings().all()]
        return rows

async def main():
    # BMRI Balance sheet pages 22, 23
    bmri_rows = await inspect_pages("a7ccfea3-30b5-4e2d-b357-fb5648386eb2", [22, 23, 30, 35])
    print(f"BMRI found {len(bmri_rows)} tables on pages [22, 23, 30, 35]")
    for r in bmri_rows:
        cells = r["cells"] if isinstance(r["cells"], list) else json.loads(r["cells"])
        print(f"Page {r['page_index']} Tbl {r['table_index']}: {len(cells)} cells, unit_hint={r['unit_hint']}")
        # sample some cell texts
        sample_texts = [c.get("text", "") for c in cells[:10]]
        print("  Sample texts:", sample_texts[:5])

    # LSIP Balance sheet pages 14, 15, IS 16, CF 19
    lsip_rows = await inspect_pages("82e20a07-232e-45bc-9a7b-3b160e8c2ece", [14, 15, 16, 19])
    print(f"\nLSIP found {len(lsip_rows)} tables on pages [14, 15, 16, 19]")
    for r in lsip_rows:
        cells = r["cells"] if isinstance(r["cells"], list) else json.loads(r["cells"])
        print(f"Page {r['page_index']} Tbl {r['table_index']}: {len(cells)} cells, unit_hint={r['unit_hint']}")
        sample_texts = [c.get("text", "") for c in cells[:10]]
        print("  Sample texts:", sample_texts[:5])

if __name__ == "__main__":
    asyncio.run(main())
