import asyncio
import yaml
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.mcp.types import RouteQuery
from sqlalchemy import text
import re

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        with open("db/seeds/page_router_queries.yaml") as f:
            q_dict = yaml.safe_load(f)
        conf = q_dict["DEBT_FACILITIES"]["BANK"]
        rq = RouteQuery(**conf)

        doc_id = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"
        pages_res = await conn.execute(text("SELECT page_index, page_text FROM document_pages WHERE doc_id = :doc_id ORDER BY page_index ASC"), {"doc_id": doc_id})
        page_text_map = {int(r["page_index"]): str(r["page_text"]) for r in pages_res.mappings().all()}

        print("Anchors in conf:", rq.anchor_patterns)
        
        matches = []
        for p_idx, p_text in page_text_map.items():
            header = p_text[:2000]
            for pat in rq.anchor_patterns:
                if re.search(pat, header, re.I):
                    is_cont = bool(re.search(r"\(lanjutan\)|\(continued\)", header, re.I))
                    matches.append((p_idx, pat, is_cont))
        print("Matches in first 2000 chars:", matches[:10])

asyncio.run(main())
