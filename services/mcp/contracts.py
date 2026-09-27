"""Ontology-driven extraction contract generation for EMIMIND MCP Server.

All sector-specific extraction rules, granular note modules, and narrative
requirements live in the database (see migration 019 + seed_metric_ontology.py
+ seed_extraction_narratives.py). This module only queries and assembles them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.mcp.types import (
    ExtractionContract,
    ExtractionFactRule,
    ExtractionNarrativeRule,
    GranularNoteModule,
    RouteQuery,
)

_PAGE_ROUTER_QUERIES: dict[str, dict[str, Any]] | None = None


def load_page_router_queries() -> dict[str, dict[str, Any]]:
    """Loads and caches page router query definitions from db/seeds/page_router_queries.yaml."""
    global _PAGE_ROUTER_QUERIES
    if _PAGE_ROUTER_QUERIES is None:
        yaml_path = Path(__file__).resolve().parents[2] / "db" / "seeds" / "page_router_queries.yaml"
        if not yaml_path.is_file():
            yaml_path = Path("db/seeds/page_router_queries.yaml").resolve()
        if yaml_path.is_file():
            with open(yaml_path, "r", encoding="utf-8") as f:
                _PAGE_ROUTER_QUERIES = yaml.safe_load(f) or {}
        else:
            _PAGE_ROUTER_QUERIES = {}
    return _PAGE_ROUTER_QUERIES


def get_route_query(module_name: str, sector: str = "ALL") -> RouteQuery | None:
    """Returns RouteQuery for a given module and sector, falling back to ALL or aliases."""
    queries = load_page_router_queries()
    mod_data = queries.get(module_name)
    if not mod_data:
        alias_map = {
            "BANK_LOAN_QUALITY_NPL": "BANK_LOANS_NPL",
            "BIOLOGICAL_ASSETS_DETAIL": "PLANTATION_AREA",
            "BIOLOGICAL_ASSETS": "PLANTATION_AREA",
            "REVENUE_BREAKDOWN": "REVENUE_CUSTOMERS",
            "CUSTOMER_CONCENTRATION": "REVENUE_CUSTOMERS",
            "COGS_COMPONENTS": "COGS_BREAKDOWN",
            "DEBT_BY_LENDER": "DEBT_FACILITIES",
        }
        target_mod = alias_map.get(module_name)
        if target_mod:
            mod_data = queries.get(target_mod)
    if not mod_data:
        return None

    sec_keys = [sector]
    if sector == "CPO":
        sec_keys.append("PLANTATION")
    elif sector == "PLANTATION":
        sec_keys.append("CPO")
    sec_keys.append("ALL")

    entry = None
    for k in sec_keys:
        if k in mod_data:
            entry = mod_data[k]
            break

    if not entry:
        return None

    return RouteQuery(
        terms_id=list(entry.get("terms_id", [])),
        terms_en=list(entry.get("terms_en", [])),
        max_pages=int(entry.get("max_pages", 6)),
        anchor_patterns=list(entry.get("anchor_patterns", [])),
    )


_STANDARD_SCALING_RULES: dict[str, Any] = {
    "unit": "IDR",
    "instructions": (
        "All extracted monetary amounts must be converted to full IDR integer/decimal "
        "value before submission. Inspect the top of each financial statement table for "
        "'Disajikan dalam jutaan rupiah' (multiply by 1,000,000) or 'Disajikan dalam "
        "ribuan rupiah' (multiply by 1,000)."
    ),
}

_DO_NOT_EXTRACT = [
    "Do NOT extract financial ratios (ROE, ROA, DER, PE, PBV, Margins, NIM) unless the ratio itself is a required KPI in the sector contract. EMIMIND derives them.",
    "Do NOT extract prior year comparative columns unless specifically asked.",
    "Do NOT extract decorative or boilerplate auditor opinion letters.",
]

_UNIVERSAL_GUIDELINES = [
    "Granular Decomposition: Do NOT stop at top-level financial statements. Extract every disclosure table listed in `granular_note_modules` into segmented ExtractedFactItems.",
    "Precision: Capture exact monetary numbers and exact unit/shares. Do not round numbers.",
    "Targeted Navigation: Use the 'Index of Notes' (Daftar Catatan) to jump to target pages. Do NOT read the entire PDF sequentially.",
    "Causality: When management explains WHY a metric changed, capture it in 'causal_links'.",
    "Sign conventions: Cost of Sales, Expenses, and negative Cash Flows should be positive numbers in the payload.",
    "Provenance: Every ExtractedFactItem MUST include source_page (1-indexed) and source_label_original.",
    "Prime-then-validate: Every metric below carries its own importance (CRITICAL/HIGH/OPTIONAL), synonyms, and search hints. Treat CRITICAL as non-negotiable; declare omitted_kpis with search_pages_checked only after exhausting all hints.",
]


async def _load_metrics(conn: AsyncConnection, sector: str) -> list[ExtractionFactRule]:
    result = await conn.execute(
        text(
            """
            SELECT
                metric_id, name_en, name_id, label_bilingual, category,
                sector_applicability, importance, value_type, unit,
                statement_type, extraction_mode, calculation_formula, dependencies,
                synonyms_id, synonyms_en, search_hints, extraction_guideline,
                expected_segment_fields
            FROM metric_definitions
            WHERE sector_applicability && ARRAY[:sector, 'ALL']::TEXT[]
            ORDER BY
                CASE importance
                    WHEN 'CRITICAL' THEN 0
                    WHEN 'HIGH' THEN 1
                    WHEN 'OPTIONAL' THEN 2
                    ELSE 3
                END,
                category, metric_id
            """
        ),
        {"sector": sector},
    )
    rules: list[ExtractionFactRule] = []
    for row in result.mappings():
        importance = (row["importance"] or "HIGH").upper()
        extraction_mode = (row["extraction_mode"] or "EXTRACTED_RAW").upper()
        # Only EXTRACTED_RAW metrics are extraction-mandatory. CALCULATED_DETERMINISTIC
        # is computed from dependencies; HYBRID_FALLBACK is extracted if disclosed but
        # falls back to computation. Both are shown in the contract for transparency
        # but do not block on absence.
        is_required = importance in ("CRITICAL", "HIGH") and extraction_mode == "EXTRACTED_RAW"
        rules.append(
            ExtractionFactRule(
                concept_id=row["metric_id"],
                label=row["label_bilingual"] or f"{row['name_id']} / {row['name_en']}",
                statement_type=row["statement_type"] or "NOTE",
                required=is_required,
                description=None,
                importance=importance,
                extraction_mode=extraction_mode,
                synonyms_id=list(row["synonyms_id"] or []),
                synonyms_en=list(row["synonyms_en"] or []),
                search_hints=list(row["search_hints"] or []),
                extraction_guideline=row["extraction_guideline"],
                expected_segment_fields=list(row["expected_segment_fields"] or []),
                calculation_formula=row["calculation_formula"],
                dependencies=list(row["dependencies"] or []),
                unit=row["unit"] or "IDR",
                value_type=row["value_type"] or "MONETARY",
            )
        )
    return rules


async def _load_granular_modules(conn: AsyncConnection, sector: str) -> list[GranularNoteModule]:
    result = await conn.execute(
        text(
            """
            SELECT
                sector_code, module_name, typical_note_title, description,
                target_concepts, expected_segment_fields, guideline, is_mandatory
            FROM sector_metric_contracts
            WHERE sector_code = :sector
               OR (:sector = 'PLANTATION' AND sector_code = 'CPO')
               OR (:sector = 'CPO' AND sector_code = 'PLANTATION')
               OR sector_code = 'ALL'
            ORDER BY sector_code, module_name
            """
        ),
        {"sector": sector},
    )
    modules: list[GranularNoteModule] = []
    seen_module_names: set[str] = set()
    for row in result.mappings():
        mod_name = row["module_name"]
        seen_module_names.add(mod_name)
        rq = get_route_query(mod_name, sector)
        modules.append(
            GranularNoteModule(
                name=mod_name,
                description=row["description"],
                typical_note_title=row["typical_note_title"],
                target_concepts=list(row["target_concepts"] or []),
                expected_segment_fields=list(row["expected_segment_fields"] or []),
                guideline=row["guideline"],
                route_query=rq,
            )
        )

    # If no modules were found in the database for this sector, add default required router modules
    if not seen_module_names:
        if sector == "BANK":
            rq = get_route_query("BANK_LOANS_NPL", sector)
            modules.append(
                GranularNoteModule(
                    name="BANK_LOANS_NPL",
                    description="Kolektibilitas kredit dan pencadangan kerugian (NPL, CKPN).",
                    typical_note_title="Catatan Kualitas Aset Produktif / Kolektibilitas Kredit",
                    target_concepts=["idx:LoansAndAdvances", "idx:NonPerformingLoansGross", "idx:NPLCoverageRatio"],
                    expected_segment_fields=["segment", "type", "kol_rating", "npl_status"],
                    guideline="Extract loan quality and NPL per collectibility category.",
                    route_query=rq,
                )
            )
        elif sector in ("PLANTATION", "CPO"):
            rq = get_route_query("PLANTATION_AREA", sector)
            modules.append(
                GranularNoteModule(
                    name="PLANTATION_AREA",
                    description="Profil kebun kelapa sawit: luas areal tertanam (tanaman menghasilkan/mature vs belum menghasilkan/immature).",
                    typical_note_title="Catatan Tanaman Produktif / Aset Biologis / Perkebunan",
                    target_concepts=["ifrs:BiologicalAssets", "idx:MaturePlantedArea"],
                    expected_segment_fields=["segment", "type", "planted_area_ha"],
                    guideline="Extract planted hectares breakdown with segment={'segment': 'Mature/Immature', 'type': 'biological_asset_maturity', 'planted_area_ha': <ha>}.",
                    route_query=rq,
                )
            )

    return modules


async def _load_narrative_rules(conn: AsyncConnection, sector: str) -> list[ExtractionNarrativeRule]:
    result = await conn.execute(
        text(
            """
            SELECT topic, expected_section, target_note_description, guideline
            FROM extraction_narrative_rules
            WHERE sector_applicability && ARRAY[:sector, 'ALL']::TEXT[]
            ORDER BY
                CASE importance
                    WHEN 'CRITICAL' THEN 0
                    WHEN 'HIGH' THEN 1
                    ELSE 2
                END,
                topic
            """
        ),
        {"sector": sector},
    )
    rules: list[ExtractionNarrativeRule] = []
    for row in result.mappings():
        rules.append(
            ExtractionNarrativeRule(
                topic=row["topic"],
                target_note_description=row["target_note_description"],
                expected_section=row["expected_section"],
                guideline=row["guideline"],
            )
        )
    return rules


ANNOUNCEMENT_DOC_TYPES = {
    "DIVIDEND", "RIGHTS_ISSUE", "RUPS_RESULT", "MATERIAL_INFO",
    "BOND_ISSUE", "AFFILIATED_TX", "PRIVATE_PLACEMENT", "TENDER_OFFER",
    "INSIDER_TX", "BOARD_CHANGE", "SHARE_BUYBACK", "SUSPEND_NOTICE",
    "UNSUSPEND_NOTICE", "PUBLIC_EXPOSE", "ARTICLES_AMENDMENT",
    "NAME_CHANGE", "LISTING_ACTION", "GENERIC_DISCLOSURE",
}


def _build_generic_disclosure_contract(
    *,
    doc_id: str,
    ticker: str,
    company_name: str,
    fiscal_period: str,
) -> ExtractionContract:
    """Safety-net contract used when no bespoke announcement contract exists.

    Design: docs/PENGUMUMAN_EXTRACTION_DESIGN.md §4.3. Fields are HIGH (not
    CRITICAL) so a submission with a few filled fields validates — announcements
    vary enormously and demanding all fields would fail most of the corpus.
    """
    facts = [
        ExtractionFactRule(
            concept_id="disclosure:doc_date",
            label="Tanggal pengumuman / Document date",
            statement_type="NOTE",
            importance="HIGH",
            extraction_mode="EXTRACTED_RAW",
            synonyms_id=["tanggal pengumuman", "tanggal dokumen"],
            synonyms_en=["document date", "announcement date"],
            unit="DATE",
            value_type="DATE",
        ),
        ExtractionFactRule(
            concept_id="disclosure:effective_date",
            label="Tanggal efektif / Effective date",
            statement_type="NOTE",
            importance="HIGH",
            extraction_mode="EXTRACTED_RAW",
            synonyms_id=["tanggal efektif", "berlaku efektif"],
            synonyms_en=["effective date"],
            unit="DATE",
            value_type="DATE",
        ),
        ExtractionFactRule(
            concept_id="disclosure:parties",
            label="Pihak-pihak terkait / Parties involved",
            statement_type="NOTE",
            importance="HIGH",
            extraction_mode="EXTRACTED_RAW",
            synonyms_id=["pihak", "pihak terkait"],
            synonyms_en=["parties", "counterparty"],
            unit="TEXT",
            value_type="TEXT",
        ),
        ExtractionFactRule(
            concept_id="disclosure:monetary_amounts",
            label="Nilai transaksi / Monetary amounts",
            statement_type="NOTE",
            importance="HIGH",
            extraction_mode="EXTRACTED_RAW",
            synonyms_id=["nilai", "jumlah", "nominal"],
            synonyms_en=["amount", "value", "principal"],
            unit="IDR",
            value_type="MONETARY",
        ),
        ExtractionFactRule(
            concept_id="disclosure:key_dates",
            label="Tanggal-tanggal penting / Key dates",
            statement_type="NOTE",
            importance="HIGH",
            extraction_mode="EXTRACTED_RAW",
            synonyms_id=["tanggal cum", "tanggal ex", "tanggal pembayaran", "tanggal recording"],
            synonyms_en=["cum date", "ex date", "payment date", "recording date"],
            unit="DATE",
            value_type="DATE",
        ),
        ExtractionFactRule(
            concept_id="disclosure:event_type_hint",
            label="Jenis kejadian / Event type hint",
            statement_type="NOTE",
            importance="OPTIONAL",
            extraction_mode="EXTRACTED_RAW",
            synonyms_id=["jenis", "kategori"],
            synonyms_en=["event type", "category"],
            unit="TEXT",
            value_type="TEXT",
        ),
    ]
    narratives = [
        ExtractionNarrativeRule(
            topic="disclosure_summary",
            target_note_description="Ringkasan pengumuman: apa, siapa, kapan, mengapa, dampak.",
            expected_section="MGMT_STMT",
            guideline=(
                "Produce a 3–6 sentence narrative summarising the announcement: the event, the "
                "parties involved, timing, financial impact if disclosed, and management rationale. "
                "Do NOT invent numbers not present in the source PDF."
            ),
        ),
    ]
    guidelines = [
        f"Target Issuer: {company_name} ({ticker}) — Announcement (GENERIC_DISCLOSURE), Period: {fiscal_period}.",
        "This is a generic disclosure contract used when no bespoke announcement contract exists.",
        "Extract what is CLEARLY stated in the document. Never fabricate KPIs to satisfy the shape.",
        "Announcements are typically 1–10 pages; scanning the full PDF is acceptable and expected.",
        "Provenance: every ExtractedFactItem MUST include source_page (1-indexed) and source_label_original.",
    ]
    return ExtractionContract(
        doc_id=doc_id,
        ticker=ticker.upper(),
        company_name=company_name,
        sector="UNIVERSAL",
        fiscal_period=fiscal_period.upper(),
        period_type="instant",
        scaling_rules=_STANDARD_SCALING_RULES,
        required_facts=facts,
        required_narratives=narratives,
        granular_note_modules=[],
        sector_specific_guidelines=guidelines,
        do_not_extract=[
            "Do NOT extract standard financial statements (BS / IS / CF) unless the announcement re-states them.",
            "Do NOT extract prior-period comparative data unless the announcement structures a table around it.",
        ],
    )


async def _load_announcement_contract_from_db(
    conn: AsyncConnection,
    *,
    doc_type: str,
    doc_id: str,
    ticker: str,
    company_name: str,
    fiscal_period: str,
) -> ExtractionContract | None:
    """Read a bespoke announcement contract row and materialize an ExtractionContract."""
    res = await conn.execute(
        text("SELECT contract_json FROM announcement_extraction_contracts WHERE doc_type = :dt"),
        {"dt": doc_type},
    )
    row = res.mappings().first()
    if not row:
        return None
    body = row["contract_json"] or {}

    facts = [ExtractionFactRule(**f) for f in body.get("required_facts", [])]
    narratives = [ExtractionNarrativeRule(**n) for n in body.get("required_narratives", [])]
    modules = [GranularNoteModule(**m) for m in body.get("granular_note_modules", [])]

    return ExtractionContract(
        doc_id=doc_id,
        ticker=ticker.upper(),
        company_name=company_name,
        sector=(body.get("sector") or "UNIVERSAL").upper(),
        fiscal_period=fiscal_period.upper(),
        period_type=body.get("period_type", "instant"),
        scaling_rules=body.get("scaling_rules") or _STANDARD_SCALING_RULES,
        required_facts=facts,
        required_narratives=narratives,
        granular_note_modules=modules,
        sector_specific_guidelines=[
            f"Target Issuer: {company_name} ({ticker}) — {doc_type}, Period: {fiscal_period}.",
            *body.get("sector_specific_guidelines", []),
        ],
        do_not_extract=body.get("do_not_extract") or [],
    )


async def build_extraction_contract(
    conn: AsyncConnection,
    *,
    doc_id: str,
    ticker: str,
    company_name: str,
    sector: str,
    fiscal_period: str,
    period_type: str = "duration_ytd",
    doc_type: str | None = None,
) -> ExtractionContract:
    """Build a full extraction contract.

    Routing:
    - If `doc_type` is an announcement class: read the bespoke contract from
      `announcement_extraction_contracts` if present; else return the compiled
      GENERIC_DISCLOSURE safety net.
    - Otherwise (financial docs): query the ontology tables as before.

    Callers must pass an already-open async SQLAlchemy connection so the caller
    controls transaction scope. See services/mcp/server.py for usage.
    """
    if doc_type and doc_type.upper() in ANNOUNCEMENT_DOC_TYPES:
        dt = doc_type.upper()
        bespoke = await _load_announcement_contract_from_db(
            conn,
            doc_type=dt,
            doc_id=doc_id,
            ticker=ticker,
            company_name=company_name,
            fiscal_period=fiscal_period,
        )
        if bespoke is not None:
            return bespoke
        return _build_generic_disclosure_contract(
            doc_id=doc_id,
            ticker=ticker,
            company_name=company_name,
            fiscal_period=fiscal_period,
        )

    sector_upper = (sector or "GENERIC").upper()

    required_facts = await _load_metrics(conn, sector_upper)
    granular_modules = await _load_granular_modules(conn, sector_upper)
    required_narratives = await _load_narrative_rules(conn, sector_upper)

    critical_count = sum(1 for r in required_facts if r.importance == "CRITICAL")
    high_count = sum(1 for r in required_facts if r.importance == "HIGH")

    sector_guidelines = [
        f"Target Issuer: {company_name} ({ticker}) — Sector: {sector_upper}, Period: {fiscal_period}.",
        f"Coverage bar for this sector: {critical_count} CRITICAL metrics (non-negotiable) + {high_count} HIGH-priority metrics.",
        *_UNIVERSAL_GUIDELINES,
    ]

    core_modules: dict[str, RouteQuery] = {}
    for mod in ["BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW", "MDA"]:
        rq = get_route_query(mod, sector_upper)
        if rq:
            core_modules[mod] = rq

    return ExtractionContract(
        doc_id=doc_id,
        ticker=ticker.upper(),
        company_name=company_name,
        sector=sector_upper,
        fiscal_period=fiscal_period.upper(),
        period_type=period_type,
        scaling_rules=_STANDARD_SCALING_RULES,
        required_facts=required_facts,
        required_narratives=required_narratives,
        granular_note_modules=granular_modules,
        core_modules=core_modules,
        sector_specific_guidelines=sector_guidelines,
        do_not_extract=_DO_NOT_EXTRACT,
    )
