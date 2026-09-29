import sys
sys.path.insert(0, r"C:\Users\rizky\Documents\Code\EmiMind")
from services.mcp.periods import resolve_fiscal_period as r, resolve_period_from_text as t
tests = ["Pengantar Lap Keu Q1 31 Maret 2026.pdf","013-BWPT-Corsec-III-2021 LK 31 Desember 2020.pdf","001-DIR-I-2025 Laporan Juni 2025.pdf",
"Laporan Keuangan Unaudited Juni 2024.pdf", "LK Desember 2023 dan 2022.pdf", "Public Expose 2025.pdf",
"Checklist.pdf", "ESG2025-IPCM.pdf", "Surat Pengantar.pdf", "FS 31 Mar 2023 (Unaudited).pdf",
"Laporan Keuangan per 31 Desember 2023 & 2022.pdf", "LK Triwulan II 2025.pdf", "Laporan Tahunan 2024.pdf",
"Semester I 2024.pdf", "LK Q3 2025.pdf", "Q1-2025.pdf", "FS_2024-12-31.pdf", "LK 30 September 2024.pdf",
"report_20240630.pdf", "LK Kuartal 1 2024.pdf", "LKT 2023.pdf", "FinancialStatement-2022-IV-XXXX.pdf",
"Sustainability Report 2024.pdf", "LK Juni 2024 (Revisi Desember).pdf", "Laporan Keuangan Sept 2024.pdf",
"FOOD_2023_TW1_RDF_LK PT SFI TW 3_2022.pdf","BWPT_2021_TW3_RDF_013-BWPT-Corsec-III-2021.pdf","INDX_2020_TW2_RDF_Q2_FY2020_Checklist Pengungkapan Laporan Keuangan.pdf",
"LPPS_2025_TW3_RDF_041-LPPS-PengantarLapKeu-30Sep25.pdf","202603_ULTJ_Group_Q1_FR.pdf","June 30, 2024 FS.pdf","random_scan.pdf","Semester 2 2023.pdf", "H1 2024 results.pdf"]
for n in tests:
    x = r(n)
    print(f"{n!r:75} -> {x.fiscal_period if x else None} {x.source if x else ''} {'CONFLICT->'+x.conflicting_period if x and x.conflict else ''}")
for h in ["2025H1", "2025q2", " 2024FY ", "2025H2"]:
    print(h, r("x.pdf", h).fiscal_period)
print(t("LAPORAN KEUANGAN KONSOLIDASIAN INTERIM 30 JUNI 2025 DAN 31 DESEMBER 2024 SERTA UNTUK PERIODE ENAM BULAN YANG BERAKHIR 30 JUNI 2025 DAN 2024"))
print(t("Consolidated financial statements as of 31 December 2025 and for the year then ended. Jakarta, 30 Maret 2026"))
print(t("December 31, 2025 and 2024"))
