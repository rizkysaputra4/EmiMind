import asyncio
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from sqlalchemy import text
import re

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        rq = get_route_query('BALANCE_SHEET', 'BANK')
        pages_res = await conn.execute(text("SELECT page_index, page_text FROM document_pages WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' ORDER BY page_index ASC"))
        pages_rows = pages_res.mappings().all()
        page_text_map = {int(r["page_index"]): str(r["page_text"]) for r in pages_rows}

        is_core_stmt = any(
            re.search(r"posisi\s+keuangan|laba\s+rugi|arus\s+kas|financial\s+position|profit\s+or\s+loss|cash\s+flows", pat, re.I)
            for pat in rq.anchor_patterns
        )

        excluded_pages = set()
        for p_idx, p_text in page_text_map.items():
            header = p_text[:1000]
            if re.search(r"daftar\s+isi|table\s+of\s+contents|laporan\s+atas\s+reviu|report\s+on\s+review|auditor\s+independen|independent\s+auditor", header, re.I):
                excluded_pages.add(p_idx)

        prim = []
        cont = []
        for p_idx, p_text in page_text_map.items():
            if p_idx in excluded_pages:
                continue
            header = p_text[:1000]
            if any(re.search(pat, header, re.I) for pat in rq.anchor_patterns):
                if re.search(r"\(lanjutan\)|\(continued\)", header, re.I):
                    cont.append(p_idx)
                else:
                    prim.append(p_idx)

        print("Excluded count:", len(excluded_pages))
        print("Page 4 excluded?", 4 in excluded_pages)
        print("Primary anchors:", prim)
        print("Cont anchors:", cont)

asyncio.run(main())
