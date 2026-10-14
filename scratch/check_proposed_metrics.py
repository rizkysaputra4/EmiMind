import asyncio
from sqlalchemy import text
from services.mcp.services.common import get_engine

async def main():
    async with get_engine().connect() as conn:
        res = await conn.execute(text("SELECT metric_id, name_en FROM metric_definitions ORDER BY metric_id"))
        all_metrics = {r[0]: r[1] for r in res.fetchall()}
        print(f"Total metrics in DB: {len(all_metrics)}")
        test_ids = [
            "idx:MarketableSecurities", "idx:GovernmentBonds", "idx:AcceptanceReceivables",
            "idx:PrepaidExpenses", "idx:PrepaidTaxes", "ifrs:DeferredTaxAssets",
            "idx:DerivativeFinancialLiabilities", "idx:AcceptancePayables", "idx:OtherLiabilities",
            "idx:ShareCapital", "idx:RetainedEarnings", "idx:SalariesAndEmployeeBenefitsExpense",
            "idx:GeneralAdministrativeExpense", "idx:AllowanceForLoanLosses",
            "idx:SecuritiesSoldUnderRepurchaseAgreements", "idx:SubordinatedDebt",
            "idx:CurrentAccountsWithCentralBank", "idx:CurrentAccountsWithOtherBanks", "idx:PlacementsWithBanks"
        ]
        for tid in test_ids:
            print(f"  {tid}: {'EXISTS' if tid in all_metrics else 'MISSING'}")

asyncio.run(main())
