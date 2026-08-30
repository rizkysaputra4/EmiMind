import asyncio
import os
import shutil
from pathlib import Path
from sqlalchemy import text
from services.shared.db import create_pool
from services.shared.config import get_settings

async def clean():
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)
    
    print("=" * 60)
    print("  MEMBERSIHKAN DATA DOKUMEN & TABEL TERKAIT")
    print("=" * 60)

    async with pool.begin() as conn:
        # Hapus data tabel turunan dokumen
        tables_to_clean = [
            "ingest_review_queue",
            "citation_reports",
            "concept_review",
            "kg_edges",
            "kg_nodes",
            "derived_metrics",
            "issuer_profile",
            "financial_facts",
            "narrative_chunks",
            "worker_runs",
            "conversation_turns",
            "documents",
        ]

        for t in tables_to_clean:
            try:
                await conn.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
                print(f"  [OK] Tabel {t:22s} telah dikosongkan.")
            except Exception as e:
                print(f"  [SKIP] Tabel {t:20s} ({e})")

    await pool.dispose()

    # Bersihkan file lokal minio-data/emimind-raw jika ada
    minio_raw = Path("minio-data") / "emimind-raw"
    if minio_raw.exists():
        for item in minio_raw.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
        print("  [OK] Folder penyimpanan objek MinIO (emimind-raw) telah dibersihkan.")

    print("\n" + "=" * 60)
    print("  SEMUA DATA DOKUMEN BERHASIL DIBERSIHKAN")
    print("  Siap untuk proses upload dan pengujian baru.")
    print("=" * 60)

asyncio.run(clean())
