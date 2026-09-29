import psycopg
from services.mcp.types import ConceptDefinition
from services.mcp.fact_semantics import check_concept_label, name_variants
dsn = "postgresql://emimind:emimind@localhost:5432/emimind"
cases = [
 ("Kas","ifrs:CashAndCashEquivalents",False),
 ("Total kredit yang telah direstrukturisasi dalam kategori NPL","idx:NonPerformingLoansGross",False),
 ("Total simpanan dari bank lain","idx:BankLoans",False),
 ("Bunga yang masih akan diterima","ifrs:TradeAndOtherReceivables",False),
 ("Total Ekuitas","ifrs:EquityAttributableToOwnersOfParent",False),
 ("Bagian lancar atas liabilitas sewa","ifrs:ShortTermBorrowings",False),
 ("Kas dan setara kas akhir tahun","ifrs:CashAndCashEquivalents",True),
 ("Total Aset","ifrs:Assets",True),
 ("Ekuitas yang dapat diatribusikan kepada pemilik entitas induk","ifrs:EquityAttributableToOwnersOfParent",True),
 ("Laba tahun berjalan","ifrs:ProfitLoss",True),
 ("Beban pokok penjualan","ifrs:CostOfSales",True),
 ("Penjualan","ifrs:CostOfSales",False),
 ("Total Aset Lancar","ifrs:CurrentAssets",True),
 ("Total Aset Tidak Lancar","ifrs:NonCurrentAssets",True),
 ("Total Aset Lancar","ifrs:Assets",False),
 ("Total Liabilitas","ifrs:Liabilities",True),
 ("Total Liabilitas Jangka Pendek","ifrs:CurrentLiabilities",True),
 ("Total Liabilitas Jangka Panjang","ifrs:NonCurrentLiabilities",True),
 ("Total Ekuitas","ifrs:Equity",True),
 ("Pendapatan dari kontrak dengan pelanggan","ifrs:Revenue",True),
 ("Laba bruto","ifrs:GrossProfit",True),
 ("Laba periode berjalan","ifrs:ProfitLoss",True),
 ("Laba usaha","ifrs:OperatingProfit",True),
 ("Kas Neto yang Diperoleh dari Aktivitas Operasi","ifrs:CashFlowsFromUsedInOperatingActivities",True),
 ("Laba sebelum pajak penghasilan","ifrs:ProfitBeforeTax",True),
 ("Beban pajak penghasilan","ifrs:IncomeTaxExpense",True),
 ("Persediaan","ifrs:Inventories",True),
 ("Aset tetap","ifrs:PropertyPlantAndEquipment",True),
 ("Aset biologis","ifrs:BiologicalAssets",True),
 ("Beban keuangan","ifrs:FinanceCosts",True),
 ("Penghasilan keuangan","ifrs:FinanceIncome",True),
 ("Beban penjualan dan distribusi","ifrs:SellingExpense",True),
 ("Beban umum dan administrasi","ifrs:AdministrativeExpense",True),
 ("Kredit yang diberikan","idx:LoansAndAdvances",True),
 ("Laba yang dapat diatribusikan kepada pemilik entitas induk","ifrs:ProfitLossAttributableToOwnersOfParent",True),
]
ids = sorted({c for _,c,_ in cases})
with psycopg.connect(dsn) as c:
    cur = c.cursor()
    cur.execute("SELECT metric_id, name_id, name_en, synonyms_id, synonyms_en, flow_stock_type FROM metric_definitions WHERE metric_id = ANY(%s)", (ids,))
    defs = {r[0]: ConceptDefinition(metric_id=r[0], name_id=r[1] or "", name_en=r[2] or "", synonyms_id=r[3] or [], synonyms_en=r[4] or [], flow_stock_type=r[5]) for r in cur.fetchall()}
bad = 0
for label, cid, exp in cases:
    d = defs.get(cid)
    if d is None:
        print("NOT IN ONTOLOGY", cid); continue
    v = check_concept_label(label, d)
    flag = "OK " if v.ok == exp else "XX "
    bad += v.ok != exp
    print(flag, v.ok, label, "->", cid, "|", v.reason[:150])
print("mismatches", bad)
