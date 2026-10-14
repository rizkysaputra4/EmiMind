import psycopg

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/emimind")
cur = conn.cursor()
cur.execute("""
    SELECT page_index, substring(page_text from 1 for 1000)
    FROM document_pages
    WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
      AND page_index BETWEEN 180 AND 195
    ORDER BY page_index
""")
for r in cur.fetchall():
    lines = [l.strip() for l in r[1].split("\n") if l.strip()]
    # look for lines containing Catatan or Note or 3. or 4. or 5.
    interesting = [l for l in lines[3:15] if any(k in l.upper() for k in ["CATATAN", "NOTE", "KAS", "GIRO", "BANK", "PENEMPATAN"])]
    print(f"=== Page {r[0]} ===")
    print(" / ".join(interesting[:3]))
