"""Regex-based classifier that maps an IDX announcement title to a doc_type.

Loads rules from `announcement_class_rules` at process start (cached) and
returns the highest-priority match, or GENERIC_DISCLOSURE if nothing matches.

Design: [docs/PENGUMUMAN_EXTRACTION_DESIGN.md §5](../../docs/PENGUMUMAN_EXTRACTION_DESIGN.md).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

GENERIC_FALLBACK_DOC_TYPE = "GENERIC_DISCLOSURE"


@dataclass(frozen=True)
class CompiledRule:
    pattern: re.Pattern[str]
    doc_type: str
    priority: int


@dataclass(frozen=True)
class ClassificationResult:
    doc_type: str
    source: str  # 'regex' | 'fallback'
    confidence: float  # 1.0 for regex hit, 0.0 for fallback
    matched_pattern: str | None = None


_RULE_CACHE: list[CompiledRule] | None = None


async def load_rules(conn: AsyncConnection, *, force_reload: bool = False) -> list[CompiledRule]:
    """Load active rules ordered by priority ascending (lower = higher precedence)."""
    global _RULE_CACHE
    if _RULE_CACHE is not None and not force_reload:
        return _RULE_CACHE

    res = await conn.execute(
        text(
            """
            SELECT pattern, doc_type, priority
            FROM announcement_class_rules
            WHERE is_active
            ORDER BY priority ASC, id ASC
            """
        )
    )
    compiled: list[CompiledRule] = []
    for row in res.mappings():
        try:
            pat = re.compile(row["pattern"])
        except re.error:
            # A broken rule shouldn't kill the classifier — log and skip.
            continue
        compiled.append(
            CompiledRule(pattern=pat, doc_type=row["doc_type"], priority=row["priority"])
        )
    _RULE_CACHE = compiled
    return compiled


def classify_with_rules(
    text_inputs: Iterable[str], rules: list[CompiledRule]
) -> ClassificationResult:
    """Given one or more strings (title, filename, subject), return the first-priority match."""
    haystack = " || ".join(s for s in text_inputs if s)
    for rule in rules:
        if rule.pattern.search(haystack):
            return ClassificationResult(
                doc_type=rule.doc_type,
                source="regex",
                confidence=1.0,
                matched_pattern=rule.pattern.pattern,
            )
    return ClassificationResult(
        doc_type=GENERIC_FALLBACK_DOC_TYPE, source="fallback", confidence=0.0
    )


async def classify(
    conn: AsyncConnection,
    *,
    title: str | None = None,
    filename: str | None = None,
    subject: str | None = None,
) -> ClassificationResult:
    """One-shot: load rules if needed and classify against provided text inputs."""
    rules = await load_rules(conn)
    texts = [t for t in (title, filename, subject) if t]
    return classify_with_rules(texts, rules)


def reset_cache() -> None:
    """Test hook to force a rule reload."""
    global _RULE_CACHE
    _RULE_CACHE = None
