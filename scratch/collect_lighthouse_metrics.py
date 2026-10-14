import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        for ticker, doc_id in [("BMRI", "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"), ("LSIP", "82e20a07-232e-45bc-9a7b-3b160e8c2ece")]:
            print(f"\n================ {ticker} ================")
            doc_res = await conn.execute(
                text("SELECT id, ticker, fiscal_period, period_end, page_count FROM documents WHERE id = :id"),
                {"id": doc_id}
            )
            print("Doc:", dict(doc_res.mappings().first() or {}))

            facts_res = await conn.execute(
                text("SELECT count(*) as total, count(DISTINCT concept_id) as distinct_concepts, "
                     "count(CASE WHEN segment IS NOT NULL THEN 1 END) as segmented, "
                     "count(CASE WHEN extraction_method = 'table_parser' THEN 1 END) as table_parser, "
                     "count(CASE WHEN extraction_method = 'llm_extract' THEN 1 END) as llm_extract "
                     "FROM financial_facts WHERE source_doc_id = :id"),
                {"id": doc_id}
            )
            print("Facts:", dict(facts_res.mappings().first() or {}))

            narratives_res = await conn.execute(
                text("SELECT count(*) as total FROM narrative_chunks WHERE source_doc_id = :id"),
                {"id": doc_id}
            )
            print("Narratives:", dict(narratives_res.mappings().first() or {}))

            log_res = await conn.execute(
                text("SELECT action, source, reason, metadata FROM document_processing_log WHERE doc_id = :id ORDER BY id"),
                {"id": doc_id}
            )
            print("Logs:")
            for l in log_res.mappings():
                print(" ", dict(l))

asyncio.run(main())
