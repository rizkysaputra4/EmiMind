import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'financial_facts'")
        )
        print("financial_facts columns:", [r[0] for r in res.fetchall()])

        res2 = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'derived_facts'")
        )
        print("derived_facts columns:", [r[0] for r in res2.fetchall()])

asyncio.run(main())
