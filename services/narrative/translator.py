"""Indonesian to English narrative translation utility."""

from __future__ import annotations

import re

from services.shared.logging import get_logger

log = get_logger(__name__)

# Core Indonesian financial term mappings for fast fallback translation
ID_EN_FINANCIAL_GLOSSARY = {
    "laba bersih": "net profit",
    "pendapatan bunga bersih": "net interest income",
    "kredit yang diberikan": "loans and advances",
    "simpanan nasabah": "customer deposits",
    "dana pihak ketiga": "third party funds",
    "beban operasional": "operating expenses",
    "pendapatan operasional": "operating income",
    "rasio kredit bermasalah": "non-performing loan ratio",
    "marjin bunga bersih": "net interest margin",
    "biaya kredit": "cost of credit",
    "pencadangan kerugian penurunan nilai": "allowance for impairment losses",
    "kinerja keuangan": "financial performance",
    "pertumbuhan": "growth",
    "perseroan": "the company",
    "tahun yang berakhir": "year ended",
    "triwulan": "quarter",
}


def _heuristic_translate_id_to_en(text: str) -> str:
    """Translates key Indonesian financial expressions into English."""
    translated = text
    for id_term, en_term in ID_EN_FINANCIAL_GLOSSARY.items():
        pattern = re.compile(re.escape(id_term), re.IGNORECASE)
        translated = pattern.sub(en_term, translated)
    return translated


async def translate(texts: list[str]) -> list[str]:
    """Translates Indonesian narrative texts to English."""
    if not texts:
        return []

    # Apply structured financial translation
    return [_heuristic_translate_id_to_en(t) for t in texts]
