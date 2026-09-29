"""Inspect + index copies of real filings (workstream B verification)."""
import asyncio, sys, time
from services.mcp.services.inspection import inspect_document
from services.ingest.tasks.index_pages import index_pages_task

async def main(paths):
    for p in paths:
        t = time.time()
        r = await inspect_document(p)
        print("INSPECT", p.split("/")[-1], r.status, r.doc_id, r.fiscal_period, r.message[:120], flush=True)
        if r.doc_id:
            out = await index_pages_task({}, r.doc_id)
            print("INDEXED", r.doc_id, out, round(time.time()-t,1), flush=True)

asyncio.run(main(sys.argv[1:]))
