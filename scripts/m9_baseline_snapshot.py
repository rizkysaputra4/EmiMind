"""Snapshot pre-remediation extraction metrics into a frozen JSON baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

load_dotenv()


def _dsn() -> str:
    dsn = os.getenv("EMI_POSTGRES_DSN_SYNC")
    if dsn:
        return dsn
    async_dsn = os.getenv("EMI_POSTGRES_DSN")
    if not async_dsn:
        print("Error: EMI_POSTGRES_DSN_SYNC or EMI_POSTGRES_DSN must be set.", file=sys.stderr)
        sys.exit(2)
    return async_dsn.replace("postgresql+asyncpg://", "postgresql://")


def collect_baseline_metrics() -> dict[str, Any]:
    """Queries Postgres for pre-remediation baseline extraction metrics."""
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            # 1. Global totals
            cur.execute(
                """
                SELECT
                    count(DISTINCT concept_id) AS distinct_concepts,
                    count(*) FILTER (WHERE segment IS NOT NULL) AS segmented_facts
                FROM financial_facts;
                """
            )
            gf_row = cur.fetchone()
            global_distinct_concepts = int(gf_row[0]) if gf_row and gf_row[0] is not None else 0
            global_segmented_facts = int(gf_row[1]) if gf_row and gf_row[1] is not None else 0

            cur.execute(
                """
                SELECT
                    count(*) AS narrative_total,
                    count(DISTINCT md5(text_original)) AS narrative_distinct_text
                FROM narrative_chunks;
                """
            )
            gn_row = cur.fetchone()
            global_narrative_total = int(gn_row[0]) if gn_row and gn_row[0] is not None else 0
            global_narrative_distinct_text = (
                int(gn_row[1]) if gn_row and gn_row[1] is not None else 0
            )

            cur.execute(
                """
                SELECT
                    count(*) AS documents,
                    count(*) FILTER (WHERE page_count = 1) AS docs_with_page_count_1,
                    count(*) FILTER (WHERE period_end = '2024-12-31') AS docs_with_period_end_2024_12_31
                FROM documents;
                """
            )
            gd_row = cur.fetchone()
            global_documents = int(gd_row[0]) if gd_row and gd_row[0] is not None else 0
            global_docs_page_count_1 = int(gd_row[1]) if gd_row and gd_row[1] is not None else 0
            global_docs_period_end_2024 = (
                int(gd_row[2]) if gd_row and gd_row[2] is not None else 0
            )

            results: dict[str, Any] = {
                "global": {
                    "distinct_concepts": global_distinct_concepts,
                    "segmented_facts": global_segmented_facts,
                    "narrative_total": global_narrative_total,
                    "narrative_distinct_text": global_narrative_distinct_text,
                    "documents": global_documents,
                    "docs_with_page_count_1": global_docs_page_count_1,
                    "docs_with_period_end_2024_12_31": global_docs_period_end_2024,
                }
            }

            # 2. Per-ticker facts
            cur.execute(
                """
                SELECT
                    ticker,
                    count(DISTINCT concept_id) AS distinct_concepts,
                    count(*) FILTER (WHERE segment IS NOT NULL) AS segmented_facts
                FROM financial_facts
                WHERE ticker IN (SELECT ticker FROM issuer_profile)
                GROUP BY ticker;
                """
            )
            facts_by_ticker = {
                row[0]: {
                    "distinct_concepts": int(row[1]),
                    "segmented_facts": int(row[2]),
                }
                for row in cur.fetchall()
            }

            # 3. Per-ticker narratives
            cur.execute(
                """
                SELECT
                    ticker,
                    count(*) AS narrative_total,
                    count(DISTINCT md5(text_original)) AS narrative_distinct_text
                FROM narrative_chunks
                GROUP BY ticker;
                """
            )
            narratives_by_ticker = {
                row[0]: {
                    "narrative_total": int(row[1]),
                    "narrative_distinct_text": int(row[2]),
                }
                for row in cur.fetchall()
            }

            # 4. Per-ticker documents
            cur.execute(
                """
                SELECT
                    ticker,
                    count(*) AS documents,
                    count(*) FILTER (WHERE page_count = 1) AS docs_with_page_count_1,
                    count(*) FILTER (WHERE period_end = '2024-12-31') AS docs_with_period_end_2024_12_31
                FROM documents
                GROUP BY ticker;
                """
            )
            docs_by_ticker = {
                row[0]: {
                    "documents": int(row[1]),
                    "docs_with_page_count_1": int(row[2]),
                    "docs_with_period_end_2024_12_31": int(row[3]),
                }
                for row in cur.fetchall()
            }

            # Combine all tickers that are in issuer_profile and have facts
            all_tickers = sorted(facts_by_ticker.keys())
            for t in all_tickers:
                t_facts = facts_by_ticker.get(t, {"distinct_concepts": 0, "segmented_facts": 0})
                t_narratives = narratives_by_ticker.get(
                    t, {"narrative_total": 0, "narrative_distinct_text": 0}
                )
                t_docs = docs_by_ticker.get(
                    t,
                    {
                        "documents": 0,
                        "docs_with_page_count_1": 0,
                        "docs_with_period_end_2024_12_31": 0,
                    },
                )

                results[t] = {
                    "distinct_concepts": t_facts["distinct_concepts"],
                    "segmented_facts": t_facts["segmented_facts"],
                    "narrative_total": t_narratives["narrative_total"],
                    "narrative_distinct_text": t_narratives["narrative_distinct_text"],
                    "documents": t_docs["documents"],
                    "docs_with_page_count_1": t_docs["docs_with_page_count_1"],
                    "docs_with_period_end_2024_12_31": t_docs["docs_with_period_end_2024_12_31"],
                }

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=str,
        default="eval/reports/m9_baseline.json",
        help="Output path for baseline metrics JSON.",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = collect_baseline_metrics()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"Baseline snapshot written to {out_path}")
    print(f"Total tickers captured: {len(metrics) - 1}")
    if "BMRI" in metrics:
        print(f"BMRI: {metrics['BMRI']}")
    if "LSIP" in metrics:
        print(f"LSIP: {metrics['LSIP']}")
    print(f"Global: {metrics['global']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
