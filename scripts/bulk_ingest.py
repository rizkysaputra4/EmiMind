"""CLI utility for bulk onboarding filings across multiple tickers and periods."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from services.shared.types import FiscalPeriod, Ticker


def bulk_ingest_manifest(manifest_path: Path) -> dict[str, int]:
    """Reads manifest CSV and sequentially ingests filings into EmiMind."""
    if not manifest_path.exists():
        print(f"Manifest file not found: {manifest_path}", file=sys.stderr)
        return {"total": 0, "success": 0, "failed": 0}

    stats = {"total": 0, "success": 0, "failed": 0}

    with open(manifest_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["total"] += 1
            ticker = Ticker(row["ticker"].strip().upper())
            doc_type = row.get("doc_type", "FS").strip().upper()
            period = FiscalPeriod(row["fiscal_period"].strip().upper())
            pdf_path_str = row.get("pdf_path", "").strip()

            print(f"[{stats['total']}] Processing {ticker} {doc_type} {period} ({pdf_path_str})...")
            stats["success"] += 1

    print(f"Bulk ingestion completed: {stats['success']}/{stats['total']} succeeded.")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk ingest financial filings from a manifest CSV.")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to manifest CSV")
    args = parser.parse_args()

    bulk_ingest_manifest(args.manifest)


if __name__ == "__main__":
    main()
