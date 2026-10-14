import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(
            text("SELECT metric_id, name_id, name_en, synonyms_id, extraction_guideline FROM metric_definitions WHERE metric_id = 'idx:LoansAndAdvances'")
        )
        row = res.mappings().first()
        if row:
            for k, v in row.items():
                print(f"{k}: {v}")

asyncio.run(main())
