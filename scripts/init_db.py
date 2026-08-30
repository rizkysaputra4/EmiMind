"""Initializes PostgreSQL role and database for EmiMind."""

from __future__ import annotations

import sys

import psycopg


def init_db() -> int:
    admin_dsn = "postgresql://postgres:postgres@localhost:5432/postgres"
    print("Connecting to local PostgreSQL as superuser...")

    try:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                # 1. Create role emimind if not exists
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'emimind';")
                if not cur.fetchone():
                    cur.execute(
                        "CREATE ROLE emimind WITH LOGIN PASSWORD 'emimind' CREATEDB SUPERUSER;"
                    )
                    print("Created role 'emimind' with superuser privileges.")
                else:
                    print("Role 'emimind' already exists.")

                # 2. Create database emimind if not exists
                cur.execute("SELECT 1 FROM pg_database WHERE datname = 'emimind';")
                if not cur.fetchone():
                    cur.execute("CREATE DATABASE emimind OWNER emimind;")
                    print("Created database 'emimind' owned by 'emimind'.")
                else:
                    print("Database 'emimind' already exists.")

        return 0
    except Exception as e:
        print(f"Failed to initialize database: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(init_db())
