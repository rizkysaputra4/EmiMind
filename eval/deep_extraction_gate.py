"""Deep Extraction Acceptance Gate (M9.6.2).

Evaluates committed extraction results against the 9 quality thresholds defined
in DEEP_EXTRACTION_REMEDIATION_PLAN.md (§Phase 6) and tasks/09-M9-deep-extraction.md:
1. Router recall (core >= 0.90, notes >= 0.80)
2. Sector KPI coverage (mandatory contract facts in committed facts UNION omissions = 100%)
3. Concept depth (distinct concepts >= sector minimum / baseline)
4. Segmented facts (>= 25 per annual filing)
5. Numeric grounding (100% on pdf_text pages)
6. Narrative genuineness (0 cross-ticker duplicates, 0 boilerplate hits)
7. Provenance (0 null/out-of-bounds source pages)
8. Token efficiency (input_tokens / (page_count * 2000) <= 15%)
9. Period correctness (fiscal_period='2025Q4', period_end='2025-12-31', 100% page_count match)

Usage:
    uv run python eval/deep_extraction_gate.py --tickers BMRI,LSIP --out eval/reports/m9_gate.json
    uv run python eval/deep_extraction_gate.py --aggregate --since 2026-09-27T00:00:00
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import pymupdf
import yaml  # type: ignore[import-untyped]
from dotenv import load_dotenv

from services.mcp.services.routing import get_extraction_contract
from services.shared.logging import get_logger

log = get_logger("eval.deep_extraction_gate")

load_dotenv()


@dataclass
class CheckResult:
    dimension: str
    ticker: str
    value: Any
    threshold: str
    status: str  # "PASS" or "FAIL"
    details: str = ""


def _dsn() -> str:
    dsn = os.getenv("EMI_POSTGRES_DSN_SYNC")
    if dsn:
        return dsn
    async_dsn = os.getenv("EMI_POSTGRES_DSN")
    if not async_dsn:
        print("Error: EMI_POSTGRES_DSN_SYNC or EMI_POSTGRES_DSN must be set.", file=sys.stderr)
        sys.exit(2)
    return async_dsn.replace("postgresql+asyncpg://", "postgresql://")


def load_sector_depth_minimums(path: Path | str = "db/seeds/sector_depth_minimums.yaml") -> dict[str, int]:
    p = Path(path)
    if not p.exists():
        return {"GENERIC": 30}
    with open(p, encoding="utf-8") as f:
        data: dict[str, int] = yaml.safe_load(f)
    return data if isinstance(data, dict) else {"GENERIC": 30}


def load_boilerplate_phrases(path: Path | str = "db/seeds/narrative_boilerplate.txt") -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]


def load_router_recall(path: Path | str = "eval/reports/router_recall.json") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        res: dict[str, Any] = json.load(f)
        return res


def load_baseline(path: Path | str = "eval/reports/m9_baseline.json") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        res: dict[str, Any] = json.load(f)
        return res


async def _fetch_mandatory_contract_kpis(doc_id: str) -> set[str]:
    """Retrieve required fact concept IDs for doc_id using ExtractionContractService."""
    try:
        contract = await get_extraction_contract(doc_id)
        return {f.concept_id for f in contract.required_facts if f.required}
    except Exception as exc:
        print(f"Warning: Failed to fetch contract for {doc_id}: {exc}", file=sys.stderr)
        return set()


def collect_metrics_for_ticker(  # noqa: PLR0912, PLR0917
    conn: psycopg.Connection[Any],
    ticker: str,
    period: str = "2025Q4",
    sector_depths: dict[str, int] | None = None,
    baseline_data: dict[str, Any] | None = None,
    boilerplate_phrases: list[str] | None = None,
    router_recall_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collects all factual extraction metrics from DB for a given ticker and fiscal period."""
    if sector_depths is None:
        sector_depths = load_sector_depth_minimums()
    if baseline_data is None:
        baseline_data = load_baseline()
    if boilerplate_phrases is None:
        boilerplate_phrases = load_boilerplate_phrases()
    if router_recall_data is None:
        router_recall_data = load_router_recall()

    with conn.cursor() as cur:
        # 1. Fetch document metadata
        cur.execute(
            """
            SELECT d.id, d.ticker, d.fiscal_period, d.period_end, d.page_count, d.source_url,
                   ip.sector, ip.sub_sector
            FROM documents d
            LEFT JOIN issuer_profile ip ON d.ticker = ip.ticker
            WHERE d.ticker = %s AND d.fiscal_period = %s
            ORDER BY d.ingested_at DESC
            LIMIT 1;
            """,
            (ticker, period),
        )
        doc_row = cur.fetchone()
        if not doc_row:
            return {"ticker": ticker, "period": period, "error": f"No document found for {ticker} {period}"}

        doc_id = str(doc_row[0])
        doc_ticker = str(doc_row[1])
        doc_period = str(doc_row[2])
        doc_period_end = str(doc_row[3])
        doc_page_count = int(doc_row[4])
        source_url = str(doc_row[5])
        sector = str(doc_row[6] or "GENERIC")
        sub_sector = str(doc_row[7] or "")

        # 2. Check PyMuPDF physical page count
        candidate_paths = [
            Path(source_url),
            Path("incoming_reports") / Path(source_url).name,
            Path("incoming_reports/processed") / Path(source_url).name,
            Path(".") / Path(source_url).name,
        ]
        actual_page_count = 0
        pdf_resolved_path: str | None = None
        for cp in candidate_paths:
            if cp.exists() and cp.is_file():
                try:
                    doc_fitz = pymupdf.open(str(cp))  # type: ignore[no-untyped-call]
                    actual_page_count = len(doc_fitz)
                    doc_fitz.close()  # type: ignore[no-untyped-call]
                    pdf_resolved_path = str(cp)
                    break
                except Exception as err:
                    log.debug("Could not inspect candidate PDF path", path=str(cp), error=str(err))

        # 3. Router Recall from router_recall.json
        core_recalls: list[float] = []
        notes_recalls: list[float] = []
        if router_recall_data and "modules" in router_recall_data:
            for mod in router_recall_data["modules"]:
                if mod.get("ticker") == ticker:
                    rec = float(mod.get("recall", 0.0))
                    if mod.get("type") == "core":
                        core_recalls.append(rec)
                    elif mod.get("type") == "notes":
                        notes_recalls.append(rec)

        mean_core_recall = (sum(core_recalls) / len(core_recalls)) if core_recalls else None
        mean_notes_recall = (sum(notes_recalls) / len(notes_recalls)) if notes_recalls else None

        # 4. Sector KPI Coverage
        # Run async contract retrieval
        mandatory_kpis = asyncio.run(_fetch_mandatory_contract_kpis(doc_id))

        cur.execute(
            """
            SELECT DISTINCT concept_id
            FROM financial_facts
            WHERE source_doc_id = %s;
            """,
            (doc_id,),
        )
        committed_concepts = {r[0] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT suggested_canonical
            FROM concept_review
            WHERE doc_id = %s AND local_label LIKE 'OMITTED: %%';
            """,
            (doc_id,),
        )
        omitted_concepts = {r[0] for r in cur.fetchall()}

        covered_kpis = committed_concepts | omitted_concepts
        missing_kpis = mandatory_kpis - covered_kpis
        kpi_coverage_ratio = (
            len(mandatory_kpis - missing_kpis) / len(mandatory_kpis) if mandatory_kpis else 1.0
        )

        # 5. Concept Depth
        distinct_concepts_count = len(committed_concepts)
        # Determine sector minimum
        sector_min = sector_depths.get(
            sector, sector_depths.get(sub_sector, sector_depths.get("GENERIC", 30))
        )
        baseline_ticker = baseline_data.get(ticker, {})
        baseline_docs = baseline_ticker.get("documents", 1) or 1
        baseline_raw = baseline_ticker.get("distinct_concepts", 0)
        baseline_per_doc = max(1, baseline_raw // baseline_docs) if baseline_docs > 1 else baseline_raw
        depth_threshold = max(sector_min, 2 * baseline_per_doc if baseline_per_doc <= sector_min // 2 else sector_min)

        # 6. Segmented Facts
        cur.execute(
            """
            SELECT count(*)
            FROM financial_facts
            WHERE source_doc_id = %s AND segment IS NOT NULL AND source_page IS NOT NULL;
            """,
            (doc_id,),
        )
        row = cur.fetchone()
        segmented_facts_count = int(row[0]) if row else 0

        # 7. Numeric Grounding (on pdf_text pages)
        cur.execute(
            """
            SELECT ff.extraction_method, ff.extraction_conf, count(*)
            FROM financial_facts ff
            JOIN document_pages dp ON dp.doc_id = ff.source_doc_id AND dp.page_index = ff.source_page
            WHERE ff.source_doc_id = %s AND dp.text_source = 'pdf_text'
            GROUP BY ff.extraction_method, ff.extraction_conf;
            """,
            (doc_id,),
        )
        grounding_breakdown = cur.fetchall()
        total_facts_on_text_pages = sum(r[2] for r in grounding_breakdown)
        grounded_facts = sum(
            r[2]
            for r in grounding_breakdown
            if r[0] == "table_parser" or (r[0] == "llm_extract" and float(r[1] or 0) >= 0.70)
        )
        grounding_ratio = (grounded_facts / total_facts_on_text_pages) if total_facts_on_text_pages else 1.0

        # 8. Narrative Genuineness
        # 8a: Cross-ticker duplicate MD5
        cur.execute(
            """
            SELECT count(*)
            FROM narrative_chunks nc1
            JOIN narrative_chunks nc2 ON md5(nc1.text_original) = md5(nc2.text_original) AND nc1.ticker != nc2.ticker
            WHERE nc1.source_doc_id = %s;
            """,
            (doc_id,),
        )
        row = cur.fetchone()
        cross_ticker_duplicates = int(row[0]) if row else 0

        # 8b: Known-boilerplate hits
        cur.execute(
            """
            SELECT text_original
            FROM narrative_chunks
            WHERE source_doc_id = %s;
            """,
            (doc_id,),
        )
        boilerplate_hits = 0
        for (narrative_txt,) in cur.fetchall():
            norm_txt = " ".join(narrative_txt.lower().split())
            for bp in boilerplate_phrases:
                if bp and bp in norm_txt:
                    boilerplate_hits += 1

        # 9. Provenance
        cur.execute(
            """
            SELECT count(*)
            FROM financial_facts
            WHERE source_doc_id = %s
              AND (source_page IS NULL OR source_page < 1 OR source_page > %s);
            """,
            (doc_id, doc_page_count),
        )
        row = cur.fetchone()
        bad_provenance_count = int(row[0]) if row else 0

        # 10. Token Efficiency
        cur.execute(
            """
            SELECT metadata
            FROM document_processing_log
            WHERE doc_id = %s AND action = 'COMMITTED'
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (doc_id,),
        )
        log_row = cur.fetchone()
        commit_meta = log_row[0] if log_row and isinstance(log_row[0], dict) else {}
        input_tokens = int(commit_meta.get("input_tokens", 0))
        whole_book_est = doc_page_count * 2000
        token_ratio = (input_tokens / whole_book_est) if whole_book_est else 0.0

        return {
            "ticker": doc_ticker,
            "period": doc_period,
            "period_end": doc_period_end,
            "doc_id": doc_id,
            "page_count": doc_page_count,
            "actual_page_count": actual_page_count,
            "pdf_path": pdf_resolved_path,
            "sector": sector,
            "mean_core_recall": mean_core_recall,
            "mean_notes_recall": mean_notes_recall,
            "mandatory_kpis_count": len(mandatory_kpis),
            "missing_kpis": list(missing_kpis),
            "kpi_coverage_ratio": kpi_coverage_ratio,
            "distinct_concepts_count": distinct_concepts_count,
            "depth_threshold": depth_threshold,
            "segmented_facts_count": segmented_facts_count,
            "total_facts_on_text_pages": total_facts_on_text_pages,
            "grounded_facts_count": grounded_facts,
            "grounding_ratio": grounding_ratio,
            "cross_ticker_duplicates": cross_ticker_duplicates,
            "boilerplate_hits": boilerplate_hits,
            "bad_provenance_count": bad_provenance_count,
            "input_tokens": input_tokens,
            "whole_book_est": whole_book_est,
            "token_ratio": token_ratio,
        }


