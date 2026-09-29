"""Commit a small set of REAL LSIP 2025Q3 facts (read from the parsed cells) and inspect what lands in the DB."""
import asyncio
import json

from sqlalchemy import text

from services.mcp.services.common import get_engine
from services.mcp.services.extraction import commit_verified_report, submit_draft_extraction

DOC = "79655cd8-7525-4bb6-ad03-3168d708473d"
M = 1_000_000


def f(cid, val, page, st, cell=None, label=None):
    d = {"concept_id": cid, "value_numeric": str(val * M), "statement": st, "source_page": page, "source_label_original": label or cid}
    if cell:
        d["cell_ref"] = {"table_index": cell[0], "row": cell[1], "col": cell[2]}
    return d


payload = {
    "doc_id": DOC, "ticker": "LSIP", "fiscal_period": "2025Q3",
    "facts": [
        f("ifrs:Assets", 14_784_538, 5, "BS", (1, 8, 1), "Total Liabilitas dan Ekuitas"),
        f("ifrs:Liabilities", 1_425_966, 5, "BS", None, "Total Liabilitas"),
        f("ifrs:Equity", 13_358_572, 5, "BS", (1, 7, 1), "Total Ekuitas"),
        f("ifrs:Revenue", 3_956_904, 6, "IS", None, "Pendapatan dari kontrak dengan pelanggan"),
        f("ifrs:CostOfSales", -2_483_760, 6, "IS", (0, 7, 1), "Beban pokok penjualan"),
        f("ifrs:GrossProfit", 1_473_144, 6, "IS", (0, 8, 1), "Laba bruto"),
        f("ifrs:ProfitLoss", 1_246_424, 6, "IS", (0, 21, 1), "Laba periode berjalan"),
    ],
}


async def main() -> None:
    rep = await submit_draft_extraction(json.dumps(payload))
    print("submit:", rep.status, sorted({i.category for i in rep.issues}))
    # Omit every missing mandatory KPI, INCLUDING cash & equivalents which IS on page 4,
    # to test whether omissions are verified against the cited pages.
    missing = sorted({i.concept_id for i in rep.issues if i.concept_id and "MANDATORY" in i.category})
    payload["omitted_kpis"] = [
        {"metric_id": m, "reason": "NOT_DISCLOSED_IN_REPORT", "explanation": "Reviewer test: not extracted in this partial run.", "search_pages_checked": list(range(1, 114))}
        for m in missing
    ]
    print("omitting", len(missing), "metrics, incl. C&CE:", "ifrs:CashAndCashEquivalents" in missing)
    rep = await submit_draft_extraction(json.dumps(payload))
    print("submit#2:", rep.status, sorted({i.category for i in rep.issues}))
    for i in rep.issues:
        if "MANDATORY" not in i.category:
            print("  ", i.severity, i.category, i.feedback_message[:200])
    eng = get_engine()
    async with eng.connect() as conn:
        before = (await conn.execute(text("select count(*) from narrative_chunks where source_doc_id=:d"), {"d": DOC})).scalar()
    com = await commit_verified_report(json.dumps(payload))
    print("commit:", com.status, "facts", com.facts_committed, "narratives", com.narratives_committed, "|", (com.message or "")[:300] if hasattr(com, "message") else "")
    async with eng.connect() as conn:
        rows = (await conn.execute(text(
            """select concept_id, value_numeric, statement, period_type, extraction_method, extraction_conf,
                      needs_review, source_bbox::text bbox from financial_facts where source_doc_id=:d order by id"""), {"d": DOC})).mappings().all()
        for r in rows:
            print(dict(r))
        after = (await conn.execute(text("select count(*) from narrative_chunks where source_doc_id=:d"), {"d": DOC})).scalar()
        sample = (await conn.execute(text("select section, source_page, left(text_original,160) t from narrative_chunks where source_doc_id=:d limit 4"), {"d": DOC})).mappings().all()
        print(f"narrative_chunks before={before} after={after}")
        for s in sample:
            print("  ", dict(s))


asyncio.run(main())
