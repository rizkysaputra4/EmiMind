import psycopg

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/emimind")
cur = conn.cursor()
q = '"giro pada bank lain" OR "penempatan pada bank indonesia" OR "penempatan pada bank lain" OR kas OR "current accounts with other banks" OR "placements with bank indonesia" OR "placements with other banks" OR cash'

cur.execute("""
    SELECT page_index, ts_rank_cd(tsv, websearch_to_tsquery('simple', %s)) as r
    FROM document_pages
    WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2' AND page_index IN (183, 184, 185, 186, 187, 188, 189)
    ORDER BY page_index
""", (q,))
for r in cur.fetchall():
    print(f"P{r[0]}: ts_rank = {r[1]}")
