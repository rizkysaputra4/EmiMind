import psycopg
import re

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/emimind")
cur = conn.cursor()

def test_heading(doc_id, pat, is_core=False):
    cur.execute("SELECT page_index, page_text FROM document_pages WHERE doc_id = %s ORDER BY page_index", (doc_id,))
    matches = []
    for p_idx, txt in cur.fetchall():
        header = txt[:2500]
        if is_core:
            m = re.search(r"(?:^|\n)\s*" + pat, header, re.I)
        else:
            m = re.search(r"(?:^|\n)\s*(?:(?:catatan|note)\s*)?\d{1,3}\.\s*" + pat, header, re.I)
            if not m:
                # Also allow all-caps or title pattern without number if it matches note subheading
                m = re.search(r"(?:^|\n)\s*" + pat + r"(?:\s+[a-z\s]+)?(?:\n|$)", header, re.I)
        if m:
            is_cont = bool(re.search(pat + r"[^\n]*(?:\(lanjutan\)|\(continued\))", header, re.I))
            matches.append((p_idx, is_cont))
    return matches

print("BMRI DEBT (PINJAMAN YANG DITERIMA):", test_heading("a7ccfea3-30b5-4e2d-b357-fb5648386eb2", "PINJAMAN YANG DITERIMA")[:5])
print("BMRI CASH_BANKS (GIRO PADA BANK LAIN):", test_heading("a7ccfea3-30b5-4e2d-b357-fb5648386eb2", "GIRO PADA BANK LAIN")[:5])
print("LSIP BIOLOGICAL (ASET BIOLOGIS):", test_heading("82e20a07-232e-45bc-9a7b-3b160e8c2ece", "ASET BIOLOGIS")[:5])
print("LSIP REVENUE (PENDAPATAN DARI KONTRAK):", test_heading("82e20a07-232e-45bc-9a7b-3b160e8c2ece", "PENDAPATAN DARI KONTRAK")[:5])
