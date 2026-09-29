"""Independently verify committed facts against the real PDF pages."""
import re
import sys
from decimal import Decimal

import fitz
import psycopg

DOCS = {
    "a7ccfea3-30b5-4e2d-b357-fb5648386eb2": "incoming_reports/processed/BMRI_2025_AUDIT_RDF_LK PT Bank Mandiri-Desember 2025.pdf",
    "82e20a07-232e-45bc-9a7b-3b160e8c2ece": "incoming_reports/processed/LSIP_bilingual_31 des_2025_released.pdf",
}


def digits_in(text: str) -> set[str]:
    # every number token on the page, stripped to bare digits
    toks = re.findall(r"\(?-?\d[\d.,]*\)?", text)
    out = set()
    for t in toks:
        d = re.sub(r"[^\d]", "", t)
        if d:
            out.add(d.lstrip("0") or "0")
    return out


def candidates(v: Decimal, unit: str) -> list[str]:
    v = abs(v)
    c = []
    for scale in (Decimal(1), Decimal(1_000), Decimal(1_000_000), Decimal(1_000_000_000)):
        x = v / scale
        if x == x.to_integral_value():
            c.append(str(int(x)))
        else:
            # decimals e.g. 19.36 -> 1936
            s = format(x.normalize(), "f").replace(".", "")
            c.append(s.lstrip("0"))
    return c


with psycopg.connect("postgresql://emimind:emimind@localhost:5432/emimind") as con:
    for doc_id, path in DOCS.items():
        pdf = fitz.open(path)
        rows = con.execute(
            """select id, concept_id, value_numeric, unit, statement, period_type, source_page,
                      segment::text, concept_local, extraction_method, extraction_conf, source_bbox::text
               from financial_facts where source_doc_id=%s order by source_page, id""",
            (doc_id,),
        ).fetchall()
        ok = bad = 0
        print(f"\n=== {path} ({len(rows)} facts, {pdf.page_count} pages)")
        for (fid, cid, val, unit, st, pt, pg, seg, label, meth, conf, bbox) in rows:
            text = pdf[pg - 1].get_text() if 1 <= pg <= pdf.page_count else ""
            toks = digits_in(text)
            hit = any(c in toks for c in candidates(val, unit or ""))
            if hit:
                ok += 1
            else:
                bad += 1
            flag = "OK " if hit else "MISS"
            print(f"{flag} p{pg:<4} {st:<4} {pt:<12} {meth:<12} {conf} {cid:<45} {val} {unit} | {label[:40]} | {seg or ''}")
        print(f"found on cited page: {ok}/{ok + bad}")
