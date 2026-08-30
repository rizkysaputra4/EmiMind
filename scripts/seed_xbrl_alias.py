"""Seeds or updates xbrl_alias table from CSV file."""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

CSV_PATH = Path(__file__).resolve().parent.parent / "db" / "seeds" / "xbrl_alias_seed.csv"


def seed_xbrl_alias() -> int:
    dsn = os.getenv("EMI_POSTGRES_DSN_SYNC")
    if not dsn:
        async_dsn = os.getenv("EMI_POSTGRES_DSN")
        if async_dsn:
            dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql://")
        else:
            print("Error: EMI_POSTGRES_DSN_SYNC or EMI_POSTGRES_DSN must be set.", file=sys.stderr)
            return 1

    if not CSV_PATH.exists():
        print(f"Error: Seed file not found at {CSV_PATH}", file=sys.stderr)
        return 1

    print(f"Loading XBRL alias map from {CSV_PATH}...")
    rows: list[dict[str, str]] = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("No rows found in XBRL seed CSV.")
        return 0

    upsert_sql = """
    INSERT INTO xbrl_alias (taxonomy_concept, canonical_concept_id, description)
    VALUES (%s, %s, %s)
    ON CONFLICT (taxonomy_concept) DO UPDATE
    SET canonical_concept_id = EXCLUDED.canonical_concept_id,
        description = EXCLUDED.description;
    """

    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                processed_count = 0
                for r in rows:
                    cur.execute(
                        upsert_sql,
                        (
                            r["taxonomy_concept"].strip(),
                            r["canonical_concept_id"].strip(),
                            r.get("description", "").strip() or None,
                        ),
                    )
                    processed_count += 1
                conn.commit()

                cur.execute("SELECT count(*) FROM xbrl_alias;")
                total_in_db = cur.fetchone()[0]  # type: ignore[index]

                print(f"Successfully processed {processed_count} XBRL alias mappings.")
                print(f"Total xbrl_alias rows in database: {total_in_db}")
                return 0
    except Exception as e:
        print(f"Error seeding xbrl_alias: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(seed_xbrl_alias())
