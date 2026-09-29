"""Routing and contract services for EMIMIND MCP Server."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.mcp.contracts import (
    build_extraction_contract as default_build_extraction_contract,
)
from services.mcp.contracts import (
    get_route_query,
    load_page_router_queries,
)
from services.mcp.services.common import _log_processing_event, get_engine
from services.mcp.types import (
    ExtractionContract,
    PageTable,
    PageTableCell,
    RoutedPage,
    RoutedPages,
)
from services.retrieval.page_router import route_pages as default_route_pages
from services.shared.config import get_settings
from services.shared.minio_client import get_minio as default_get_minio


async def get_extraction_contract(
    doc_id: str,
    *,
    engine: AsyncEngine | None = None,
    contract_builder: Callable[..., Any] = default_build_extraction_contract,
) -> ExtractionContract:
    """Retrieves the dynamic extraction contract, required concepts, and scaling rules for a document."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        res = await conn.execute(
            text("SELECT id, ticker, fiscal_period, doc_type FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document with ID {doc_id} not found in database.")

        ticker = doc["ticker"]
        fiscal_period = doc["fiscal_period"]
        doc_type_val = doc["doc_type"]

        # Prefer issuer_profile (the extraction-scope allowlist); fall back to
        # peer_groups only if a stale doc_id exists for an unmapped ticker.
        prof_res = await conn.execute(
            text("SELECT name, sector, sub_sector FROM issuer_profile WHERE ticker = :ticker"),
            {"ticker": ticker},
        )
        prof_row = prof_res.mappings().first()
        if prof_row and prof_row.get("sector"):
            company_name = prof_row["name"] or f"PT {ticker} Tbk"
            sector_name = prof_row["sector"]
        else:
            sec_res = await conn.execute(
                text(
                    "SELECT name, sector, sub_sector FROM peer_groups WHERE :ticker = ANY(tickers) LIMIT 1"
                ),
                {"ticker": ticker},
            )
            sec_row = sec_res.mappings().first()
            company_name = (
                sec_row["name"] if sec_row and sec_row.get("name") else f"PT {ticker} Tbk"
            )
            sector_name = sec_row["sector"] if sec_row and sec_row.get("sector") else "GENERIC"

        contract = await contract_builder(
            conn,
            doc_id=str(doc_id),
            ticker=ticker,
            company_name=company_name,
            sector=sector_name,
            fiscal_period=fiscal_period,
            doc_type=doc_type_val,
        )
        return cast(ExtractionContract, contract)


