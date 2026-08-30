"""Suite B: Citation Precision & Evidence Grounding Verification."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy import text

from services.shared.config import get_settings
from services.shared.db import create_pool

CITATION_REGEX = re.compile(
    r"\[([A-Z0-9]{2,10})-([A-Z0-9_]+)-([A-Z0-9_]+)(?:#p(\d+))?\]"
)


async def verify_citation(conn: Any, citation_str: str) -> dict[str, Any]:
    """Verifies that a citation string resolves to a valid document and extracted fact/chunk."""
    m = CITATION_REGEX.match(citation_str)
    if not m:
        return {"citation": citation_str, "valid": False, "reason": "Malformed syntax"}

    ticker, doc_type, period, page_str = m.groups()
    page_num = int(page_str) if page_str else 1

    # 1. Verify document existence
    d_res = await conn.execute(
        text("SELECT id FROM documents WHERE ticker = :ticker AND fiscal_period = :period LIMIT 1"),
        {"ticker": ticker, "period": period},
    )
    doc = d_res.first()
    if not doc:
        return {"citation": citation_str, "valid": False, "reason": "Document not in database"}

    # 2. Verify fact or narrative chunk on that page
    f_res = await conn.execute(
        text("SELECT id FROM financial_facts WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"),
        {"ticker": ticker, "period": period, "page": page_num},
    )
    has_fact = f_res.first() is not None

    nc_res = await conn.execute(
        text("SELECT id FROM narrative_chunks WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"),
        {"ticker": ticker, "period": period, "page": page_num},
    )
    has_chunk = nc_res.first() is not None

    if not has_fact and not has_chunk:
        return {"citation": citation_str, "valid": False, "reason": f"No fact or narrative found on page {page_num}"}

    return {"citation": citation_str, "valid": True, "ticker": ticker, "period": period, "page": page_num}


async def run_suite_b() -> dict[str, Any]:
    """Runs Suite B verification on recent assistant turns in the database."""
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)

    results: list[dict[str, Any]] = []
    total_citations = 0
    passed_citations = 0

    async with pool.connect() as conn:
        # Fetch latest 20 assistant turns
        res = await conn.execute(
            text("SELECT id, content FROM conversation_turns WHERE role = 'assistant' ORDER BY ts DESC LIMIT 20")
        )
        turns = res.mappings().all()

        # If no conversation turns yet, evaluate baseline test citations
        sample_citations = [
            "[BMRI-FS-2024Q4#p1]",
            "[BMRI-FS-2024Q4#p2]",
            "[BMRI-FS-2024Q4#p3]",
        ]

        citations_to_check: list[str] = []
        for t in turns:
            matches = [m.group(0) for m in CITATION_REGEX.finditer(t["content"])]
            citations_to_check.extend(matches)

        if not citations_to_check:
            citations_to_check = sample_citations

        for cit in set(citations_to_check):
            total_citations += 1
            ver = await verify_citation(conn, cit)
            results.append(ver)
            if ver["valid"]:
                passed_citations += 1

    await pool.dispose()
    pass_rate = (passed_citations / total_citations) * 100.0 if total_citations > 0 else 100.0

    return {
        "total": total_citations,
        "passed": passed_citations,
        "failed": total_citations - passed_citations,
        "pass_rate": pass_rate,
        "results": results,
    }


def main() -> None:
    res = asyncio.run(run_suite_b())
    print("\n=======================================================")
    print(" Running EmiMind Eval Suite B: Citation Precision Gate")
    print("=======================================================\n")
    print(f"Total Citations Tested : {res['total']}")
    print(f"Valid Citations        : {res['passed']}")
    print(f"Failed Citations       : {res['failed']}")
    print(f"Citation Precision     : {res['pass_rate']:.1f}%\n")
    for r in res["results"]:
        status_str = "PASS" if r["valid"] else "FAIL"
        extra = f"Page {r.get('page')}" if r["valid"] else f"Reason: {r.get('reason')}"
        print(f"  - [{status_str}] {r['citation']}: {extra}")
    print()


if __name__ == "__main__":
    main()
