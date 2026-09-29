"""Checks extract_page_grids on real pages: bbox bounds, text-at-bbox agreement, units."""
import sys, time, re
import pymupdf
from services.extraction.pdf import parse_pdf
from services.extraction.tables import extract_page_grids

path = sys.argv[1]
pages_wanted = [int(x) for x in sys.argv[2].split(",")]
verbose = len(sys.argv) > 3
data = open(path, "rb").read()
doc = pymupdf.open(stream=data, filetype="pdf")
parsed = parse_pdf(data)
pages = [parsed[p - 1] for p in pages_wanted]
t0 = time.perf_counter()
grids = extract_page_grids(data, pages)
print(f"{len(grids)} grids in {time.perf_counter()-t0:.1f}s")

def norm(s): return re.sub(r"\s+", "", s)

tot = inb = match = nob = 0
for g in grids:
    pg = doc[g.page_index - 1]; W, H = pg.rect.width, pg.rect.height
    words = pg.get_text("words")
    n_val = sum(1 for c in g.cells if c.value is not None)
    n_mixed = sum(1 for c in g.cells if c.value_from_mixed_cell)
    n_note = sum(1 for c in g.cells if c.note_ref)
    print(f"p{g.page_index} t{g.table_index} {g.extraction_method} conf={g.confidence} unit={g.unit_hint} cells={len(g.cells)} values={n_val} mixed={n_mixed} note_refs={n_note} maxcellconf={max(c.confidence for c in g.cells)}")
    for c in g.cells:
        tot += 1
        if c.bbox is None:
            nob += 1; continue
        x0, y0, x1, y1 = c.bbox
        if 0 <= x0 <= x1 <= W + 0.5 and 0 <= y0 <= y1 <= H + 0.5:
            inb += 1
        # words whose centre lies in the bbox
        gw = [w[4] for w in words if x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1]
        got = " ".join(gw)
        want_words = c.text.split()
        ok = bool(want_words) and all(w in gw for w in want_words)
        match += bool(ok)
        if verbose and (c.value_from_mixed_cell or c.note_ref or not ok):
            print(f"   r{c.row}c{c.col} {'MIX' if c.value_from_mixed_cell else ''}{'NOTE' if c.note_ref else ''}{'' if ok else 'BBOX-MISMATCH'} text={c.text!r:.50} value={c.value} got={got[:40]!r}")
print(f"cells={tot} values={sum(1 for g in grids for c in g.cells if c.value is not None)} mixed={sum(1 for g in grids for c in g.cells if c.value_from_mixed_cell)} note_refs={sum(1 for g in grids for c in g.cells if c.note_ref)}")
print(f"cells={tot} bbox_null={nob} in_bounds={inb} text_at_bbox_match={match} ({match/max(1,tot-nob):.1%})")
