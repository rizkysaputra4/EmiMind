"""Seeds or updates concept_map table from CSV file."""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

CSV_PATH = Path(__file__).resolve().parent.parent / "db" / "seeds" / "concept_map_seed.csv"


def seed_concept_map() -> int:
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

    print(f"Loading concept map from {CSV_PATH}...")
    rows: list[dict[str, str]] = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("No rows found in seed CSV.")
        return 0

    upsert_sql = """
    INSERT INTO concept_map (
        local_label, sector, psak_version, canonical_concept_id, confidence, created_by
    ) VALUES (%s, %s, %s, %s, %s, 'manual')
    ON CONFLICT (local_label, coalesce(sector, '')) DO UPDATE
    SET psak_version = EXCLUDED.psak_version,
        canonical_concept_id = EXCLUDED.canonical_concept_id,
        confidence = EXCLUDED.confidence;
    """

    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                processed_count = 0
                for r in rows:
                    cur.execute(
                        upsert_sql,
                        (
                            r["local_label"].strip(),
                            r["sector"].strip() if r.get("sector") else None,
                            r["psak_version"].strip() if r.get("psak_version") else None,
                            r["canonical_concept_id"].strip(),
                            float(r.get("confidence", "1.0")),
                        ),
                    )
                    processed_count += 1
                conn.commit()

                cur.execute("SELECT count(*) FROM concept_map;")
                total_in_db = cur.fetchone()[0]  # type: ignore[index]

                print(f"Successfully processed {processed_count} concept mappings.")
                print(f"Total concept_map rows in database: {total_in_db}")
                return 0
    except Exception as e:
        print(f"Error seeding concept_map: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(seed_concept_map())
