"""One-off cleanup of polluted/test data identified in docs/M9_REVIEW.md. Prints before/after counts."""
import psycopg

DOC_IDS = [
    "e35ffc42-ecb1-4801-bad8-630fd97ee684",  # fake BMRI 2024Q4 (unit-test data)
    "79655cd8-7525-4bb6-ad03-3168d708473d",  # review test: LSIP 2025Q3
    "48bc6360-3d09-46f6-b9e1-08e02a1a860c",  # review test: BMRI 2025Q1
    "304e9b72-8ed7-4659-8153-c18c869807c8",  # review test: AALI 2021Q1
    "a7cccdf8-058b-45e4-aa36-51a2767a77ae",  # review test: BMRI 2024Q2 cover letter
    "a7ccfea3-30b5-4e2d-b357-fb5648386eb2",  # old lighthouse BMRI 2025Q4 (to be re-extracted)
    "82e20a07-232e-45bc-9a7b-3b160e8c2ece",  # old lighthouse LSIP 2025Q4 (to be re-extracted)
]
PERIODS = [("BMRI", "2024Q4"), ("LSIP", "2025Q3"), ("BMRI", "2025Q1"), ("AALI", "2021Q1"),
           ("BMRI", "2024Q2"), ("BMRI", "2025Q4"), ("LSIP", "2025Q4")]

with psycopg.connect("postgresql://emimind:emimind@localhost:5432/emimind") as c:
    def counts(label):
        r = c.execute("select (select count(*) from documents), (select count(*) from financial_facts),"
                      " (select count(*) from narrative_chunks), (select count(*) from derived_metrics),"
                      " (select count(*) from document_pages)").fetchone()
        print(label, dict(zip(["documents", "facts", "narratives", "derived", "pages"], r)))
    counts("before")
    # guard: only the listed docs exist for these ticker-periods
    others = c.execute("select id, ticker, fiscal_period from documents where (ticker, fiscal_period) in (select * from unnest(%s::text[], %s::text[])) and not (id::text = any(%s))",
                       ([p[0] for p in PERIODS], [p[1] for p in PERIODS], DOC_IDS)).fetchall()
    assert not others, f"unexpected other documents share these periods: {others}"
    worker_hashes = [r[0] for r in c.execute("select doc_hash from documents where id::text = any(%s) or ticker like 'TEST\\_%%'", (DOC_IDS,)).fetchall()]
    c.execute("delete from documents where id::text = any(%s)", (DOC_IDS,))
    c.execute("delete from documents where ticker like 'TEST\\_%'")
    for t, p in PERIODS:
        c.execute("delete from derived_metrics where ticker=%s and fiscal_period=%s", (t, p))
        c.execute("delete from kg_nodes where ticker=%s and fiscal_period=%s", (t, p))
    c.execute("delete from worker_runs where doc_hash = any(%s)", (worker_hashes,))
    c.commit()
    counts("after ")
