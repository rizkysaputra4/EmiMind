"""Seed extraction_narrative_rules: which narrative sections the LLM must extract per sector."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text

from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("seed.extraction_narratives")


NARRATIVE_RULES: list[dict[str, Any]] = [
    # -------------- Generic (ALL sectors) --------------
    {
        "topic": "General Corporate Overview",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "expected_section": "MDA",
        "target_note_description": "Catatan 1 (Informasi Umum Perusahaan / General Information)",
        "guideline": (
            "Extract clean prose describing the company's core operations, concession/plantation permits, "
            "subsidiaries, and primary business activities. Skip auditor boilerplate."
        ),
        "expected_link_types": [],
    },
    {
        "topic": "Segment Operations & Revenue Drivers",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "expected_section": "FOOTNOTE",
        "target_note_description": "Catatan Informasi Segmen Operasi / Segment Reporting",
        "guideline": (
            "Extract text explaining product contributions, geographic distribution, and market drivers "
            "for sales changes. Feed the LLM's causal_links extraction from this narrative."
        ),
        "expected_link_types": ["VOLUME_GROWTH", "PRICE_CHANGE"],
    },
    {
        "topic": "Financial Risk & Market Factors",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "expected_section": "RISK",
        "target_note_description": "Catatan Manajemen Risiko Keuangan / Financial Risk Management",
        "guideline": (
            "Extract descriptions of commodity price risks, foreign exchange exposure, and interest rate "
            "policies. Note the currency mix and hedging positions."
        ),
        "expected_link_types": ["MACRO_CURRENCY", "COST_PRESSURE"],
    },
    {
        "topic": "Subsequent Events & Material Commitments",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "expected_section": "MGMT_STMT",
        "target_note_description": "Catatan Peristiwa Setelah Tanggal Pelaporan / Subsequent Events",
        "guideline": (
            "Extract material events, dividend announcements, or capital commitments occurring after "
            "reporting date."
        ),
        "expected_link_types": [],
    },
    {
        "topic": "Management Guidance & Outlook",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "expected_section": "MDA",
        "target_note_description": "Ikhtisar Manajemen / Prospek Usaha / Guidance FY",
        "guideline": (
            "Extract forward-looking guidance ranges (revenue growth, capex, margin targets, dividend "
            "payout) exactly as management stated them. Preserve numeric ranges."
        ),
        "expected_link_types": [],
    },
    # -------------- Sector-specific --------------
    {
        "topic": "Banking Credit Quality & Loan Book",
        "sector_applicability": ["BANK"],
        "importance": "CRITICAL",
        "expected_section": "FOOTNOTE",
        "target_note_description": "Catatan Kualitas Aset Produktif / CKPN PSAK 71",
        "guideline": (
            "Extract narrative on NPL formation, loan restructuring, CKPN methodology (PSAK 71 staging), "
            "and coverage ratio movements. Explain drivers of cost-of-credit changes."
        ),
        "expected_link_types": ["OPERATIONAL_EFFICIENCY", "COST_PRESSURE"],
    },
    {
        "topic": "Commodity Price & Volume Drivers",
        "sector_applicability": ["CPO", "COAL", "NICKEL", "GOLD_COPPER", "OIL_GAS"],
        "importance": "CRITICAL",
        "expected_section": "MDA",
        "target_note_description": "Analisis Kinerja Operasional Komoditas",
        "guideline": (
            "Explicitly capture the LLM-facing causal narrative: weather impact on FFB/coal production, "
            "ASP movements, DMO obligations, smelter downtime, ore-grade changes."
        ),
        "expected_link_types": ["WEATHER_CLIMATE", "PRICE_CHANGE", "VOLUME_GROWTH"],
    },
    {
        "topic": "Property Presales & Landbank Strategy",
        "sector_applicability": ["PROPERTY"],
        "importance": "HIGH",
        "expected_section": "MDA",
        "target_note_description": "Strategi Marketing Sales & Pengembangan Kota Mandiri",
        "guideline": (
            "Extract narrative on presales achievement vs guidance, project launch pipeline, and landbank "
            "monetisation strategy per township."
        ),
        "expected_link_types": ["VOLUME_GROWTH"],
    },
    {
        "topic": "Telco Network Investment & ARPU Dynamics",
        "sector_applicability": ["TELCO", "TOWER"],
        "importance": "HIGH",
        "expected_section": "MDA",
        "target_note_description": "Analisis Trafik Data & Strategi Monetisasi",
        "guideline": (
            "Capture narrative on data traffic growth, ARPU direction (prepaid vs postpaid), tower "
            "colocation strategy, and 5G/fiber rollout progress."
        ),
        "expected_link_types": ["VOLUME_GROWTH", "PRICE_CHANGE"],
    },
    {
        "topic": "Digital Platform Unit Economics",
        "sector_applicability": ["DIGITAL"],
        "importance": "CRITICAL",
        "expected_section": "MDA",
        "target_note_description": "Ikhtisar Kinerja Segmen (On-Demand / E-commerce / Fintech)",
        "guideline": (
            "Extract narrative on contribution margin trajectory, promotional-incentive discipline, "
            "cohort behaviour, and path to adjusted EBITDA breakeven per segment."
        ),
        "expected_link_types": ["OPERATIONAL_EFFICIENCY"],
    },
]


async def seed_extraction_narratives() -> None:
    pool = create_pool()
    async with pool.connect() as conn:
        for rule in NARRATIVE_RULES:
            await conn.execute(
                text(
                    """
                    INSERT INTO extraction_narrative_rules (
                        topic, sector_applicability, importance, expected_section,
                        target_note_description, guideline, expected_link_types
                    ) VALUES (
                        :topic, :sector_applicability, :importance, :expected_section,
                        :target_note_description, :guideline, :expected_link_types
                    )
                    ON CONFLICT (topic) DO UPDATE SET
                        sector_applicability   = EXCLUDED.sector_applicability,
                        importance             = EXCLUDED.importance,
                        expected_section       = EXCLUDED.expected_section,
                        target_note_description = EXCLUDED.target_note_description,
                        guideline              = EXCLUDED.guideline,
                        expected_link_types    = EXCLUDED.expected_link_types;
                    """
                ),
                rule,
            )
        await conn.commit()

        count = (await conn.execute(text("SELECT count(*) FROM extraction_narrative_rules"))).scalar()
        print("=== NARRATIVE RULES SEEDING COMPLETE ===")
        print(f"Total narrative rules in DB: {count}")

    await pool.dispose()


if __name__ == "__main__":
    asyncio.run(seed_extraction_narratives())
