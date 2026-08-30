"""Idempotent seed script for peer_groups."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import psycopg

from services.shared.config import get_settings


def seed_peer_groups(csv_path: Path | None = None) -> int:
    """Reads peer_groups_seed.csv and upserts rows into peer_groups table."""
    settings = get_settings()
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent.parent / "db" / "seeds" / "peer_groups_seed.csv"

    if not csv_path.exists():
        print(f"Seed file not found: {csv_path}", file=sys.stderr)
        return 0

    upsert_sql = """
    INSERT INTO peer_groups (id, name, tickers, sector, sub_sector)
    VALUES (%(id)s, %(name)s, %(tickers)s, %(sector)s, %(sub_sector)s)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        tickers = EXCLUDED.tickers,
        sector = EXCLUDED.sector,
        sub_sector = EXCLUDED.sub_sector;
    """

    conn_str = settings.postgres_dsn.replace("+asyncpg", "")
    inserted = 0

    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Clean up tickers array string representation
                    tickers_raw = row["tickers"].strip("{}").split(",")
                    tickers = [t.strip() for t in tickers_raw if t.strip()]
                    params = {
                        "id": row["id"].strip(),
                        "name": row["name"].strip(),
                        "tickers": tickers,
                        "sector": row["sector"].strip() if row["sector"] else None,
                        "sub_sector": row["sub_sector"].strip() if row["sub_sector"] else None,
                    }
                    cur.execute(upsert_sql, params)
                    inserted += 1
        conn.commit()

    print(f"Seeded {inserted} peer groups into peer_groups table.")
    return inserted


if __name__ == "__main__":
    seed_peer_groups()
