"""Live pipeline test on real filings: inspect -> index -> tables -> route.

Usage: uv run python live_pipeline.py <pdf path> [<pdf path> ...]
"""
import asyncio
import json
import sys
import time

from sqlalchemy import text

from services.ingest.tasks.index_pages import index_pages_task
from services.mcp.services.common import get_engine
from services.mcp.services.inspection import inspect_document


async def main(paths: list[str]) -> None:
    engine = get_engine()
    for path in paths:
        print(f"\n######## {path}")
        t0 = time.time()
        res = await inspect_document(path)
        print("inspect:", res.status, res.ticker, res.fiscal_period, res.doc_type, res.doc_id, "|", res.message[:160])
        if not res.doc_id:
            continue
        async with engine.connect() as conn:
            d = (await conn.execute(text("select fiscal_period, period_end, page_count, doc_type from documents where id=:i"), {"i": res.doc_id})).mappings().first()
            print("documents row:", dict(d) if d else None)
        t1 = time.time()
        try:
            out = await index_pages_task({}, res.doc_id)
            print("index:", out, f"{time.time() - t1:.1f}s")
        except Exception as exc:  # report, keep going
            print("INDEX FAILED:", type(exc).__name__, exc)
            continue
        async with engine.connect() as conn:
            r = (await conn.execute(text(
                """select count(*) pages, count(*) filter (where text_source='ocr') ocr,
                          count(page_label) labelled, min(page_index), max(page_index)
                   from document_pages where doc_id=:i"""), {"i": res.doc_id})).mappings().first()
            print("pages:", dict(r))
            r = (await conn.execute(text(
                """select count(*) tables, count(distinct page_index) pages_with_tables,
                          count(*) filter (where unit_hint is not null) with_unit,
                          jsonb_agg(distinct unit_hint) units
                   from document_page_tables where doc_id=:i"""), {"i": res.doc_id})).mappings().first()
            print("tables:", dict(r))
        print(f"total {time.time() - t0:.1f}s")


asyncio.run(main(sys.argv[1:]))
