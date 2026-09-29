"""Load db/seeds/announcement_class_rules.csv into announcement_class_rules table."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.shared.config import get_settings

SEED_PATH = Path(__file__).resolve().parents[1] / "db" / "seeds" / "announcement_class_rules.csv"


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.postgres_dsn)
    async with engine.connect() as conn:
        await conn.execute(text("TRUNCATE announcement_class_rules RESTART IDENTITY"))
        with SEED_PATH.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        for row in rows:
            await conn.execute(
                text(
                    """
                    INSERT INTO announcement_class_rules (pattern, doc_type, priority, notes, is_active)
                    VALUES (:pattern, :doc_type, :priority, :notes, TRUE)
                    """
                ),
                {
                    "pattern": row["pattern"],
                    "doc_type": row["doc_type"].strip().upper(),
                    "priority": int(row["priority"]),
                    "notes": row.get("notes") or None,
                },
            )
        await conn.commit()
    print(f"Loaded {len(rows)} announcement classifier rules from {SEED_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
