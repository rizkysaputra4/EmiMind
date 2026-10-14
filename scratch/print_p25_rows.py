import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine
import json

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT cells FROM document_page_tables WHERE doc_id = :doc_id AND page_index = 25"),
            {"doc_id": DOC_ID}
        )
        for raw in res.scalars():
            cells = json.loads(raw) if isinstance(raw, str) else raw
            rows = {}
            for c in cells:
                rows.setdefault(c.get("row"), {})[c.get("col")] = c.get("text")
            for r in sorted(rows.keys()):
                cols = [f"c{col}:{rows[r].get(col)}" for col in sorted(rows[r].keys())]
                print(f"R{r}: " + " | ".join(cols))

asyncio.run(main())
