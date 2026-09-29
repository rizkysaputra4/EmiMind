import asyncio, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from wsB_harness import *  # noqa: F403
async def main():
    rep = await submit(payload(LSIP_Q3, "LSIP", "2025Q3", LSIP_Q3_GENUINE, omitted=LSIP_Q3_OMISSIONS))
    show("genuine+omissions", rep); print("facts", len(LSIP_Q3_GENUINE), "omissions", len(LSIP_Q3_OMISSIONS))
asyncio.run(main())
