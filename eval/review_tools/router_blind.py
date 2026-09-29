"""Blind router test: my own page labels (from headings) vs get_routed_pages output."""
import asyncio
import sys

from services.mcp.services.routing import get_routed_pages

import json

DOC = sys.argv[1]
GOLD = {k: set(v) for k, v in json.loads(sys.argv[2]).items()} if len(sys.argv) > 2 else {
    "BALANCE_SHEET": {4, 5},
    "INCOME_STATEMENT": {6, 7},
    "CASH_FLOW": {9},
    "CASH_BANKS": {54, 55},
    "BIOLOGICAL_ASSETS_DETAIL": {59, 60},
    "PLANTATION_AREA": {62, 73, 74},
    "REVENUE_BREAKDOWN": {93, 94},
    "CUSTOMER_CONCENTRATION": {94, 95},
    "COGS_BREAKDOWN": {94, 95},
}


async def main() -> None:
    tot_hit = tot_gold = tot_ret = 0
    for mod, gold in GOLD.items():
        try:
            r = await get_routed_pages(DOC, mod, 3)
        except Exception as exc:
            print(f"{mod:<26} ERROR {type(exc).__name__}: {str(exc)[:150]}")
            continue
        pages = [p.page_index for p in r.pages]
        hit = gold & set(pages)
        tot_hit += len(hit)
        tot_gold += len(gold)
        tot_ret += len(pages)
        print(f"{mod:<26} recall={len(hit)}/{len(gold)} returned={len(pages):>2} {sorted(pages)} gold={sorted(gold)}")
    print(f"TOTAL recall={tot_hit}/{tot_gold} = {tot_hit / max(tot_gold, 1):.0%}, pages returned={tot_ret}")


asyncio.run(main())