async def get_routed_pages(
    doc_id: str,
    module: str,
    top_k: int = 3,
    *,
    engine: AsyncEngine | None = None,
    router_fn: Callable[..., Any] = default_route_pages,
    minio_getter: Callable[..., Any] = default_get_minio,
    log_event_fn: Callable[..., Any] = _log_processing_event,
) -> RoutedPages:
    """Return ranked page_index hits (+ expanded neighbours, text, image URL, and tables) for a contract module."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        res = await conn.execute(
            text(
                "SELECT id, ticker, fiscal_period, doc_type, minio_key, doc_hash FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document with ID {doc_id} not found in database.")

        ticker = doc["ticker"]
        prof_res = await conn.execute(
            text("SELECT sector FROM issuer_profile WHERE ticker = :ticker"),
            {"ticker": ticker},
        )
        prof_row = prof_res.mappings().first()
        sector = prof_row["sector"] if prof_row and prof_row.get("sector") else "GENERIC"

        route_query = get_route_query(module.upper(), sector)
        if not route_query:
            valid_modules = sorted(load_page_router_queries().keys())
            raise ValueError(
                f"Unknown module '{module}'. Valid modules are: {', '.join(valid_modules)}"
            )

        routed_spans = await router_fn(conn, str(doc_id), route_query, top_k=top_k)

        # Unique page numbers across all spans
        page_score_map: dict[int, float] = {}
        for s in routed_spans:
            for p in s.pages:
                if p not in page_score_map or s.score > page_score_map[p]:
                    page_score_map[p] = s.score

        unique_pages = sorted(page_score_map.keys())

        if not unique_pages:
            await log_event_fn(
                conn,
                action="ROUTED",
                source="get_routed_pages",
                file_name=Path(doc.get("minio_key") or "").name or f"{ticker}_{doc_id}.pdf",
                ticker=ticker,
                doc_id=str(doc_id),
                doc_hash=doc.get("doc_hash"),
                metadata={
                    "module": module.upper(),
                    "pages": [],
                    "span_count": len(routed_spans),
                    "chars": 0,
                    "text_chars": 0,
                    "table_chars": 0,
                    "images": 0,
                },
            )
            await conn.commit()
            return RoutedPages(
                doc_id=str(doc_id),
                module=module.upper(),
                total_pages_returned=0,
                pages=[],
                spans=[s.pages for s in routed_spans],
            )

        # Fetch page text and metadata
        pages_res = await conn.execute(
            text(
                """
                SELECT page_index, page_label, text_source, page_text, image_key
                FROM document_pages
                WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                ORDER BY page_index ASC
                """
            ),
            {"doc_id": doc_id, "pages": unique_pages},
        )
        page_records = {int(r["page_index"]): dict(r) for r in pages_res.mappings().all()}

        # Fetch page table grids
        tables_res = await conn.execute(
            text(
                """
                SELECT page_index, table_index, extraction_method, confidence, unit_hint, cells
                FROM document_page_tables
                WHERE doc_id = :doc_id AND page_index = ANY(:pages)
                ORDER BY page_index ASC, table_index ASC
                """
            ),
            {"doc_id": doc_id, "pages": unique_pages},
        )
        tables_by_page: dict[int, list[PageTable]] = {}
        for tr in tables_res.mappings().all():
            p_idx = int(tr["page_index"])
            raw_cells = tr["cells"] if isinstance(tr["cells"], list) else json.loads(tr["cells"])
            cells_objs = [
                PageTableCell(
                    row=int(c.get("row", 0)),
                    col=int(c.get("col", 0)),
                    text=str(c.get("text", "")),
                    value=float(c["value"]) if c.get("value") is not None else None,
                    bbox=c.get("bbox"),
                    confidence=float(c["confidence"]) if c.get("confidence") is not None else None,
                )
                for c in raw_cells
            ]
            tbl = PageTable(
                table_index=int(tr["table_index"]),
                extraction_method=str(tr["extraction_method"]),
                confidence=float(tr["confidence"]),
                unit_hint=tr.get("unit_hint"),
                cells=cells_objs,
            )
            tables_by_page.setdefault(p_idx, []).append(tbl)

        # MinIO Presigned URLs for thumbnails
        settings = get_settings()
        page_image_urls: dict[int, str | None] = {}
        try:
            minio_client = minio_getter(settings)
            for p_idx in unique_pages:
                prec = page_records.get(p_idx, {})
                img_key = prec.get("image_key")
                if img_key:
                    try:
                        url = minio_client.presigned_get_object(
                            settings.minio_bucket_raw, img_key, expires=timedelta(hours=1)
                        )
                        page_image_urls[p_idx] = url
                    except Exception:
                        page_image_urls[p_idx] = None
        except Exception:
            pass

        routed_pages_list: list[RoutedPage] = []
        for p_idx in unique_pages:
            prec = page_records.get(p_idx, {})
            routed_pages_list.append(
                RoutedPage(
                    page_index=p_idx,
                    page_label=prec.get("page_label"),
                    text_source=prec.get("text_source", "pdf_text"),
                    score=page_score_map.get(p_idx, 0.0),
                    page_text=prec.get("page_text", ""),
                    image_url=page_image_urls.get(p_idx),
                    tables=tables_by_page.get(p_idx, []),
                )
            )

        text_chars = sum(len(rp.page_text or "") for rp in routed_pages_list)
        table_chars = sum(
            len(tbl.model_dump_json()) for rp in routed_pages_list for tbl in rp.tables
        )
        served_chars = text_chars + table_chars
        images_served = sum(1 for rp in routed_pages_list if rp.image_url)

        # Log event
        file_name = Path(doc.get("minio_key") or "").name or f"{ticker}_{doc_id}.pdf"
        await log_event_fn(
            conn,
            action="ROUTED",
            source="get_routed_pages",
            file_name=file_name,
            ticker=ticker,
            doc_id=str(doc_id),
            doc_hash=doc.get("doc_hash"),
            metadata={
                "module": module.upper(),
                "pages": unique_pages,
                "span_count": len(routed_spans),
                # Served-content size, used by eval/deep_extraction_gate.py to compute tokens
                # server-side: tokens = chars / 4 + TOKENS_PER_PAGE_IMAGE x images.
                "chars": served_chars,
                "text_chars": text_chars,
                "table_chars": table_chars,
                "images": images_served,
            },
        )
        await conn.commit()

        return RoutedPages(
            doc_id=str(doc_id),
            module=module.upper(),
            total_pages_returned=len(routed_pages_list),
            pages=routed_pages_list,
            spans=[s.pages for s in routed_spans],
        )
