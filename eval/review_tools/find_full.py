"""Find pages whose full text matches each regex (multiline-joined)."""
import re
import sys

import pymupdf

pdf = pymupdf.open(sys.argv[1])
texts = [" ".join(pdf[i].get_text().split()) for i in range(pdf.page_count)]
for pat in sys.argv[2:]:
    r = re.compile(pat, re.I)
    hits = [i + 1 for i, t in enumerate(texts) if r.search(t)]
    print(f"{pat!r}: {hits[:40]}")
