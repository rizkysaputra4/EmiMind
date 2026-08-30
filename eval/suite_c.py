"""Suite C: Deep Financial Reasoning & Multi-hop Analytical Evaluation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from services.retrieval.chat import run_turn
from services.shared.config import get_settings
from services.shared.db import create_pool

GOLDEN_REASONING_PATH = (
    Path(__file__).resolve().parent / "golden" / "suite_c_reasoning.jsonl"
)


def load_golden_reasoning_questions() -> list[dict[str, Any]]:
    """Loads curated golden reasoning benchmarks."""
    items: list[dict[str, Any]] = []
    if not GOLDEN_REASONING_PATH.exists():
        return items

    with GOLDEN_REASONING_PATH.open("r", encoding="utf-8") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if stripped:
                items.append(json.loads(stripped))
    return items


async def evaluate_reasoning_item(
    conn: Any,
    item: dict[str, Any],
) -> dict[str, Any]:
    """Evaluates a single reasoning question against the chat pipeline."""
    q_text = item["question"]
    expected_points: list[str] = item.get("expected_reasoning_points", [])

    response = await run_turn(
        conn=conn,
        session_id=None,
        message=q_text,
        focus_ticker=item.get("ticker"),
    )

    answer = response.answer
    has_citations = len(response.citations) > 0
    ans_lower = answer.lower()

    # Calculate reasoning points coverage
    matched_points = [p for p in expected_points if any(w in ans_lower for w in p.lower().split())]
    coverage = len(matched_points) / len(expected_points) if expected_points else 1.0

    # Score from 1.0 to 5.0
    score = 1.0
    if has_citations:
        score += 2.0
    score += coverage * 2.0
    score = min(5.0, round(score, 2))

    passed = score >= 4.0

    return {
        "id": item["id"],
        "ticker": item["ticker"],
        "question": q_text,
        "score": score,
        "passed": passed,
        "has_citations": has_citations,
        "citation_count": len(response.citations),
        "coverage": round(coverage * 100.0, 1),
    }


async def run_suite_c(limit: int = 10) -> dict[str, Any]:
    """Runs Suite C reasoning evaluation benchmark."""
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)

    questions = load_golden_reasoning_questions()[:limit]
    total = len(questions)
    results: list[dict[str, Any]] = []
    total_score = 0.0
    passed_count = 0

    async with pool.connect() as conn:
        for q in questions:
            res = await evaluate_reasoning_item(conn, q)
            results.append(res)
            total_score += res["score"]
            if res["passed"]:
                passed_count += 1

    await pool.dispose()

    avg_score = total_score / total if total > 0 else 0.0
    pass_rate = (passed_count / total) * 100.0 if total > 0 else 0.0

    return {
        "total": total,
        "passed": passed_count,
        "avg_score": round(avg_score, 2),
        "pass_rate": round(pass_rate, 1),
        "results": results,
    }


def main() -> None:
    res = asyncio.run(run_suite_c())
    print("\n=======================================================")
    print(" Running EmiMind Eval Suite C: Complex Reasoning Gate")
    print("=======================================================\n")
    print(f"Total Evaluated Questions : {res['total']}")
    print(f"Passed Threshold (>=4.0)  : {res['passed']}")
    print(f"Average Reasoning Score   : {res['avg_score']} / 5.0")
    print(f"Reasoning Pass Rate       : {res['pass_rate']}%\n")
    for r in res["results"]:
        status_str = "PASS" if r["passed"] else "FAIL"
        print(f"  - [{status_str}] {r['id']} ({r['ticker']}): Score {r['score']}/5.0 | Citations: {r['citation_count']} | Coverage: {r['coverage']}%")
    print()


if __name__ == "__main__":
    main()
