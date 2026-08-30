"""Evaluation test runner CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys

from eval.suite_a import run_suite_a
from eval.suite_b import run_suite_b
from eval.suite_c import run_suite_c
from eval.suite_screener import run_suite_screener


def _run_a() -> int:
    print("\n=======================================================")
    print(" Running EmiMind Eval Suite A: Fact Recall Benchmark  ")
    print("=======================================================\n")
    try:
        results_a = run_suite_a()
        print(f"Total Golden Questions : {results_a['total']}")
        print(f"Passed Assertions      : {results_a['passed']}")
        print(f"Failed Assertions      : {results_a['failed']}")
        print(f"Fact Recall Pass Rate  : {results_a['pass_rate'] * 100:.1f}%\n")

        if results_a["failures"]:
            print("Failed Items Sample:")
            for f in results_a["failures"][:5]:
                print(
                    f"  - [{f['id']}] {f['ticker']} ({f['fiscal_period']}) {f['concept_id']}: {f['reason']}"
                )
            print()
    except Exception as e:
        print(f"Suite A failed to execute: {e}", file=sys.stderr)
        return 1
    return 0


def _run_b() -> int:
    print("\n=======================================================")
    print(" Running EmiMind Eval Suite B: Citation Precision Gate")
    print("=======================================================\n")
    try:
        results_b = asyncio.run(run_suite_b())
        print(f"Total Citations Tested : {results_b['total']}")
        print(f"Valid Citations        : {results_b['passed']}")
        print(f"Failed Citations       : {results_b['failed']}")
        print(f"Citation Precision     : {results_b['pass_rate']:.1f}%\n")
        for r in results_b["results"][:5]:
            status_str = "PASS" if r["valid"] else "FAIL"
            extra = f"Page {r.get('page')}" if r["valid"] else f"Reason: {r.get('reason')}"
            print(f"  - [{status_str}] {r['citation']}: {extra}")
        print()
        if results_b["pass_rate"] < 100.0:
            return 1
    except Exception as e:
        print(f"Suite B failed to execute: {e}", file=sys.stderr)
        return 1
    return 0


def _run_c() -> int:
    print("\n=======================================================")
    print(" Running EmiMind Eval Suite C: Complex Reasoning Gate")
    print("=======================================================\n")
    try:
        results_c = asyncio.run(run_suite_c(limit=5))
        print(f"Total Evaluated Questions : {results_c['total']}")
        print(f"Passed Threshold (>=4.0)  : {results_c['passed']}")
        print(f"Average Reasoning Score   : {results_c['avg_score']} / 5.0")
        print(f"Reasoning Pass Rate       : {results_c['pass_rate']}%\n")
        for r in results_c["results"]:
            status_str = "PASS" if r["passed"] else "FAIL"
            print(
                f"  - [{status_str}] {r['id']} ({r['ticker']}): Score {r['score']}/5.0 "
                f"| Citations: {r['citation_count']} | Coverage: {r['coverage']}%"
            )
        print()
        if results_c["avg_score"] < 4.0:
            return 1
    except Exception as e:
        print(f"Suite C failed to execute: {e}", file=sys.stderr)
        return 1
    return 0


def _run_screener() -> int:
    print("\n=======================================================")
    print(" Running EmiMind Eval Suite Screener Benchmark         ")
    print("=======================================================\n")
    try:
        results_scr = asyncio.run(run_suite_screener())
        print(f"Total Screener Queries : {results_scr.total_queries}")
        print(f"Passed Validations     : {results_scr.passed_queries}")
        print(f"Screener Pass Rate     : {results_scr.pass_rate:.1f}%\n")
        for r in results_scr.results[:5]:
            print(f"  - [{r['status']}] {r['id']}: \"{r['query']}\" (Sector: {r['sector']})")
        print()
        if results_scr.pass_rate < 90.0:
            return 1
    except Exception as e:
        print(f"Suite Screener failed to execute: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EmiMind Evaluation Runner")
    parser.add_argument(
        "--suite",
        choices=["a", "b", "c", "screener", "all"],
        default="a",
        help="Evaluation suite to run (default: a)",
    )
    args = parser.parse_args()

    exit_code = 0
    if args.suite in ("a", "all"):
        exit_code |= _run_a()
    if args.suite in ("b", "all"):
        exit_code |= _run_b()
    if args.suite in ("c", "all"):
        exit_code |= _run_c()
    if args.suite in ("screener", "all"):
        exit_code |= _run_screener()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
