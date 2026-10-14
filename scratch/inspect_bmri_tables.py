import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine
import json

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text(
                "SELECT page_index, table_index, cells FROM document_page_tables "
                "WHERE doc_id = :doc_id AND page_index IN (22, 23, 24, 25, 27, 29, 30, 31, 32, 33, 217, 504) "
                "ORDER BY page_index, table_index"
            ),
            {"doc_id": DOC_ID}
        )
        for r in res.fetchall():
            p_idx, t_idx, raw = r
            cells = json.loads(raw) if isinstance(raw, str) else raw
            rows = set(c.get("row") for c in cells)
            print(f"Page {p_idx} Table {t_idx}: {len(cells)} cells, {len(rows)} rows")
            # print first 5 rows
            row_texts = {}
            for c in cells:
                row_texts.setdefault(c.get("row"), {})[c.get("col")] = c.get("text")
            for r_num in sorted(row_texts.keys())[:6]:
                cols = [f"c{col}:{row_texts[r_num].get(col)}" for col in sorted(row_texts[r_num].keys())]
                print(f"  R{r_num}: " + " | ".join(cols))

asyncio.run(main())
