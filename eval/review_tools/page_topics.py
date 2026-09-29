"""For each page: sub-headings (lines starting with a letter/number enumerator) and key-term hits."""
import re
import sys

import pymupdf

pdf = pymupdf.open(sys.argv[1])
terms = sys.argv[3].split("|") if len(sys.argv) > 3 else []
a, _, b = sys.argv[2].partition("-")
for p in range(int(a), int(b or a) + 1):
    lines = [ln.strip() for ln in pdf[p - 1].get_text().splitlines() if ln.strip()]
    subs = [ln for ln in lines if re.match(r"^([a-z]\.|\([a-z]\)|[ivx]+\.|\d+\.)\s*\S", ln) and len(ln) < 90]
    low = " ".join(lines).lower()
    hits = [t for t in terms if t.lower() in low]
    print(f"p{p}: subs={subs[:6]} hits={hits}")
