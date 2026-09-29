"""False-positive probe: every current-period row of the primary statements as a fact.

Text mode: label = the Indonesian text of the line, value = first amount * page scale.
Cell mode: every table cell in the current-period column with a numeric value; label = the
row's first text cell. Only grounding categories are counted (the concepts are synthetic).
"""
import asyncio, sys, re, json
from collections import Counter
from decimal import Decimal
sys.path.insert(0, __import__("os").path.dirname(__file__))
from wsB_harness import *  # noqa: F403
from services.mcp.grounding import _parse_lines, page_header_years, detect_page_scale
from services.mcp.services.common import get_engine
from services.mcp.services.extraction import _load_page_evidence
from services.mcp.validator import resolve_payload_period_end
from services.mcp.grounding import _text_chunks, _row_label_texts, column_header_text, period_matches_header, _amount_columns

GROUNDING = ("GROUNDING", "ROW_LABEL", "PROVENANCE")

async def main(doc, ticker, fp, pages_spec, stmt_spec):
    pages = [int(x) for x in pages_spec.split(",")]
    stmts = dict(zip(pages, stmt_spec.split(",")))
    pe = resolve_payload_period_end(fp)
    eng = get_engine()
    async with eng.connect() as conn:
        le = await _load_page_evidence(conn, doc, set(pages), want_all_text=False)
    await eng.dispose()
    text_facts, cell_facts = [], []
    for p in pages:
        ev = le.evidence[p]
        scale = detect_page_scale(ev.page_text) or Decimal(1)
        years = page_header_years(ev.page_text, pe)
        st = stmts[p]; pt = "instant" if st == "BS" else "duration_ytd"
        for i, ln in enumerate(_parse_lines(ev.page_text)):
            am = ln.amounts
            if not ln.chunks or not years or len(am) != len(years) or am[0].is_dash:
                continue
            label = ln.chunks[0]
            val = abs(am[1].values[0]) * scale
            if am[1].is_dash or abs(am[1].values[0]) == abs(am[0].values[0]): continue
            text_facts.append(fact(f"idx:Probe{p}L{i}", val, p, st=st, label=label, pt=pt))
        for t in ev.tables:
            amount_cols = _amount_columns(t)
            for c in t.cells:
                if c.value is None or c.value == 0:
                    continue
                hdr = column_header_text(t, c.row, c.col)
                cur = period_matches_header(hdr, pe) if hdr else None
                if cur is None and years and c.col in amount_cols and len(amount_cols) == len(years):
                    cur = years[amount_cols.index(c.col)] == pe.year
                if cur is not False:
                    continue
                lbls = _row_label_texts(t, c.row, exclude_col=c.col)
                if not lbls:
                    continue
                cell_facts.append(fact(f"idx:ProbeT{p}_{t.table_index}_{c.row}_{c.col}", Decimal(str(abs(c.value))) * scale, p, st=st,
                                       label=lbls[0], pt=pt, cell=(t.table_index, c.row, c.col)))
    for name, facts in (("text", text_facts), ("cell", cell_facts)):
        rep = await submit(payload(doc, ticker, fp, facts))
        bad = {}
        for i in rep.issues:
            if i.category.startswith(GROUNDING) and i.severity.value == "ERROR":
                bad.setdefault(i.concept_id, []).append(i)
        print(f"{ticker} {fp} {name}: {len(facts)} genuine rows, {len(bad)} CAUGHT "
              f"({100*len(bad)/max(1,len(facts)):.1f}%) {Counter(x[0].category for x in bad.values())}")
        for cid, iss in list(bad.items())[:12]:
            f = next(f for f in facts if f['concept_id'] == cid)
            print(f"    {cid} label={f['source_label_original']!r} val={f['value_numeric']} :: {iss[0].category}: {iss[0].feedback_message[:200]}")
asyncio.run(main(*sys.argv[1:]))
