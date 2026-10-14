import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(text("SELECT metric_id, category FROM metric_definitions ORDER BY category, metric_id"))
        for r in res.fetchall():
            print(f"{r[0]} ({r[1]})")

asyncio.run(main())
