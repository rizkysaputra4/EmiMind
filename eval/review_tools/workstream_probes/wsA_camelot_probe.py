import sys, camelot, pymupdf
path, page = sys.argv[1], int(sys.argv[2])
d = pymupdf.open(path); pg = d[page-1]
print("page rect", pg.rect, "rotation", pg.rotation, "mediabox", pg.mediabox)
for flavor in ("lattice", "stream"):
    ts = camelot.read_pdf(path, pages=str(page), flavor=flavor, suppress_stdout=True)
    print(flavor, len(ts))
    for t in ts:
        print(" shape", t.shape, "acc", round(t.accuracy,1), "ws", round(t.whitespace,1), "pdf_size", t.pdf_size, "bbox", t._bbox)
        H = pg.rect.height
        for r in range(min(len(t.cells), 12)):
            row = []
            for c in range(len(t.cells[r])):
                cell = t.cells[r][c]; txt = str(t.df.iloc[r, c]).strip()
                if not txt: continue
                box = pymupdf.Rect(cell.x1, H - cell.y2, cell.x2, H - cell.y1)
                got = pg.get_textbox(box).strip().replace("\n"," | ")
                row.append(f"[{c}] {txt[:40]!r} @({box.x0:.0f},{box.y0:.0f},{box.x1:.0f},{box.y1:.0f}) tb={got[:40]!r}")
            print("  r", r, " ; ".join(row))
