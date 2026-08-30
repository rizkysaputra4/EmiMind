"""Applies forward-only SQL migrations from db/schema to Postgres."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "db" / "schema"


def run_migrations() -> int:
    dsn = os.getenv("EMI_POSTGRES_DSN_SYNC")
    if not dsn:
        # Fallback to convert asyncpg DSN if sync DSN not provided
        async_dsn = os.getenv("EMI_POSTGRES_DSN")
        if async_dsn:
            dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql://")
        else:
            print("Error: EMI_POSTGRES_DSN_SYNC or EMI_POSTGRES_DSN must be set.", file=sys.stderr)
            return 1

    sql_files = sorted(SCHEMA_DIR.glob("*.sql"))
    if not sql_files:
        print(f"No migration files found in {SCHEMA_DIR}")
        return 0

    print(f"Connecting to database to apply migrations from {SCHEMA_DIR}...")
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        filename text PRIMARY KEY,
                        applied_at timestamptz NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute("SELECT filename FROM schema_migrations;")
                applied = {row[0] for row in cur.fetchall()}

                applied_count = 0
                for sql_file in sql_files:
                    filename = sql_file.name
                    if filename in applied:
                        continue

                    print(f"Applying migration: {filename}...")
                    sql_content = sql_file.read_text(encoding="utf-8")
                    with conn.transaction():
                        cur.execute(sql_content)
                        cur.execute(
                            "INSERT INTO schema_migrations (filename) VALUES (%s);",
                            (filename,),
                        )
                    applied_count += 1
                    print(f"Applied: {filename}")

                print(f"Done. {applied_count} migrations applied.")
                return 0
    except Exception as e:
        print(f"Migration error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_migrations())
