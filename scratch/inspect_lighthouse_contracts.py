import asyncio
from services.mcp.services.common import get_engine
from services.mcp.services.routing import get_extraction_contract

async def main():
    engine = get_engine()
    bmri_c = await get_extraction_contract('a7ccfea3-30b5-4e2d-b357-fb5648386eb2', engine=engine)
    print('BMRI sector:', bmri_c.sector)
    print('BMRI scaling_rules:', bmri_c.scaling_rules)
    print('BMRI required facts count:', len(bmri_c.required_facts))
    print('BMRI required facts concepts:', [f.concept_id for f in bmri_c.required_facts])
    print('BMRI granular modules:', [m.name for m in bmri_c.granular_note_modules])

    lsip_c = await get_extraction_contract('82e20a07-232e-45bc-9a7b-3b160e8c2ece', engine=engine)
    print('\nLSIP sector:', lsip_c.sector)
    print('LSIP scaling_rules:', lsip_c.scaling_rules)
    print('LSIP required facts count:', len(lsip_c.required_facts))
    print('LSIP required facts concepts:', [f.concept_id for f in lsip_c.required_facts])
    print('LSIP granular modules:', [m.name for m in lsip_c.granular_note_modules])

if __name__ == '__main__':
    asyncio.run(main())