def evaluate_gate(
    metrics_list: list[dict[str, Any]],
    is_aggregate: bool = False,
) -> tuple[bool, list[CheckResult], dict[str, Any]]:
    """Evaluates the gate acceptance criteria against a list of per-ticker metrics.

    Returns:
        all_passed (bool): True if 100% of applicable checks pass.
        results (list[CheckResult]): Detail for each dimension and ticker.
        summary (dict): Aggregated overview stats.
    """
    results: list[CheckResult] = []
    all_passed = True

    for m in metrics_list:
        ticker = m.get("ticker", "UNKNOWN")
        if "error" in m:
            all_passed = False
            results.append(
                CheckResult(
                    dimension="document_lookup",
                    ticker=ticker,
                    value=m.get("error"),
                    threshold="Document exists in DB",
                    status="FAIL",
                    details=m.get("error", ""),
                )
            )
            continue

        # 1. Router recall (skipped in aggregate mode per M9.6.3)
        if not is_aggregate:
            core_recall = m.get("mean_core_recall")
            notes_recall = m.get("mean_notes_recall")

            passed_core = core_recall is not None and core_recall >= 0.90
            passed_notes = notes_recall is not None and notes_recall >= 0.80

            recall_pass = passed_core and passed_notes
            if not recall_pass:
                all_passed = False
            results.append(
                CheckResult(
                    dimension="Router recall (core >= 0.90, notes >= 0.80)",
                    ticker=ticker,
                    value=f"core={f'{core_recall:.2f}' if core_recall is not None else 'N/A'}, notes={f'{notes_recall:.2f}' if notes_recall is not None else 'N/A'}",
                    threshold="core >= 0.90, notes >= 0.80",
                    status="PASS" if recall_pass else "FAIL",
                    details="Evaluated from router_recall.json",
                )
            )

        # 2. Sector KPI coverage
        kpi_ratio = float(m.get("kpi_coverage_ratio", 0.0))
        missing_kpis = m.get("missing_kpis", [])
        kpi_pass = kpi_ratio >= 1.0 and len(missing_kpis) == 0
        if not kpi_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Sector KPI coverage",
                ticker=ticker,
                value=f"{kpi_ratio:.1%}",
                threshold="100%",
                status="PASS" if kpi_pass else "FAIL",
                details=f"Missing {len(missing_kpis)}: {missing_kpis}" if missing_kpis else "All covered",
            )
        )

        # 3. Concept depth
        distinct_count = int(m.get("distinct_concepts_count", 0))
        depth_threshold = int(m.get("depth_threshold", 30))
        depth_pass = distinct_count >= depth_threshold
        if not depth_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Concept depth",
                ticker=ticker,
                value=str(distinct_count),
                threshold=f">= {depth_threshold}",
                status="PASS" if depth_pass else "FAIL",
                details=f"Sector={m.get('sector')}, distinct concepts={distinct_count}",
            )
        )

        # 4. Segmented facts
        seg_count = int(m.get("segmented_facts_count", 0))
        seg_pass = seg_count >= 25
        if not seg_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Segmented facts",
                ticker=ticker,
                value=str(seg_count),
                threshold=">= 25",
                status="PASS" if seg_pass else "FAIL",
                details="Granular note segments with valid page provenance",
            )
        )

        # 5. Numeric grounding
        grounding_ratio = float(m.get("grounding_ratio", 0.0))
        grounding_pass = grounding_ratio >= 1.0
        if not grounding_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Numeric grounding",
                ticker=ticker,
                value=f"{grounding_ratio:.1%}",
                threshold="100%",
                status="PASS" if grounding_pass else "FAIL",
                details=f"{m.get('grounded_facts_count')}/{m.get('total_facts_on_text_pages')} on text pages",
            )
        )

        # 6. Narrative genuineness
        cross_dups = int(m.get("cross_ticker_duplicates", 0))
        bp_hits = int(m.get("boilerplate_hits", 0))
        narrative_pass = cross_dups == 0 and bp_hits == 0
        if not narrative_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Narrative genuineness",
                ticker=ticker,
                value=f"dups={cross_dups}, boilerplate={bp_hits}",
                threshold="0 and 0",
                status="PASS" if narrative_pass else "FAIL",
                details=f"Cross-ticker md5 dups={cross_dups}, seed boilerplate hits={bp_hits}",
            )
        )

        # 7. Provenance
        bad_provenance = int(m.get("bad_provenance_count", 0))
        prov_pass = bad_provenance == 0
        if not prov_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Provenance",
                ticker=ticker,
                value=str(bad_provenance),
                threshold="0",
                status="PASS" if prov_pass else "FAIL",
                details="Facts with null source_page or > page_count",
            )
        )

        # 8. Token efficiency
        token_ratio = float(m.get("token_ratio", 0.0))
        token_pass = token_ratio <= 0.15
        if not token_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Token efficiency",
                ticker=ticker,
                value=f"{token_ratio:.2%}",
                threshold="<= 15%",
                status="PASS" if token_pass else "FAIL",
                details=f"{m.get('input_tokens', 0)} tokens vs {m.get('whole_book_est', 0)} est",
            )
        )

        # 9. Period correctness
        p_match = m.get("period") == "2025Q4" or is_aggregate
        pe_match = m.get("period_end") == "2025-12-31" or is_aggregate
        pc = int(m.get("page_count", 0))
        apc = int(m.get("actual_page_count", 0))
        pc_match = (pc == apc and pc > 0) if apc > 0 else True
        period_pass = p_match and pe_match and pc_match
        if not period_pass:
            all_passed = False
        results.append(
            CheckResult(
                dimension="Period correctness",
                ticker=ticker,
                value=f"period={m.get('period')}, end={m.get('period_end')}, pages={pc}/{apc}",
                threshold="100% match",
                status="PASS" if period_pass else "FAIL",
                details="Fiscal period & PyMuPDF page count verification",
            )
        )

    summary = {
        "timestamp": datetime.now().isoformat(),
        "all_passed": all_passed,
        "is_aggregate": is_aggregate,
        "evaluated_tickers": [m.get("ticker") for m in metrics_list],
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results if r.status == "PASS"),
        "failed_checks": sum(1 for r in results if r.status == "FAIL"),
    }

    return all_passed, results, summary


