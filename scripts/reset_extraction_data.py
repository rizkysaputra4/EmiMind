"""Purge runtime extraction data from Postgres, preserving all config/ontology.

USE WITH CARE. This deletes every extracted fact, narrative, derived metric,
knowledge-graph node, worker-run log, ingest-review queue entry, and citation
report. It does NOT touch config tables (metric_definitions,
sector_metric_contracts, extraction_narrative_rules, xbrl_alias, peer_groups,
concept_map, issuer_profile, users, auth_tokens, schema_migrations).

Usage:
    python scripts/reset_extraction_data.py --yes                         # extraction-pipeline data
    python scripts/reset_extraction_data.py --yes --include-conversations # also chat sessions
    python scripts/reset_extraction_data.py --yes --include-market        # also market/technical
    python scripts/reset_extraction_data.py --yes --all                   # everything above
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()


EXTRACTION_TABLES = [
    "citation_reports",
    "kg_edges",
    "kg_nodes",
    "derived_metrics",
    "narrative_chunks",
    "financial_facts",
    "concept_review",
    "ingest_review_queue",
    "worker_runs",
    "document_page_tables",
    "document_pages",
    "documents",
]

CONVERSATION_TABLES = ["conversation_turns", "chat_sessions"]

MARKET_TABLES = ["technical_state_history", "technical_state", "market_prices"]

# Preserved regardless of flags — these are seeded config, not runtime data.
CONFIG_TABLES_PRESERVED = [
    "metric_definitions",
    "sector_metric_contracts",
    "extraction_narrative_rules",
    "xbrl_alias",
    "peer_groups",
    "concept_map",
    "issuer_profile",
    "users",
    "auth_tokens",
    "schema_migrations",
]


def _dsn() -> str:
    dsn = os.getenv("EMI_POSTGRES_DSN_SYNC")
    if dsn:
        return dsn
    async_dsn = os.getenv("EMI_POSTGRES_DSN")
    if not async_dsn:
        print("Error: EMI_POSTGRES_DSN_SYNC or EMI_POSTGRES_DSN must be set.", file=sys.stderr)
        sys.exit(2)
    return async_dsn.replace("postgresql+asyncpg://", "postgresql://")


def _truncate(cur: psycopg.Cursor, tables: list[str]) -> None:
    for t in tables:
        # Guard with table existence check so tables not yet migrated are safely skipped
        cur.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            );
            """,
            (t,),
        )
        exists = cur.fetchone()[0]
        if exists:
            # RESTART IDENTITY resets serials; CASCADE handles FK dependencies
            cur.execute(f'TRUNCATE TABLE "{t}" RESTART IDENTITY CASCADE;')
            print(f"  truncated {t}")
        else:
            print(f"  skipped {t} (table does not exist)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Confirm destructive operation.")
    parser.add_argument("--include-conversations", action="store_true", help="Also truncate chat_sessions + conversation_turns.")
    parser.add_argument("--include-market", action="store_true", help="Also truncate market_prices + technical_state(_history).")
    parser.add_argument("--all", action="store_true", help="Equivalent to --include-conversations --include-market.")
    args = parser.parse_args()

    if not args.yes:
        print("Refusing to proceed without --yes. This will DELETE data.")
        return 1

    include_conv = args.include_conversations or args.all
    include_mkt = args.include_market or args.all

    targets = list(EXTRACTION_TABLES)
    if include_conv:
        targets.extend(CONVERSATION_TABLES)
    if include_mkt:
        targets.extend(MARKET_TABLES)

    print(f"About to truncate {len(targets)} tables:")
    for t in targets:
        print(f"  - {t}")
    print(f"Preserved (config): {', '.join(CONFIG_TABLES_PRESERVED)}")
    print()

    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            _truncate(cur, targets)
        conn.commit()

    print(f"\nDone. {len(targets)} tables truncated. Config preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
