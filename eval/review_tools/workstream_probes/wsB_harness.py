"""wsB verification harness: submit payloads against real indexed docs (no DB writes)."""
import asyncio, json
from services.mcp.services.common import get_engine
from services.mcp.services.extraction import submit_draft_extraction

LSIP_Q3 = "0d5a1599-cb28-4f0b-9212-c6d447728f25"
LSIP_Q4 = "9cbf5811-986f-4c8f-882f-6c0cf67a504a"
BMRI_Q4 = "9a0154b0-9d27-42d4-b45a-f2ee9e75a187"
M = 1_000_000

async def _noop(*a, **k):
    return None

def fact(cid, val, page, st="BS", cell=None, label=None, seg=None, pt=None, unit="IDR"):
    f = {"concept_id": cid, "value_numeric": str(val), "statement": st, "source_page": page,
         "source_label_original": label if label is not None else cid, "unit": unit}
    if cell:
        f["cell_ref"] = {"table_index": cell[0], "row": cell[1], "col": cell[2]}
    if seg:
        f["segment"] = seg
    if pt:
        f["period_type"] = pt
    return f

def omit(mid, pages, expl="The interim consolidated financial statements do not disclose this operational metric anywhere."):
    return {"metric_id": mid, "reason": "NOT_DISCLOSED_IN_REPORT", "explanation": expl, "search_pages_checked": pages}

def payload(doc, ticker, fp, facts, narratives=None, omitted=None):
    return {"doc_id": doc, "ticker": ticker, "fiscal_period": fp, "facts": facts,
            "narratives": narratives or [], "omitted_kpis": omitted or []}

async def submit(p):
    eng = get_engine()
    rep = await submit_draft_extraction(json.dumps(p), engine=eng, log_event_fn=_noop)
    await eng.dispose()
    return rep

def show(name, rep, only_errors=False):
    print(f"== {name}: status={rep.status} errors={rep.errors_count} warnings={rep.warnings_count}")
    for i in rep.issues:
        sev = i.severity.value if hasattr(i.severity, "value") else i.severity
        if only_errors and sev != "ERROR":
            continue
        print(f"   {sev:<7} {i.category:<34} {i.concept_id or '':<45} {i.feedback_message[:230]}")

LSIP_Q3_GENUINE = [
    fact("ifrs:Assets", 14_784_538 * M, 4, label="Total Aset"),
    fact("ifrs:CurrentAssets", 8_017_709 * M, 4, label="Total Aset Lancar"),
    fact("ifrs:NonCurrentAssets", 6_766_829 * M, 4, label="Total Aset Tidak Lancar"),
    fact("ifrs:Inventories", 548_271 * M, 4, cell=(2, 12, 1), label="Persediaan"),
    fact("ifrs:PropertyPlantAndEquipment", 5_052_444 * M, 4, label="Aset tetap"),
    fact("ifrs:CurrentLiabilities", 828_016 * M, 5, label="Total Liabilitas Jangka Pendek"),
    fact("ifrs:NonCurrentLiabilities", 597_950 * M, 5, label="Total Liabilitas Jangka Panjang"),
    fact("ifrs:Liabilities", 1_425_966 * M, 5, label="Total Liabilitas"),
    fact("ifrs:Equity", 13_358_572 * M, 5, cell=(1, 7, 1), label="Total Ekuitas"),
    fact("ifrs:EquityAttributableToOwnersOfParent", 13_361_953 * M, 5, label="Ekuitas yang Dapat Diatribusikan kepada Pemilik Entitas Induk"),
    fact("ifrs:Revenue", 3_956_904 * M, 6, st="IS", cell=(0, 6, 1), label="Pendapatan dari kontrak dengan pelanggan"),
    fact("ifrs:CostOfSales", 2_483_760 * M, 6, st="IS", cell=(0, 7, 1), label="Beban pokok penjualan"),
    fact("ifrs:OperatingProfit", 1_290_253 * M, 6, st="IS", cell=(0, 15, 1), label="Laba usaha"),
    fact("ifrs:FinanceCosts", 267 * M, 6, st="IS", cell=(0, 17, 1), label="Beban keuangan"),
    fact("ifrs:ProfitBeforeTax", 1_489_836 * M, 6, st="IS", cell=(0, 19, 1), label="Laba sebelum pajak penghasilan"),
    fact("ifrs:ProfitLoss", 1_246_424 * M, 6, st="IS", cell=(0, 21, 1), label="Laba periode berjalan"),
    fact("idx:SellingAndMarketingExpense", 55_151 * M, 6, st="IS", cell=(0, 11, 1), label="Beban penjualan dan distribusi"),
    fact("ifrs:CashFlowsFromUsedInOperatingActivities", 2_152_702 * M, 9, st="CF", cell=(0, 18, 1), label="Kas Neto yang Diperoleh dari Aktivitas Operasi"),
    fact("idx:Capex", 254_623 * M, 9, st="CF", cell=(0, 27, 1), label="Penambahan aset tetap"),
    fact("ifrs:CashAndCashEquivalents", 6_901_140 * M, 9, st="CF", cell=(0, 44, 1), label="Kas dan Setara Kas Akhir Periode"),
]

LSIP_Q3_GENUINE.append(fact("ifrs:ProfitLossAttributableToOwnersOfParent", 1_247_373 * M, 7, st="IS", cell=(1, 3, 1),
                            label="Laba periode berjalan yang dapat diatribusikan kepada Pemilik entitas induk"))
ALL_PAGES_Q3 = list(range(1, 114))
LSIP_Q3_OMISSIONS = [omit(m, ALL_PAGES_Q3) for m in (
    "idx:CPOAveragePriceASP", "idx:CPOCashCostPerKg", "idx:CPOProductionVolume", "idx:FfbProduction",
    "idx:MaturePlantedArea", "idx:OilExtractionRate", "idx:BankLoans", "ifrs:LongTermBorrowings",
    "ifrs:ShortTermBorrowings", "ifrs:TradeAndOtherReceivables", "idx:OperatingExpenses",
    "ifrs:DepreciationAndAmortisationExpense")]

LSIP_Q3_GENUINE += [
    fact("ifrs:TradeAndOtherReceivables", 39_236 * M, 4, cell=(2, 7, 1), label="Piutang usaha - Pihak berelasi",
         seg={"segment": "Piutang usaha", "counterparty": "Pihak berelasi"}),
    fact("ifrs:TradeAndOtherReceivables", 25_922 * M, 4, cell=(2, 8, 1), label="Piutang usaha - Pihak ketiga",
         seg={"segment": "Piutang usaha", "counterparty": "Pihak ketiga"}),
]
LSIP_Q3_OMISSIONS = [o for o in LSIP_Q3_OMISSIONS if o["metric_id"] not in ("ifrs:TradeAndOtherReceivables", "ifrs:DepreciationAndAmortisationExpense")]
