"""Print a compact header (first meaningful lines) for each requested page."""
import sys

import pymupdf

path = sys.argv[1]
pdf = pymupdf.open(path)
skip = ("PT BANK MANDIRI", "DAN ENTITAS", "AND ITS", "CATATAN ATAS", "NOTES TO THE", "Untuk Tahun", "For the Year", "(Disajikan", "(Expressed", "kecuali", "unless", "Tanggal 31", "31 December", "pada Tanggal", "PT PP LONDON", "PT PERUSAHAAN")
for spec in sys.argv[2:]:
    a, _, b = spec.partition("-")
    for p in range(int(a), int(b or a) + 1):
        lines = [ln.strip() for ln in pdf[p - 1].get_text().splitlines() if ln.strip()]
        keep = [ln for ln in lines if not any(ln.startswith(s) for s in skip)]
        print(f"p{p}: " + " | ".join(keep[:14])[:330])
