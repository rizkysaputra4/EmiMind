import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine
import json

DOC_ID = "82e20a07-232e-45bc-9a7b-3b160e8c2ece"

async def main():
    async with get_engine().connect() as conn:
        for p in [63, 64]:
            res = await conn.execute(
                text("SELECT table_index, cells FROM document_page_tables WHERE doc_id = :doc_id AND page_index = :page"),
                {"doc_id": DOC_ID, "page": p}
            )
            for t_idx, raw in res.fetchall():
                cells = json.loads(raw) if isinstance(raw, str) else raw
                print(f"=== LSIP Page {p} Table {t_idx} ({len(cells)} cells) ===")
                rows = {}
                for c in cells:
                    rows.setdefault(c.get("row"), {})[c.get("col")] = c.get("text")
                for r in sorted(rows.keys()):
                    cols = [f"c{col}:{rows[r].get(col)}" for col in sorted(rows[r].keys())]
                    print(f"  R{r}: " + " | ".join(cols))

asyncio.run(main())
