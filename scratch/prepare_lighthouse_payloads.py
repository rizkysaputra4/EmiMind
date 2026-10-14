"""Prepare and validate extraction payloads for BMRI and LSIP lighthouse reports."""

import asyncio
import json
from decimal import Decimal
from services.mcp.services.common import get_engine
from services.mcp.services.routing import get_extraction_contract
from services.mcp.services.extraction import submit_draft_extraction, commit_verified_report
from services.mcp.types import (
    CellRef,
    DraftSubmissionPayload,
    ExtractedCausalLink,
    ExtractedFactItem,
    ExtractedNarrativeItem,
    MetricOmissionItem,
    ProcessingUsage,
)

async def test_bmri():
    engine = get_engine()
    doc_id = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"
    contract = await get_extraction_contract(doc_id, engine=engine)
    print("BMRI contract loaded. Required facts:", len(contract.required_facts))

async def main():
    await test_bmri()

if __name__ == "__main__":
    asyncio.run(main())
