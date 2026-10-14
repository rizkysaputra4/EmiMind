import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text(
                "SELECT metric_id, importance, extraction_mode FROM metric_definitions "
                "WHERE metric_id IN ('idx:FreeCashFlow', 'idx:EBITDA', 'idx:OperatingExpenses')"
            )
        )
        for r in res.mappings():
            print(dict(r))

asyncio.run(main())
