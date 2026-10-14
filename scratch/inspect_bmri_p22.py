import psycopg

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/emimind")
cur = conn.cursor()
cur.execute("""
    SELECT page_index, substring(page_text from 1 for 400)
    FROM document_pages
    WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
      AND page_index IN (21, 22, 23)
    ORDER BY page_index
""")
for r in cur.fetchall():
    print(f"=== Page {r[0]} ===")
    print(r[1].strip()[:300])
