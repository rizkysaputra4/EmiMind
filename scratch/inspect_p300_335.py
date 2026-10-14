import psycopg

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/emimind")
cur = conn.cursor()
cur.execute("""
    SELECT page_index, substring(page_text from 1 for 1000)
    FROM document_pages
    WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
      AND page_index BETWEEN 300 AND 335
    ORDER BY page_index
""")
for r in cur.fetchall():
    lines = [l.strip() for l in r[1].split("\n") if l.strip()]
    interesting = [l for l in lines[3:15] if any(k in l.upper() for k in ["PINJAMAN", "SURAT", "EFEK", "UTANG", "BORROWING", "35.", "36.", "37.", "38.", "39."])]
    print(f"P{r[0]}:", " // ".join(interesting[:2]))
