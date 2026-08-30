"""Review queue management CLI for founder reconciliation of unmapped concepts."""

from __future__ import annotations

import argparse
import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_dsn() -> str:
    dsn = os.getenv("EMI_POSTGRES_DSN_SYNC")
    if not dsn:
        async_dsn = os.getenv("EMI_POSTGRES_DSN")
        if async_dsn:
            dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql://")
        else:
            raise ValueError("Database DSN not configured in environment.")
    return dsn


def list_review_queue(status: str = "open") -> int:
    dsn = get_dsn()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ticker, doc_id, local_label, suggested_canonical, similarity_score, status, created_at
                FROM concept_review
                WHERE status = %s
                ORDER BY created_at DESC;
                """,
                (status,),
            )
            rows = cur.fetchall()

            if not rows:
                print(f"No concept review items found with status '{status}'.")
                return 0

            print(f"\n--- Concept Review Queue [{status.upper()}] ({len(rows)} items) ---")
            print(f"{'ID':<6} {'Ticker':<8} {'Similarity':<12} {'Suggested':<30} {'Local Label'}")
            print("-" * 80)
            for r in rows:
                r_id, ticker, doc_id, label, suggested, score, stat, created_at = r
                score_str = f"{float(score):.2f}" if score is not None else "N/A"
                suggested_str = suggested or "None"
                print(f"{r_id:<6} {ticker:<8} {score_str:<12} {suggested_str:<30} {label}")
            print("-" * 80 + "\n")
            return 0


def resolve_item(item_id: int, canonical_id: str, resolved_by: str = "founder") -> int:
    dsn = get_dsn()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, doc_id, local_label FROM concept_review WHERE id = %s;",
                (item_id,),
            )
            item = cur.fetchone()
            if not item:
                print(f"Error: Review item #{item_id} not found.", file=sys.stderr)
                return 1

            _, doc_id, local_label = item

            # 1. Update concept_review
            cur.execute(
                """
                UPDATE concept_review
                SET status = 'resolved',
                    canonical_final = %s,
                    resolved_by = %s,
                    resolved_at = now()
                WHERE id = %s;
                """,
                (canonical_id, resolved_by, item_id),
            )

            # 2. Update matching financial_facts
            cur.execute(
                """
                UPDATE financial_facts
                SET concept_id = %s,
                    needs_review = false,
                    extraction_conf = 1.0
                WHERE source_doc_id = %s AND concept_local = %s;
                """,
                (canonical_id, doc_id, local_label),
            )
            conn.commit()

            print(f"Successfully resolved item #{item_id} -> '{canonical_id}'")
            return 0


def reject_item(item_id: int, resolved_by: str = "founder") -> int:
    dsn = get_dsn()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE concept_review
                SET status = 'rejected',
                    canonical_final = NULL,
                    resolved_by = %s,
                    resolved_at = now()
                WHERE id = %s;
                """,
                (resolved_by, item_id),
            )
            conn.commit()
            print(f"Item #{item_id} marked as rejected (quarantined).")
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EmiMind Concept Review Queue Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    list_p = subparsers.add_parser("list", help="List items in review queue")
    list_p.add_argument("--status", choices=["open", "resolved", "rejected"], default="open")

    # resolve
    resolve_p = subparsers.add_parser("resolve", help="Resolve an item to a canonical concept ID")
    resolve_p.add_argument("--id", type=int, required=True, help="Review item ID")
    resolve_p.add_argument("--canonical", type=str, required=True, help="Canonical concept ID")

    # reject
    reject_p = subparsers.add_parser("reject", help="Reject and quarantine a review item")
    reject_p.add_argument("--id", type=int, required=True, help="Review item ID")

    args = parser.parse_args()

    if args.command == "list":
        return list_review_queue(args.status)
    elif args.command == "resolve":
        return resolve_item(args.id, args.canonical)
    elif args.command == "reject":
        return reject_item(args.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
