import psycopg, re

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/emimind")
cur = conn.cursor()

def find_anchors(doc_id, patterns, is_core):
    cur.execute("SELECT page_index, page_text FROM document_pages WHERE doc_id = %s ORDER BY page_index", (doc_id,))
    prim = []
    cont = []
    for p_idx, txt in cur.fetchall():
        # Exclude TOC/auditor
        header_1k = txt[:1000]
        if re.search(r"daftar\s+isi|table\s+of\s+contents|laporan\s+atas\s+reviu|report\s+on\s+review|auditor\s+independen|independent\s+auditor", header_1k, re.I):
            continue
        if not is_core and re.search(
            r"laporan\s+posisi\s+keuangan|statement\s+of\s+financial\s+position|laporan\s+laba\s+rugi|statement\s+of\s+profit\s+or\s+loss|laporan\s+arus\s+kas|statement\s+of\s+cash\s+flows|laporan\s+perubahan\s+ekuitas|statement\s+of\s+changes\s+in\s+equity|kebijakan\s+akuntansi|accounting\s+polic",
            header_1k,
            re.I,
        ):
            continue

        for pat in patterns:
            # In first 1000 chars (standard header): match pattern
            m = re.search(pat, header_1k, re.I)
            # If not in first 1000 chars, allow formal note start with note number \d+\. in first 2500 chars
            if not m and not is_core:
                m = re.search(r"(?:^|\n)\s*(?:catatan|note\s*)?\d{1,3}\.\s*" + pat, txt[:2500], re.I)

            if m:
                # Check continuation
                matched_line = m.group(0)
                # check if (lanjutan) or (continued) follows on the same line or in header
                is_cont = bool(re.search(pat + r"[^\n]*(?:\(lanjutan\)|\(continued\))", txt[:2500], re.I)) or bool(re.search(r"\(lanjutan\)|\(continued\)", header_1k, re.I))
                if is_cont:
                    cont.append(p_idx)
                else:
                    prim.append(p_idx)
                break
    return list(dict.fromkeys(prim)), list(dict.fromkeys(cont))

print("BMRI DEBT prim:", find_anchors("a7ccfea3-30b5-4e2d-b357-fb5648386eb2", ["PINJAMAN YANG DITERIMA", "SURAT BERHARGA YANG DITERBITKAN", "BORROWINGS"], False)[0])
print("BMRI CASH_BANKS prim:", find_anchors("a7ccfea3-30b5-4e2d-b357-fb5648386eb2", ["GIRO PADA BANK LAIN", "PENEMPATAN PADA BANK", "CURRENT ACCOUNTS WITH OTHER BANKS"], False)[0])
print("LSIP BIOLOGICAL prim:", find_anchors("82e20a07-232e-45bc-9a7b-3b160e8c2ece", ["ASET BIOLOGIS", "BIOLOGICAL ASSETS"], False)[0])
print("LSIP REVENUE prim:", find_anchors("82e20a07-232e-45bc-9a7b-3b160e8c2ece", ["PENDAPATAN", "REVENUE", "PENJUALAN", "PELANGGAN"], False)[0])
