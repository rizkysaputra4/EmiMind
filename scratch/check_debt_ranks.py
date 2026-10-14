import psycopg
from services.mcp.contracts import get_route_query

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/emimind")
cur = conn.cursor()
rq = get_route_query("DEBT_FACILITIES", "BANK")
terms = rq.terms_id + rq.terms_en
q = " OR ".join(f'"{t}"' for t in terms)
cur.execute("""
    SELECT page_index, ts_rank_cd(tsv, websearch_to_tsquery('simple', %s)) as r
    FROM document_pages
    WHERE doc_id = 'a7ccfea3-30b5-4e2d-b357-fb5648386eb2'
      AND page_index BETWEEN 305 AND 332
      AND tsv @@ websearch_to_tsquery('simple', %s)
    ORDER BY r DESC LIMIT 15
""", (q, q))
for r in cur.fetchall():
    print(f"P{r[0]}: {r[1]}")
