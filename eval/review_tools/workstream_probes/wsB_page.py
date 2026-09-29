import sys, json, psycopg
dsn = "postgresql://emimind:emimind@localhost:5432/emimind"
doc, pages = sys.argv[1], [int(x) for x in sys.argv[2].split(",")]
show_tables = len(sys.argv) > 3
with psycopg.connect(dsn) as c:
    cur = c.cursor()
    for p in pages:
        cur.execute("SELECT text_source, page_text FROM document_pages WHERE doc_id=%s AND page_index=%s", (doc, p))
        r = cur.fetchone()
        print(f"===== PAGE {p} [{r[0]}] =====")
        for i, ln in enumerate(r[1].splitlines()): print(f"{i:3d}| {ln}")
        if show_tables:
            cur.execute("SELECT table_index, extraction_method, confidence, unit_hint, cells FROM document_page_tables WHERE doc_id=%s AND page_index=%s ORDER BY table_index", (doc, p))
            for ti, m, conf, uh, cells in cur.fetchall():
                print(f"--- table {ti} {m} conf={conf} unit={uh} ncells={len(cells)}")
                rows = {}
                for ce in cells: rows.setdefault(ce["row"], []).append(ce)
                for rr in sorted(rows)[:60]:
                    print(f"  r{rr}: " + " | ".join(f"c{ce['col']}={ce['text'][:40]!r}->{ce.get('value')}" for ce in sorted(rows[rr], key=lambda x: x['col'])))
