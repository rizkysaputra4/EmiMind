import asyncio
import re
from pathlib import Path
import yaml
from sqlalchemy import text
from services.mcp.contracts import get_route_query
from services.mcp.server import get_engine
from services.retrieval.page_router import merge_spans

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def test_is_continuation(prev_text: str, next_text: str) -> bool:
    next_header = "\n".join(next_text.splitlines()[:25]).lower()
    prev_header = "\n".join(prev_text.splitlines()[:25]).lower()

    has_cont_marker = "(lanjutan)" in next_header or "(continued)" in next_header

    # All notes introduced on prev page
    prev_notes = re.findall(r"(?:catatan|note|^|\n)\s*(\d{1,3})\.\s*[A-Za-z]", prev_text)
    next_notes = re.findall(r"(?:catatan|note|^|\n)\s*(\d{1,3})\.\s*[A-Za-z]", next_header)

    if has_cont_marker:
        if prev_notes and next_notes:
            return bool(prev_notes[-1] == next_notes[0])
        return True

    if prev_notes and next_notes:
        if prev_notes[-1] == next_notes[0] and len(next_notes) == 1:
            return True

    return False

async def route_test(conn, doc_id, rq, top_k=3):
    pages_res = await conn.execute(
        text("SELECT page_index, page_text, embedding IS NOT NULL as has_emb FROM document_pages WHERE doc_id = :doc_id ORDER BY page_index ASC"),
        {"doc_id": doc_id},
    )
    pages_rows = pages_res.mappings().all()
    total_pages = len(pages_rows)
    page_text_map = {int(r["page_index"]): str(r["page_text"]) for r in pages_rows}

    all_terms = list(rq.terms_id) + list(rq.terms_en)
    quoted_terms = [f'"{t}"' if " " in t.strip() else t.strip() for t in all_terms if t.strip()]
    web_query = " OR ".join(quoted_terms)

    fts_res = await conn.execute(
        text("""
            SELECT page_index, ts_rank_cd(tsv, websearch_to_tsquery('simple', :q)) AS rank
            FROM document_pages
            WHERE doc_id = :doc_id AND tsv @@ websearch_to_tsquery('simple', :q)
            ORDER BY rank DESC LIMIT 40
        """),
        {"doc_id": doc_id, "q": web_query},
    )
    fts_rows = [dict(r) for r in fts_res.mappings().all()]

    is_core_stmt = any(
        re.search(r"posisi\s+keuangan|laba\s+rugi|arus\s+kas|financial\s+position|profit\s+or\s+loss|cash\s+flows", pat, re.I)
        for pat in (rq.anchor_patterns or [])
    )

    excluded_pages = set()
    for p_idx, p_text in page_text_map.items():
        header = p_text[:1000]
        if re.search(r"daftar\s+isi|table\s+of\s+contents|laporan\s+atas\s+reviu|report\s+on\s+review|auditor\s+independen|independent\s+auditor", header, re.I):
            excluded_pages.add(p_idx)
            continue
        if not is_core_stmt and re.search(
            r"laporan\s+posisi\s+keuangan|statement\s+of\s+financial\s+position|laporan\s+laba\s+rugi|statement\s+of\s+profit\s+or\s+loss|laporan\s+arus\s+kas|statement\s+of\s+cash\s+flows|laporan\s+perubahan\s+ekuitas|statement\s+of\s+changes\s+in\s+equity|kebijakan\s+akuntansi|accounting\s+polic",
            header,
            re.I,
        ):
            excluded_pages.add(p_idx)

    fts_rows = [r for r in fts_rows if int(r["page_index"]) not in excluded_pages]

    primary_anchors = []
    if rq.anchor_patterns:
        for p_idx, p_text in page_text_map.items():
            if p_idx in excluded_pages:
                continue
            header = p_text[:2000]
            if any(re.search(pat, header, re.I) for pat in rq.anchor_patterns):
                if not re.search(r"\(lanjutan\)|\(continued\)", header, re.I):
                    primary_anchors.append(p_idx)

    # Boost primary anchors to the top of FTS list
    fts_ranked_pages = primary_anchors + [int(r["page_index"]) for r in fts_rows if int(r["page_index"]) not in set(primary_anchors)]

    # Take top seeds
    top_seeds = [(p, 1.0 / (60 + i)) for i, p in enumerate(fts_ranked_pages[:top_k])]

    raw_spans = []
    for seed_page, seed_score in top_seeds:
        start = max(1, seed_page - 1)
        end = min(total_pages, seed_page + 1)

        # Forward continuation
        curr_end = end
        while curr_end < total_pages and (curr_end + 1 - start + 1) <= rq.max_pages:
            prev_p = page_text_map.get(curr_end, "")
            next_p = page_text_map.get(curr_end + 1, "")
            if test_is_continuation(prev_p, next_p):
                curr_end += 1
                end = curr_end
            else:
                break

        # Backward continuation
        curr_start = start
        while curr_start > 1 and (end - (curr_start - 1) + 1) <= rq.max_pages:
            prev_p = page_text_map.get(curr_start - 1, "")
            curr_p = page_text_map.get(curr_start, "")
            if test_is_continuation(prev_p, curr_p):
                curr_start -= 1
                start = curr_start
            else:
                break

        raw_spans.append((start, end, seed_score, seed_page))

    merged = merge_spans([(s[0], s[1]) for s in raw_spans])
    all_returned = sorted({p for m in merged for p in range(m[0], m[1] + 1)})
    return all_returned

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        # Load queries
        with open("db/seeds/page_router_queries.yaml") as f:
            q_dict = yaml.safe_load(f)

        # Apply bank overrides dynamically for this test
        for mod in ["REVENUE_BREAKDOWN", "CUSTOMER_CONCENTRATION"]:
            q_dict[mod]["BANK"] = q_dict["REVENUE_CUSTOMERS"]["BANK"]
        for mod in ["COGS_COMPONENTS"]:
            q_dict[mod]["BANK"] = q_dict["COGS_BREAKDOWN"]["BANK"]
        for mod in ["DEBT_BY_LENDER"]:
            q_dict[mod]["BANK"] = q_dict["DEBT_FACILITIES"]["BANK"]
        q_dict["BALANCE_SHEET"]["BANK"] = dict(q_dict["BALANCE_SHEET"]["ALL"])
        q_dict["BALANCE_SHEET"]["BANK"]["max_pages"] = 8

        from services.mcp.types import RouteQuery

        # Test BMRI
        with open("eval/router_gold/BMRI_2025Q4.yaml") as f:
            bmri_gold = yaml.safe_load(f)["modules"]

        doc_id = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"
        print("=== BMRI RESULTS ===")
        total_hits = 0
        total_gold = 0
        for mod, gold in bmri_gold.items():
            conf = q_dict[mod].get("BANK", q_dict[mod].get("ALL"))
            rq = RouteQuery(**conf)
            ret = await route_test(conn, doc_id, rq)
            hits = sorted(set(gold) & set(ret))
            rec = len(hits) / len(gold)
            total_hits += len(hits)
            total_gold += len(gold)
            print(f"{mod:<22} Gold: {gold} Hits: {len(hits)}/{len(gold)} Recall: {rec*100:.1f}%")

        # Test LSIP
        with open("eval/router_gold/LSIP_2025Q4.yaml") as f:
            lsip_gold = yaml.safe_load(f)["modules"]

        doc_id_lsip = "82e20a07-232e-45bc-9a7b-3b160e8c2ece"
        print("\n=== LSIP RESULTS ===")
        for mod, gold in lsip_gold.items():
            conf = q_dict[mod].get("PLANTATION", q_dict[mod].get("ALL"))
            rq = RouteQuery(**conf)
            ret = await route_test(conn, doc_id_lsip, rq)
            hits = sorted(set(gold) & set(ret))
            rec = len(hits) / len(gold)
            print(f"{mod:<22} Gold: {gold} Hits: {len(hits)}/{len(gold)} Recall: {rec*100:.1f}%")

asyncio.run(main())
