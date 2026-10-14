import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine
import json

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        for p in [35, 36, 37, 38]:
            res = await conn.execute(
                text(
                    "SELECT table_index, cells FROM document_page_tables "
                    "WHERE doc_id = :doc_id AND page_index = :page "
                    "ORDER BY table_index"
                ),
                {"doc_id": DOC_ID, "page": p}
            )
            for t_idx, raw in res.fetchall():
                cells = json.loads(raw) if isinstance(raw, str) else raw
                print(f"\n--- Page {p} Table {t_idx} ({len(cells)} cells) ---")
                rows = {}
                for c in cells:
                    rows.setdefault(c.get("row"), {})[c.get("col")] = c.get("text")
                for r in sorted(rows.keys()):
                    cols = [f"c{col}:{rows[r].get(col)}" for col in sorted(rows[r].keys())]
                    line = " | ".join(cols)
                    if any(term in line.lower() for term in ["operasi", "investasi", "pendanaan", "kas neto", "perolehan aset", "arus kas"]):
                        print(f"  R{r}: {line}")

asyncio.run(main())
