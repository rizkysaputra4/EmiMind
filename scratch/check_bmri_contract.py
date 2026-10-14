import asyncio
from services.mcp.services.common import get_engine
from services.mcp.services.routing import get_extraction_contract

async def main():
    engine = get_engine()
    doc_id = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"
    contract = await get_extraction_contract(doc_id, engine=engine)
    print("Ticker:", contract.ticker)
    print("Sector:", contract.sector)
    print("Fiscal Period:", contract.fiscal_period)
    print("Required facts count:", len(contract.required_facts))
    print("Required concepts:")
    for f in contract.required_facts:
        print(f"  {f.concept_id}: req={f.required}, mode={f.extraction_mode}, imp={f.importance}, stmt={f.statement_type}")
    print("\nGranular note modules:")
    for m in contract.granular_note_modules:
        print(f"  {m.name}: {m.typical_note_title} -> {m.target_concepts}")
    print("\nNarrative topics:")
    for n in contract.narrative_topics:
        print(f"  {n.topic} ({n.expected_section})")

asyncio.run(main())
