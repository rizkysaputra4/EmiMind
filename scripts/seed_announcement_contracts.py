"""Load db/seeds/announcement_contracts/*.yaml into announcement_extraction_contracts.

Each YAML file names one doc_type. The contract body is stored as JSONB so the
MCP server can materialise it into ExtractionContract without further schema.

Adding a new bespoke contract:
    1. Write db/seeds/announcement_contracts/{DOC_TYPE}.yaml (see existing files).
    2. Ensure {DOC_TYPE} is in the doc_type CHECK constraint (migration 020).
    3. Re-run this script.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.shared.config import get_settings

SEED_DIR = Path(__file__).resolve().parents[1] / "db" / "seeds" / "announcement_contracts"


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.postgres_dsn)
    yaml_files = sorted(SEED_DIR.glob("*.yaml"))
    if not yaml_files:
        print(f"No YAMLs found in {SEED_DIR}")
        return

    async with engine.connect() as conn:
        for path in yaml_files:
            with path.open(encoding="utf-8") as f:
                body = yaml.safe_load(f)
            doc_type = (body.get("doc_type") or path.stem).upper()
            sector = (body.get("sector") or "UNIVERSAL").upper()
            await conn.execute(
                text(
                    """
                    INSERT INTO announcement_extraction_contracts (doc_type, sector, contract_json, updated_at)
                    VALUES (:dt, :sector, CAST(:body AS jsonb), now())
                    ON CONFLICT (doc_type) DO UPDATE
                        SET sector = EXCLUDED.sector,
                            contract_json = EXCLUDED.contract_json,
                            updated_at = now();
                    """
                ),
                {"dt": doc_type, "sector": sector, "body": json.dumps(body)},
            )
            print(f"  loaded {path.name} -> doc_type={doc_type}")
        await conn.commit()

    print(f"Loaded {len(yaml_files)} announcement contracts.")


if __name__ == "__main__":
    asyncio.run(main())