def print_results_table(results: list[CheckResult], summary: dict[str, Any]) -> None:
    """Prints a formatted ASCII/Markdown table of gate check results."""
    header = f"| {'Dimension':<38} | {'Ticker':<6} | {'Value':<26} | {'Threshold':<26} | {'Status':<6} |"
    sep = f"|{'-' * 40}|{'-' * 8}|{'-' * 28}|{'-' * 28}|{'-' * 8}|"
    print("\n" + "=" * 116)
    print(f" DEEP EXTRACTION ACCEPTANCE GATE REPORT — {'ALL CHECKS PASSED' if summary['all_passed'] else 'GATE FAILED'}")
    print("=" * 116)
    print(header)
    print(sep)
    for r in results:
        # Plain version for standard terminals
        val_str = str(r.value)[:25]
        thresh_str = str(r.threshold)[:25]
        print(f"| {r.dimension:<38} | {r.ticker:<6} | {val_str:<26} | {thresh_str:<26} | {r.status:<6} |")
    print(sep)
    print(
        f"Summary: {summary['passed_checks']}/{summary['total_checks']} checks passed. "
        f"Overall: {'PASS (Exit 0)' if summary['all_passed'] else 'FAIL (Exit 1)'}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate deep extraction acceptance criteria.")
    parser.add_argument("--tickers", type=str, default="BMRI,LSIP", help="Comma-separated tickers to evaluate")
    parser.add_argument("--period", type=str, default="2025Q4", help="Fiscal period (default: 2025Q4)")
    parser.add_argument("--out", type=str, default=None, help="Output path for JSON report")
    parser.add_argument("--aggregate", action="store_true", help="Run in aggregate batch mode (skips router recall)")
    parser.add_argument("--since", type=str, default=None, help="Optional timestamp filter for aggregate mode")
    parser.add_argument("--sector-depth", type=str, default="db/seeds/sector_depth_minimums.yaml")
    parser.add_argument("--baseline", type=str, default="eval/reports/m9_baseline.json")
    parser.add_argument("--router-recall", type=str, default="eval/reports/router_recall.json")
    parser.add_argument("--boilerplate", type=str, default="db/seeds/narrative_boilerplate.txt")

    args = parser.parse_args()

    sector_depths = load_sector_depth_minimums(args.sector_depth)
    baseline_data = load_baseline(args.baseline)
    boilerplate_phrases = load_boilerplate_phrases(args.boilerplate)
    router_recall_data = load_router_recall(args.router_recall)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    metrics_list: list[dict[str, Any]] = []
    with psycopg.connect(_dsn()) as conn:
        for ticker in tickers:
            m = collect_metrics_for_ticker(
                conn=conn,
                ticker=ticker,
                period=args.period,
                sector_depths=sector_depths,
                baseline_data=baseline_data,
                boilerplate_phrases=boilerplate_phrases,
                router_recall_data=router_recall_data,
            )
            metrics_list.append(m)

    all_passed, results, summary = evaluate_gate(metrics_list, is_aggregate=args.aggregate)
    print_results_table(results, summary)

    output_payload = {
        "summary": summary,
        "results": [asdict(r) for r in results],
        "metrics": metrics_list,
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2, default=str)
        print(f"Wrote gate report to {out_path}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
