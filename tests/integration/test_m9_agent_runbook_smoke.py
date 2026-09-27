"""Integration test for Agent Runbook workflow & token logging (M9.5.1, M9.5.2)."""
# ruff: noqa: PLR0915, ASYNC240

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from services.ingest.tasks.index_pages import index_pages_task
from services.mcp.server import (
    commit_verified_report,
    get_engine,
    get_extraction_contract,
    get_routed_pages,
    inspect_document,
    submit_draft_extraction,
)
from services.mcp.types import (
    CellRef,
    DraftSubmissionPayload,
    ExtractedFactItem,
    ExtractedNarrativeItem,
    InspectionStatus,
    OmittedMetricItem,
    ProcessingUsage,
)
from services.shared.config import get_settings
from services.shared.minio_client import ensure_bucket, get_minio
from tests.fixtures.m9.build_fixtures import build_fs_small


@pytest.mark.integration
@pytest.mark.asyncio
async def test_m9_agent_runbook_smoke() -> None:
    engine = get_engine()
    settings = get_settings()
    minio_client = get_minio(settings)
    ensure_bucket(minio_client, settings.minio_bucket_raw)

    ticker = "XXXX"
    incoming_dir = Path("incoming_reports").resolve()
    incoming_dir.mkdir(parents=True, exist_ok=True)
    pdf_filename = f"{ticker}_2025_AUDIT_RDF_fs_small.pdf"
    incoming_pdf_path = incoming_dir / pdf_filename

    # Clean up prior artifacts if any
    if incoming_pdf_path.exists():
        incoming_pdf_path.unlink()
    processed_pdf_path = incoming_dir / "processed" / pdf_filename
    if processed_pdf_path.exists():
        processed_pdf_path.unlink()

    # Clean up prior database rows if any
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM derived_metrics WHERE ticker = 'XXXX' OR peer_group_id = 'BANK_TEST'"))
        await conn.execute(text("DELETE FROM financial_facts WHERE ticker = 'XXXX'"))
        await conn.execute(text("DELETE FROM narrative_chunks WHERE ticker = 'XXXX'"))
        await conn.execute(text("DELETE FROM document_processing_log WHERE ticker = 'XXXX'"))
        await conn.execute(
            text("DELETE FROM document_page_tables WHERE doc_id IN (SELECT id FROM documents WHERE ticker = 'XXXX')")
        )
        await conn.execute(
            text("DELETE FROM document_pages WHERE doc_id IN (SELECT id FROM documents WHERE ticker = 'XXXX')")
        )
        await conn.execute(text("DELETE FROM documents WHERE ticker = 'XXXX'"))
        await conn.commit()

    # 1. Seed XXXX in issuer_profile and peer_groups as BANK
    async with engine.connect() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO issuer_profile (ticker, name, sector, sub_sector)
                VALUES (:ticker, 'PT Bank XXXX Tbk', 'BANK', 'COMMERCIAL_BANK')
                ON CONFLICT (ticker) DO UPDATE SET sector = 'BANK', name = 'PT Bank XXXX Tbk';
                """
            ),
            {"ticker": ticker},
        )
        await conn.execute(
            text(
                """
                INSERT INTO peer_groups (id, name, sector, tickers)
                VALUES ('BANK_TEST', 'Test Banks', 'BANK', ARRAY[:ticker])
                ON CONFLICT (id) DO UPDATE SET tickers = ARRAY[:ticker];
                """
            ),
            {"ticker": ticker},
        )
        await conn.commit()

    try:
        # 2. Build synthetic fixture directly into incoming_reports/
        build_fs_small(incoming_pdf_path)

        # Runbook Step 1: inspect_document
        insp = await inspect_document(str(incoming_pdf_path), ticker=ticker, fiscal_period="2025Q4")
        assert insp.status == InspectionStatus.AUTHORIZED
        assert insp.doc_id is not None
        doc_id = insp.doc_id

        # Run page indexing task synchronously to generate pages and table grids
        ctx = {"db_engine": engine, "minio": minio_client, "settings": settings}
        await index_pages_task(ctx, doc_id)

        # Runbook Step 2: get_extraction_contract
        contract = await get_extraction_contract(doc_id)
        assert contract.sector == "BANK"
        assert len(contract.required_facts) > 0

        # Runbook Step 3: get_routed_pages
        bs_routed = await get_routed_pages(doc_id, "BALANCE_SHEET")
        assert any(p.page_index == 2 for p in bs_routed.pages)

        is_routed = await get_routed_pages(doc_id, "INCOME_STATEMENT")
        assert any(p.page_index == 3 for p in is_routed.pages)

        loans_routed = await get_routed_pages(doc_id, "BANK_LOANS_NPL")
        assert any(p.page_index in (5, 6) for p in loans_routed.pages)

        # Runbook Step 4: Extract facts citing cell_ref
        facts: list[ExtractedFactItem] = [
            # Balance Sheet (Page 2, Table 0, IDR_MN)
            ExtractedFactItem(
                concept_id="ifrs:Assets",
                value_numeric=Decimal("100000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Jumlah aset",
                cell_ref=CellRef(table_index=0, row=4, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:Liabilities",
                value_numeric=Decimal("70000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Jumlah liabilitas",
                cell_ref=CellRef(table_index=0, row=7, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:Equity",
                value_numeric=Decimal("30000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Jumlah ekuitas",
                cell_ref=None,  # Text-grounded on Page 2
            ),
            ExtractedFactItem(
                concept_id="ifrs:CashAndCashEquivalents",
                value_numeric=Decimal("10000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Kas dan setara kas",
                cell_ref=CellRef(table_index=0, row=1, col=2),
            ),
            ExtractedFactItem(
                concept_id="idx:LoansAndAdvances",
                value_numeric=Decimal("80000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Kredit yang diberikan",
                cell_ref=CellRef(table_index=0, row=2, col=2),
            ),
            ExtractedFactItem(
                concept_id="idx:CustomerDeposits",
                value_numeric=Decimal("50000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Simpanan nasabah",
                cell_ref=CellRef(table_index=0, row=6, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:IssuedCapital",
                value_numeric=Decimal("20000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Modal saham",
                cell_ref=CellRef(table_index=0, row=8, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:RetainedEarnings",
                value_numeric=Decimal("10000000000"),
                source_page=2,
                statement="BS",
                source_label_original="Saldo laba",
                cell_ref=CellRef(table_index=0, row=9, col=2),
            ),
            # Income Statement (Page 3, Table 0, IDR_MN)
            ExtractedFactItem(
                concept_id="ifrs:Revenue",
                value_numeric=Decimal("20000000000"),
                source_page=3,
                statement="IS",
                source_label_original="Pendapatan bunga dan operasional",
                cell_ref=CellRef(table_index=0, row=1, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:CostOfSales",
                value_numeric=Decimal("12000000000"),
                source_page=3,
                statement="IS",
                source_label_original="Beban bunga dan operasional",
                cell_ref=CellRef(table_index=0, row=2, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:GrossProfit",
                value_numeric=Decimal("8000000000"),
                source_page=3,
                statement="IS",
                source_label_original="Laba kotor / pendapatan bersih",
                cell_ref=CellRef(table_index=0, row=3, col=2),
            ),
            ExtractedFactItem(
                concept_id="idx:OperatingExpenses",
                value_numeric=Decimal("3000000000"),
                source_page=3,
                statement="IS",
                source_label_original="Beban usaha",
                cell_ref=CellRef(table_index=0, row=4, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:OperatingProfit",
                value_numeric=Decimal("5000000000"),
                source_page=3,
                statement="IS",
                source_label_original="Laba operasional",
                cell_ref=CellRef(table_index=0, row=5, col=2),
            ),
            ExtractedFactItem(
                concept_id="ifrs:ProfitLoss",
                value_numeric=Decimal("4000000000"),
                source_page=3,
                statement="IS",
                source_label_original="Laba bersih tahun berjalan",
                cell_ref=CellRef(table_index=0, row=6, col=2),
            ),
            # Note 12: Loans and Collectibility (Page 5 and 6, Table 0, IDR_MN)
            ExtractedFactItem(
                concept_id="idx:LoansGross",
                value_numeric=Decimal("80000000000"),
                source_page=6,
                statement="NOTE",
                source_label_original="Jumlah kredit",
                cell_ref=CellRef(table_index=0, row=3, col=5),
            ),
            # 5 Segmented collectibility items (>= 4 required by M9.5.1)
            ExtractedFactItem(
                concept_id="idx:LoansGross",
                value_numeric=Decimal("70000000000"),
                source_page=5,
                statement="NOTE",
                source_label_original="Lancar",
                segment={"collectibility": "Lancar", "type": "loan_collectibility"},
                cell_ref=CellRef(table_index=0, row=1, col=5),
            ),
            ExtractedFactItem(
                concept_id="idx:LoansGross",
                value_numeric=Decimal("5000000000"),
                source_page=5,
                statement="NOTE",
                source_label_original="Dalam Perhatian Khusus",
                segment={"collectibility": "Dalam Perhatian Khusus", "type": "loan_collectibility"},
                cell_ref=CellRef(table_index=0, row=2, col=5),
            ),
            ExtractedFactItem(
                concept_id="idx:LoansGross",
                value_numeric=Decimal("2000000000"),
                source_page=5,
                statement="NOTE",
                source_label_original="Kurang Lancar",
                segment={"collectibility": "Kurang Lancar", "type": "loan_collectibility"},
                cell_ref=CellRef(table_index=0, row=3, col=5),
            ),
            ExtractedFactItem(
                concept_id="idx:LoansGross",
                value_numeric=Decimal("1000000000"),
                source_page=6,
                statement="NOTE",
                source_label_original="Diragukan",
                segment={"collectibility": "Diragukan", "type": "loan_collectibility"},
                cell_ref=CellRef(table_index=0, row=1, col=5),
            ),
            ExtractedFactItem(
                concept_id="idx:LoansGross",
                value_numeric=Decimal("2000000000"),
                source_page=6,
                statement="NOTE",
                source_label_original="Macet",
                segment={"collectibility": "Macet", "type": "loan_collectibility"},
                cell_ref=CellRef(table_index=0, row=2, col=5),
            ),
        ]

        # Declare missing required items in omitted_kpis
        covered_cids = {f.concept_id for f in facts}
        omitted: list[OmittedMetricItem] = [
            OmittedMetricItem(
                metric_id="ifrs:Revenue_SEGMENTS",
                reason="NOT_DISCLOSED_IN_REPORT",
                explanation="Issuer operates single line of commercial banking with no product line breakdown disclosed",
                search_pages_checked=[3, 5, 6],
            )
        ]
        for req in contract.required_facts:
            if req.concept_id not in covered_cids:
                omitted.append(
                    OmittedMetricItem(
                        metric_id=req.concept_id,
                        reason="NOT_DISCLOSED_IN_REPORT",
                        explanation=f"Metric {req.concept_id} not separately disclosed in small test report",
                        search_pages_checked=[2, 3, 5, 6],
                    )
                )

        narratives = [
            ExtractedNarrativeItem(
                section="MDA",
                text_original="Pada tahun 2025, PT Bank XXXX Tbk mencatatkan peningkatan pendapatan sebesar 11,1% menjadi Rp20.000 miliar.",
                source_page=7,
                topic="FINANCIAL_PERFORMANCE",
            )
        ]

        usage_dict = {"input_tokens": 14200, "output_tokens": 850, "pages_read": 8}

        payload = DraftSubmissionPayload(
            doc_id=doc_id,
            ticker=ticker,
            fiscal_period="2025Q4",
            facts=facts,
            narratives=narratives,
            omitted_kpis=omitted,
            usage=ProcessingUsage(**usage_dict),
        )
        payload_json = json.dumps(payload.model_dump(mode="json"))

        # Runbook Step 6: submit_draft_extraction with usage
        val_rep = await submit_draft_extraction(payload_json, usage=usage_dict)
        assert val_rep.status == "VALID", f"Validation issues: {val_rep.issues}"

        # Runbook Step 7: commit_verified_report with usage
        commit_rep = await commit_verified_report(payload_json, usage=usage_dict)
        assert commit_rep.status == "COMMITTED"
        assert commit_rep.facts_committed >= 15

        # Verification per M9.5.1 and M9.5.2
        async with engine.connect() as conn:
            # 1. table_parser facts >= 10
            tp_res = await conn.execute(
                text(
                    "SELECT count(*) FROM financial_facts WHERE ticker = :ticker AND extraction_method = 'table_parser'"
                ),
                {"ticker": ticker},
            )
            tp_count = tp_res.scalar() or 0
            assert tp_count >= 10, f"Expected >= 10 table_parser facts, got {tp_count}"

            # 2. segment ? 'collectibility' >= 4
            coll_res = await conn.execute(
                text(
                    "SELECT count(*) FROM financial_facts WHERE ticker = :ticker AND segment ? 'collectibility'"
                ),
                {"ticker": ticker},
            )
            coll_count = coll_res.scalar() or 0
            assert coll_count >= 4, f"Expected >= 4 collectibility facts, got {coll_count}"

            # 3. input_tokens non-null in COMMITTED log entry (M9.5.2)
            log_res = await conn.execute(
                text(
                    """
                    SELECT metadata->>'input_tokens' as tokens
                    FROM document_processing_log
                    WHERE doc_id = :doc_id AND action = 'COMMITTED'
                    """
                ),
                {"doc_id": doc_id},
            )
            logged_tokens = log_res.scalar()
            assert logged_tokens is not None, "Expected input_tokens in COMMITTED document_processing_log metadata"
            assert int(logged_tokens) == 14200

    finally:
        # Clean up database test rows and files
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM derived_metrics WHERE ticker = 'XXXX' OR peer_group_id = 'BANK_TEST'"))
            await conn.execute(text("DELETE FROM financial_facts WHERE ticker = 'XXXX'"))
            await conn.execute(text("DELETE FROM narrative_chunks WHERE ticker = 'XXXX'"))
            await conn.execute(text("DELETE FROM document_processing_log WHERE ticker = 'XXXX'"))
            await conn.execute(
                text("DELETE FROM document_page_tables WHERE doc_id IN (SELECT id FROM documents WHERE ticker = 'XXXX')")
            )
            await conn.execute(
                text("DELETE FROM document_pages WHERE doc_id IN (SELECT id FROM documents WHERE ticker = 'XXXX')")
            )
            await conn.execute(text("DELETE FROM documents WHERE ticker = 'XXXX'"))
            await conn.execute(text("DELETE FROM issuer_profile WHERE ticker = 'XXXX'"))
            await conn.execute(text("DELETE FROM peer_groups WHERE id = 'BANK_TEST'"))
            await conn.commit()

        if incoming_pdf_path.exists():
            incoming_pdf_path.unlink()
        if processed_pdf_path.exists():
            processed_pdf_path.unlink()
