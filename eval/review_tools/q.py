import sys

import psycopg

sql = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
with psycopg.connect("postgresql://emimind:emimind@localhost:5432/emimind", connect_timeout=10) as c:
    for stmt in [s for s in sql.split(";;") if s.strip()]:
        cur = c.execute(stmt)
        if cur.description:
            cols = [d.name for d in cur.description]
            print(" | ".join(cols))
            for r in cur.fetchall():
                print(" | ".join(str(x) for x in r))
            print("--")
