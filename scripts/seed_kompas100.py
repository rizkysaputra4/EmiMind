"""Idempotent seed script for KOMPAS100 issuer profiles."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import psycopg

from services.shared.config import get_settings


def seed_kompas100_tickers(csv_path: Path | None = None) -> int:
    """Reads tickers_kompas100.csv and upserts rows into issuer_profile table."""
    settings = get_settings()
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent.parent / "db" / "seeds" / "tickers_kompas100.csv"

    if not csv_path.exists():
        print(f"Seed file not found: {csv_path}", file=sys.stderr)
        return 0

    upsert_sql = """
    INSERT INTO issuer_profile (ticker, name, sector, sub_sector, profile_summary_en, last_facts_period, key_kpis)
    VALUES (%(ticker)s, %(name)s, %(sector)s, %(sub_sector)s, %(summary)s, '2024Q4', %(kpis)s)
    ON CONFLICT (ticker) DO UPDATE SET
        name = EXCLUDED.name,
        sector = EXCLUDED.sector,
        sub_sector = EXCLUDED.sub_sector,
        profile_summary_en = COALESCE(issuer_profile.profile_summary_en, EXCLUDED.profile_summary_en);
    """

    conn_str = settings.postgres_dsn.replace("+asyncpg", "")
    inserted = 0

    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ticker = row["ticker"].strip().upper()
                    name = row["name"].strip()
                    sector = row["sector"].strip().upper()
                    sub_sector = row["sub_sector"].strip()
                    summary = f"{name} ({ticker}) is a KOMPAS100 index constituent operating in the {sector} ({sub_sector}) sector."
                    kpis = ["revenue", "net_profit", "roe", "margin.net"]

                    cur.execute(
                        upsert_sql,
                        {
                            "ticker": ticker,
                            "name": name,
                            "sector": sector,
                            "sub_sector": sub_sector,
                            "summary": summary,
                            "kpis": kpis,
                        },
                    )
                    inserted += 1

            conn.commit()

    print(f"Successfully seeded/upserted {inserted} KOMPAS100 issuer profiles from {csv_path.name}")
    return inserted


if __name__ == "__main__":
    seed_kompas100_tickers()
