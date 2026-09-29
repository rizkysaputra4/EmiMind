import sys, psycopg
dsn = "postgresql://emimind:emimind@localhost:5432/emimind"
with psycopg.connect(dsn) as c:
    c.read_only = True
    cur = c.cursor()
    for s in sys.argv[1:]:
        try:
            cur.execute(s); print(">>", s[:100])
            for r in cur.fetchall()[:200]: print("  ", r)
        except Exception as e:
            print("ERR", s[:60], e); c.rollback()
