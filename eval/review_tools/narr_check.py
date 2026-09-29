import re, pymupdf, psycopg
DOCS = {"a7ccfea3-30b5-4e2d-b357-fb5648386eb2": "incoming_reports/processed/BMRI_2025_AUDIT_RDF_LK PT Bank Mandiri-Desember 2025.pdf",
        "82e20a07-232e-45bc-9a7b-3b160e8c2ece": "incoming_reports/processed/LSIP_bilingual_31 des_2025_released.pdf"}
norm = lambda s: " ".join(s.lower().split())
with psycopg.connect("postgresql://emimind:emimind@localhost:5432/emimind") as c:
    for d, path in DOCS.items():
        pdf = pymupdf.open(path)
        rows = c.execute("select distinct source_page, text_original from narrative_chunks where source_doc_id=%s", (d,)).fetchall()
        for pg, t in rows:
            page = norm(pdf[pg-1].get_text())
            words = re.findall(r"[a-z]{5,}", norm(t))
            # longest run of 6 consecutive words found verbatim on the page
            best = 0
            for i in range(len(words)):
                for j in range(i+1, len(words)+1):
                    if " ".join(words[i:j]) in page: best = max(best, j-i)
                    else: break
            nums = re.findall(r"\d+[.,]\d+%?|\d+%", t)
            nums_on_page = [n for n in nums if n in page]
            print(f"p{pg}: longest verbatim word-run={best}/{len(words)} numbers on page={nums_on_page}/{nums} :: {t[:90]}")
