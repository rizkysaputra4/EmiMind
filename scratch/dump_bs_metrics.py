import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT metric_id, category, name_en FROM metric_definitions WHERE category IN ('BALANCE_SHEET', 'CAPITAL', 'CASH_FLOW', 'INCOME', 'CREDIT_QUALITY') ORDER BY category, metric_id")
        )
        for r in res.fetchall():
            print(f"{r[0]} ({r[1]}): {r[2]}")

asyncio.run(main())
