"""Find the pages whose header area carries a given note heading."""
import re
import sys

import pymupdf

pdf = pymupdf.open(sys.argv[1])
for pat in sys.argv[2:]:
    r = re.compile(pat, re.I)
    hits = [i + 1 for i in range(pdf.page_count) if r.search(" ".join(pdf[i].get_text().split()[:90]))]
    print(f"{pat!r}: {len(hits)} pages {hits[:5]} ... {hits[-5:]}")
