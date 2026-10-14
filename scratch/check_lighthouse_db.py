import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT id, ticker, fiscal_period, doc_type, status, page_count, doc_hash, source_url
            FROM documents
            WHERE ticker IN ('BMRI', 'LSIP')
            ORDER BY ticker, fiscal_period;
        """))
        rows = [dict(r) for r in res.mappings().all()]
        print('Documents in DB:')
        for r in rows:
            print(r)
        
        # Check document_pages
        res2 = await conn.execute(text("""
            SELECT d.ticker, dp.doc_id, count(*) as pages, count(dp.embedding) as embeddings
            FROM document_pages dp
            JOIN documents d ON d.id = dp.doc_id
            WHERE d.ticker IN ('BMRI', 'LSIP')
            GROUP BY d.ticker, dp.doc_id;
        """))
        print('\nDocument pages count / embedding count:')
        for r in res2.mappings().all():
            print(dict(r))

        # Check facts
        res3 = await conn.execute(text("""
            SELECT ticker, fiscal_period, count(*) as fact_count, count(DISTINCT concept_id) as concept_count
            FROM financial_facts
            WHERE ticker IN ('BMRI', 'LSIP')
            GROUP BY ticker, fiscal_period;
        """))
        print('\nFinancial facts:')
        for r in res3.mappings().all():
            print(dict(r))

if __name__ == '__main__':
    asyncio.run(main())
