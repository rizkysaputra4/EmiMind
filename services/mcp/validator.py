"""Multi-tier accounting validation and actionable feedback generator for EMIMIND MCP Server.

The validator is pure (no DB access). Its callers load page evidence, metric definitions and
cross-issuer narrative hashes and pass them in. Without page evidence nothing is validated:
the report is INVALID with ``DOCUMENT_NOT_INDEXED``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from services.mcp.fact_semantics import (
    BUILTIN_CONCEPTS,
    check_concept_label,
    find_metric_mentions,
    label_is_segment_member,
    metric_search_terms,
    resolve_period_type,
    segment_strings,
)
from services.mcp.grounding import (
    GroundingOutcome,
    dominant_scale,
    ground_fact,
    scale_from_rules,
)
from services.mcp.narrative_checks import (
    boilerplate_match,
    is_verbatim,
    issuer_anchor,
    load_boilerplate,
    narrative_md5,
    normalize_for_match,
    normalize_narrative_text,
)
from services.mcp.periods import normalize_period, period_end_for
from services.mcp.types import (
    ConceptDefinition,
    DraftSubmissionPayload,
    ExtractedFactItem,
    ExtractionContract,
    ExtractionCoverage,
    ExtractionFactRule,
    IssueSeverity,
    PageEvidence,
    ValidationIssue,
    ValidationReport,
)

__all__ = [
    "CONCEPT_ALIASES",
    "fact_identity",
    "load_narrative_boilerplate_hashes",
    "load_tie_out_rules",
    "narrative_md5",
    "normalize_narrative_text",
    "resolve_payload_period_end",
    "validate_draft_submission",
]

# Common concept ID aliases mapping (case-insensitive)
CONCEPT_ALIASES: dict[str, str] = {
    "idx:cpoproduction": "idx:CPOProductionVolume",
    "idx:cpoproductionvolume": "idx:CPOProductionVolume",
    "idx:ffbproduction": "idx:FfbProduction",
    "idx:matureplantedarea": "idx:MaturePlantedArea",
    "idx:oilextractionrate": "idx:OilExtractionRate",
    "idx:oer": "idx:OilExtractionRate",
    "idx:palmkernelproduction": "idx:PalmKernelProduction",
    "idx:cpoaveragepriceasp": "idx:CPOAveragePriceASP",
    "idx:cpocashcostperkg": "idx:CPOCashCostPerKg",
    "idx:coalproductionvolume": "idx:CoalProductionVolume",
    "idx:coalaveragepriceasp": "idx:CoalAveragePriceASP",
    "idx:calcashcostperton": "idx:CoalCashCostPerTon",
    "idx:nickeloreproduction": "idx:NickelOreProduction",
    "idx:ferronickeloutput": "idx:FerroNickelOutput",
    "idx:sharesoutstanding": "idx:SharesOutstanding",
    "idx:dividendpershare": "idx:DividendPerShare",
    "ifrs:cashflowsfromoperatingactivities": "ifrs:CashFlowsFromUsedInOperatingActivities",
    "ifrs:cashflowsfromusedinoperatingactivities": "ifrs:CashFlowsFromUsedInOperatingActivities",
}

PLACEHOLDER_SEGMENT_LABELS: set[str] = {
    "primary operations",
    "other operations",
    "operasi utama",
    "operasi lainnya",
}

ONLY_CHILD_PLACEHOLDER_LABELS: set[str] = {
    "lainnya",
    "others",
    "other",
    "lain lain",
}

# A child share within this many percentage points of a multiple of 5% counts as "round".
ROUND_FRACTION_TOLERANCE_PP = Decimal("0.5")

_GROUNDED_KINDS = ("cell", "text")
ERROR = IssueSeverity.ERROR
WARNING = IssueSeverity.WARNING


def _normalize_concept(cid: str) -> str:
    """Returns canonical concept ID if alias exists, otherwise returns original."""
    return CONCEPT_ALIASES.get(cid.lower(), cid)


def resolve_payload_period_end(fiscal_period: str) -> date | None:
    """period_end of a payload period ('2025Q3', '2025FY', '2025H1'); None when unparseable."""
    try:
        return period_end_for(fiscal_period)
    except ValueError:
        pass
    try:
        return period_end_for(normalize_period(fiscal_period))
    except ValueError:
        return None


def fact_identity(f: ExtractedFactItem, period_type: str | None) -> tuple[str, str, str]:
    """The DB identity of a fact within one (ticker, fiscal_period): concept, period type, segment."""
    seg = json.dumps(f.segment, sort_keys=True, default=str) if f.segment else "{}"
    return (_normalize_concept(f.concept_id), period_type or "", seg)


def _is_round_fraction(child_val: Decimal, parent_val: Decimal) -> bool:
    """Is the child share within ±0.5 pp of a multiple of 5% (strictly between 0 and 100)?"""
    if parent_val == 0:
        return False
    pct = (child_val / parent_val) * Decimal(100)
    nearest = (pct / 5).to_integral_value() * 5
    return 0 < nearest < 100 and abs(pct - nearest) <= ROUND_FRACTION_TOLERANCE_PP


_TIE_OUT_RULES: list[dict[str, Any]] | None = None


def load_tie_out_rules() -> list[dict[str, Any]]:
    """Loads and caches cross-statement tie-out rules from db/seeds/tie_out_rules.yaml."""
    global _TIE_OUT_RULES
    if _TIE_OUT_RULES is None:
        yaml_path = Path(__file__).resolve().parents[2] / "db" / "seeds" / "tie_out_rules.yaml"
        if not yaml_path.is_file():
            yaml_path = Path("db/seeds/tie_out_rules.yaml").resolve()
        if yaml_path.is_file():
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                _TIE_OUT_RULES = data.get("rules", [])
        else:
            _TIE_OUT_RULES = []
    return _TIE_OUT_RULES


def load_narrative_boilerplate_hashes() -> set[str]:
    """MD5 hashes of the boilerplate list (kept for callers of the old API)."""
    return load_boilerplate()[0]


def _hint_search_pages(rule: ExtractionFactRule, contract: ExtractionContract) -> list[str]:
    """Collect human-readable search hints for a metric from both the metric rule and any
    granular note module whose target_concepts includes the metric."""
    hints: list[str] = []
    if rule.search_hints:
        hints.extend(rule.search_hints)
    for module in contract.granular_note_modules:
        if (
            rule.concept_id in module.target_concepts
            or _normalize_concept(rule.concept_id) in module.target_concepts
        ):
            hint = f"'{module.typical_note_title}' ({module.name})"
            if hint not in hints:
                hints.append(hint)
    if rule.synonyms_id or rule.synonyms_en:
        synonyms = ", ".join([*rule.synonyms_id[:4], *rule.synonyms_en[:2]])
        if synonyms:
            hints.append(f"synonyms: {synonyms}")
    return hints


def _metric_is_ratio(
    rule: ExtractionFactRule, cdef: ConceptDefinition | None = None
) -> bool | None:
    """True for percent/ratio metrics, False for monetary ones, None when neither (volumes...).

    The ontology definition wins over the contract rule (whose unit defaults to IDR)."""
    unit = ((cdef.unit if cdef else None) or rule.unit or "").upper()
    vtype = ((cdef.value_type if cdef else None) or rule.value_type or "").upper()
    if unit in ("PERCENT", "PERCENTAGE", "RATIO", "%") or vtype in ("PERCENTAGE", "RATIO"):
        return True
    if vtype == "MONETARY" or unit.startswith(("IDR", "USD")):
        return False
    return None


def _pages_overlap(
    rule: ExtractionFactRule, searched_pages: list[int], contract: ExtractionContract
) -> bool:
    """A perfunctory search scope (< 2 pages) is rejected. Whether the metric is really absent
    is verified separately against every indexed page (OMISSION_CONTRADICTED)."""
    return len(searched_pages) >= 2


def _issue(
    severity: IssueSeverity,
    category: str,
    message: str,
    pages: Iterable[int | None] = (),
    *,
    concept_id: str | None = None,
    details: dict[str, Any] | None = None,
    equation: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        category=category,
        concept_id=concept_id,
        equation=equation,
        details=details or {},
        feedback_message=message,
        target_pages=sorted({p for p in pages if p is not None}),
    )


def _sev(level: str) -> IssueSeverity:
    return IssueSeverity(level) if level in IssueSeverity.__members__ else IssueSeverity.ERROR


def _segment_signature(seg: dict[str, Any]) -> str:
    """Children belong to the same breakdown when they share the same set of (string) segment
    keys and the same declared dimension; numeric annotations such as pct_total are ignored."""
    keys = sorted(k for k, v in seg.items() if isinstance(v, (str, list)))
    dim = seg.get("type") or seg.get("dimension") or ""
    return f"{'+'.join(keys)}|{dim}"


def validate_draft_submission(
    payload: DraftSubmissionPayload,
    *,
    contract: ExtractionContract,
    sector: str = "GENERIC",
    evidence: dict[int, PageEvidence] | None = None,
    page_count: int | None = None,
    retry_attempt: int = 1,
    previous_attempt_misses: list[str] | None = None,
    cross_issuer_narrative_hashes: dict[str, str] | None = None,
    concept_defs: dict[str, ConceptDefinition] | None = None,
    document_text: dict[int, str] | None = None,
) -> ValidationReport:
    """Performs multi-tier validation of a draft extraction payload.

    Args:
        evidence: page evidence for every cited page. ``None`` means the document is not
            indexed (or evidence could not be loaded): the report is INVALID.
        concept_defs: metric_definitions rows for the payload's concepts (by metric_id). When
            given, concept<->label and flow/stock checks run; unknown concepts get a WARNING.
        document_text: text of EVERY indexed page, used to verify omissions. Falls back to the
            cited-page evidence when not supplied.

    Callers must build the contract via services.mcp.contracts.build_extraction_contract.
    """
    submission_id = f"sub_{uuid.uuid4().hex[:8]}"
    issues: list[ValidationIssue] = []
    add = issues.append

    period_end = resolve_payload_period_end(payload.fiscal_period)
    if period_end is None:
        add(
            _issue(
                ERROR,
                "SCHEMA",
                f"fiscal_period '{payload.fiscal_period}' is not a valid period (expected e.g. "
                f"'2025Q3'); column/period checks cannot run.",
            )
        )

    if evidence is None:
        add(
            _issue(
                ERROR,
                "DOCUMENT_NOT_INDEXED",
                f"Document {payload.doc_id} has no page index (document_pages) or its page evidence "
                f"could not be loaded, so no fact, omission or narrative can be verified. Index the "
                f"document first (index_pages), then re-submit.",
            )
        )

    def cdef_for(cid: str) -> ConceptDefinition | None:
        norm = _normalize_concept(cid)
        if concept_defs is not None:
            found = concept_defs.get(cid) or concept_defs.get(norm)
            if found is not None:
                return found
        return BUILTIN_CONCEPTS.get(norm) or BUILTIN_CONCEPTS.get(cid)

    # -------------------------------------------------------------
    # LEVEL 1: Schema, period types, concept semantics, identity
    # -------------------------------------------------------------
    valid_statements = {"BS", "IS", "CF", "EQ", "NOTE"}
    resolved_pt: dict[int, str | None] = {}
    seen_identity: dict[tuple[str, str, str], int] = {}
    for idx, f in enumerate(payload.facts):
        pages = [f.source_page]
        if not f.statement or f.statement not in valid_statements:
            add(
                _issue(
                    ERROR,
                    "SCHEMA",
                    f"Fact '{f.concept_id}' missing required 'statement'. "
                    f"Expected one of: {sorted(valid_statements)}.",
                    pages,
                    concept_id=f.concept_id,
                )
            )

        cdef = cdef_for(f.concept_id)
        verdict = resolve_period_type(f, cdef)
        resolved_pt[idx] = verdict.resolved
        if verdict.category:
            add(_issue(ERROR, verdict.category, verdict.message, pages, concept_id=f.concept_id))

        label = (f.source_label_original or "").strip()
        if not label:
            add(
                _issue(
                    ERROR,
                    "SCHEMA",
                    f"Fact '{f.concept_id}' has no 'source_label_original'. Give the row label exactly "
                    f"as printed next to the number (prefix the section header for sub-rows).",
                    pages,
                    concept_id=f.concept_id,
                )
            )
        elif concept_defs is not None:
            if cdef is None:
                add(
                    _issue(
                        WARNING,
                        "CONCEPT_NOT_IN_ONTOLOGY",
                        f"Concept '{f.concept_id}' is not in metric_definitions; its label and "
                        f"flow/stock type cannot be checked. Prefer an ontology concept, or propose "
                        f"it via submit_discovered_metric.",
                        pages,
                        concept_id=f.concept_id,
                    )
                )
            else:
                seg_words = segment_strings(f.segment)
                cl_verdict = check_concept_label(label, cdef, seg_words)
                if not cl_verdict.ok and not (
                    f.segment and label_is_segment_member(label, seg_words)
                ):
                    add(
                        _issue(
                            ERROR,
                            "CONCEPT_LABEL_MISMATCH",
                            f"Fact '{f.concept_id}' has label '{label}', which does not denote this "
                            f"concept: {cl_verdict.reason}. Pick the concept that matches the printed line, or "
                            f"cite the line that is this concept.",
                            pages,
                            concept_id=f.concept_id,
                        )
                    )

        key = fact_identity(f, verdict.resolved)
        if key in seen_identity:
            first = payload.facts[seen_identity[key]]
            add(
                _issue(
                    ERROR,
                    "DUPLICATE_FACT",
                    f"Fact '{f.concept_id}' (period_type {verdict.resolved}, segment "
                    f"{f.segment or '{}'}) appears twice in this payload (p.{first.source_page} "
                    f"value {first.value_numeric:,} and p.{f.source_page} value "
                    f"{f.value_numeric:,}). One identity may be submitted once; drop the duplicate or "
                    f"distinguish it with a segment.",
                    [first.source_page, f.source_page],
                    concept_id=f.concept_id,
                )
            )
        else:
            seen_identity[key] = idx

    # Concept lookups (first unsegmented fact per concept wins; any fact counts as present)
    all_facts_by_concept: dict[str, ExtractedFactItem] = {}
    unsegmented_facts_by_concept: dict[str, ExtractedFactItem] = {}
    for f in payload.facts:
        norm_cid = _normalize_concept(f.concept_id)
        all_facts_by_concept.setdefault(norm_cid, f)
        all_facts_by_concept.setdefault(f.concept_id, f)
        if not f.segment:
            unsegmented_facts_by_concept.setdefault(norm_cid, f)
            unsegmented_facts_by_concept.setdefault(f.concept_id, f)
    facts_by_concept: dict[str, ExtractedFactItem] = {
        **all_facts_by_concept,
        **unsegmented_facts_by_concept,
    }

    # -------------------------------------------------------------
    # Coverage and omissions
    # -------------------------------------------------------------
    omitted_by_concept = {}
    for item in payload.omitted_kpis:
        omitted_by_concept[_normalize_concept(item.metric_id)] = item
        omitted_by_concept[item.metric_id] = item

    search_pages: dict[int, str] = (
        document_text
        if document_text is not None
        else {p: ev.page_text for p, ev in (evidence or {}).items()}
    )

    coverage = ExtractionCoverage()
    bucket_map = {
        "CRITICAL": coverage.critical,
        "HIGH": coverage.high,
        "OPTIONAL": coverage.optional,
    }

    for rule in contract.required_facts:
        # Only EXTRACTED_RAW metrics count toward extraction coverage.
        if rule.extraction_mode != "EXTRACTED_RAW":
            continue

        bucket = bucket_map.get(rule.importance.upper(), coverage.high)
        bucket.expected += 1

        norm_rule_id = _normalize_concept(rule.concept_id)
        is_present_in_facts = (rule.concept_id in facts_by_concept) or (
            norm_rule_id in facts_by_concept
        )
        is_declared_omitted = (rule.concept_id in omitted_by_concept) or (
            norm_rule_id in omitted_by_concept
        )

        if is_present_in_facts:
            bucket.found += 1
            continue

        if not rule.required:
            continue

        hints = _hint_search_pages(rule, contract)
        hints_str = "; ".join(hints) if hints else "(no additional hints)"
        if not is_declared_omitted:
            is_critical = rule.importance == "CRITICAL"
            severity_label = "CRITICAL" if is_critical else "HIGH-priority"
            add(
                _issue(
                    ERROR if is_critical else WARNING,
                    "MISSING_MANDATORY_METRIC_OR_EXPLANATION",
                    f"Missing {severity_label} metric '{rule.label}' ({rule.concept_id}). "
                    f"Typical locations: {hints_str}. "
                    f"Extract it into 'facts' with source_page; or, if truly not disclosed, add to "
                    f"'omitted_kpis' with 'reason', a 15+ char 'explanation', and "
                    f"'search_pages_checked' proving you looked at the hinted locations.",
                    concept_id=rule.concept_id,
                )
            )
            bucket.missing.append(rule.concept_id)
            continue

        omitted_item = omitted_by_concept.get(norm_rule_id) or omitted_by_concept[rule.concept_id]
        expl_lower = omitted_item.explanation.lower()
        checked = omitted_item.search_pages_checked
        out_of_range = [p for p in checked if p < 1 or (page_count is not None and p > page_count)]
        omission_error: ValidationIssue | None = None
        if len(omitted_item.explanation.strip()) < 15:
            omission_error = _issue(
                ERROR,
                "INSUFFICIENT_OMISSION_EXPLANATION",
                f"Omission explanation for '{rule.label}' ({rule.concept_id}) is too brief "
                f"('{omitted_item.explanation}'). Please provide a substantive explanation, and "
                f"re-check these locations first: {hints_str}.",
                checked,
                concept_id=rule.concept_id,
            )
        elif not checked:
            omission_error = _issue(
                ERROR,
                "MISSING_SEARCH_PAGES_AUDIT",
                f"Omission entry for '{rule.label}' ({rule.concept_id}) must specify "
                f"'search_pages_checked' as a list of page numbers you searched. "
                f"Typical locations for this metric: {hints_str}.",
                concept_id=rule.concept_id,
            )
        elif out_of_range:
            omission_error = _issue(
                ERROR,
                "PROVENANCE",
                f"Omission for '{rule.label}' ({rule.concept_id}) claims pages {out_of_range[:10]} "
                f"were searched, which are outside the document (valid: 1..{page_count}).",
                concept_id=rule.concept_id,
            )
        elif any(
            kw in expl_lower
            for kw in [
                "disclosed in md&a",
                "in md&a",
                "in highlights",
                "disclosed in highlights",
                "is reported in",
                "available on page",
            ]
        ):
            omission_error = _issue(
                ERROR,
                "CONTRADICTORY_OMISSION",
                f"Contradictory Omission for '{rule.label}' ({rule.concept_id}): the explanation "
                f"says the metric is disclosed ('{omitted_item.explanation}'). Any metric found in "
                f"the report — including MD&A / Operational Highlights — MUST be extracted into "
                f"the 'facts' array with exact value, unit, and source_page, NOT declared in "
                f"omitted_kpis. Re-extract from: {hints_str}.",
                checked,
                concept_id=rule.concept_id,
            )
        elif hints and not _pages_overlap(rule, checked, contract):
            omission_error = _issue(
                ERROR,
                "INSUFFICIENT_SEARCH_SCOPE",
                f"Omission for '{rule.label}' ({rule.concept_id}) claims pages {checked} were "
                f"searched, but none of the typical locations for this metric were checked. "
                f"Search these first: {hints_str}.",
                checked,
                concept_id=rule.concept_id,
            )
        else:
            names = [rule.label, *rule.synonyms_id, *rule.synonyms_en]
            terms = metric_search_terms(cdef_for(rule.concept_id), names)
            mentions = (
                find_metric_mentions(
                    terms,
                    search_pages,
                    want_percent=_metric_is_ratio(rule, cdef_for(rule.concept_id)),
                )
                if terms
                else []
            )
            if mentions:
                shown = "; ".join(f"p.{m.page}: '{m.line}'" for m in mentions[:3])
                omission_error = _issue(
                    ERROR,
                    "OMISSION_CONTRADICTED",
                    f"Omission for '{rule.label}' ({rule.concept_id}) is contradicted by the document: "
                    f"its caption appears next to a reported number on page(s) "
                    f"{sorted({m.page for m in mentions})} ({shown}). Extract the value from there "
                    f"instead of declaring it not disclosed.",
                    [m.page for m in mentions],
                    concept_id=rule.concept_id,
                    details={"pages": sorted({m.page for m in mentions})},
                )
        if omission_error is not None:
            add(omission_error)
            bucket.missing.append(rule.concept_id)
        else:
            bucket.omitted_with_justification += 1

    # Check Granular Segment Breakdown Requirement for Revenue
    if "ifrs:Revenue" in facts_by_concept:
        segmented_rev = [
            f for f in payload.facts if f.concept_id == "ifrs:Revenue" and f.segment is not None
        ]
        if (
            not segmented_rev
            and "REVENUE_BREAKDOWN" not in omitted_by_concept
            and "ifrs:Revenue_SEGMENTS" not in omitted_by_concept
        ):
            add(
                _issue(
                    WARNING,
                    "MISSING_GRANULAR_REVENUE_BREAKDOWN",
                    "Revenue was submitted only as an unsegmented total. Extract the product line / "
                    "division breakdown from the 'Segment Information' note as ExtractedFactItems "
                    "with segment={'segment': '<Product/Service>', 'type': 'product'}. If the issuer "
                    "operates in a single line with no breakdown, declare this in 'omitted_kpis'.",
                    [facts_by_concept["ifrs:Revenue"].source_page],
                    concept_id="ifrs:Revenue",
                )
            )

    # -------------------------------------------------------------
    # Provenance + grounding (one scale, right row, right column)
    # -------------------------------------------------------------
    doc_scale = dominant_scale(evidence) if evidence else None
    contract_scale = scale_from_rules(getattr(contract, "scaling_rules", None))
    outcomes: dict[int, GroundingOutcome] = {}

    for idx, f in enumerate(payload.facts):
        if f.segment and (f.source_page is None or f.source_page <= 0):
            add(
                _issue(
                    ERROR,
                    "SEGMENT_PROVENANCE",
                    f"Segmented fact '{f.concept_id}' must cite its own disclosure note source_page "
                    f"(got {f.source_page}).",
                    concept_id=f.concept_id,
                )
            )
            continue
        if (
            f.source_page is None
            or f.source_page < 1
            or (page_count is not None and f.source_page > page_count)
        ):
            add(
                _issue(
                    ERROR,
                    "PROVENANCE",
                    f"Fact '{f.concept_id}' source_page {f.source_page} is out of document bounds "
                    f"(valid: 1..{page_count or 'N/A'}).",
                    [f.source_page],
                    concept_id=f.concept_id,
                )
            )
            continue
        if evidence is None:
            continue
        if f.source_page not in evidence:
            add(
                _issue(
                    ERROR,
                    "PROVENANCE",
                    f"Fact '{f.concept_id}' cites source_page {f.source_page}, which is not in the "
                    f"document's page index.",
                    [f.source_page],
                    concept_id=f.concept_id,
                )
            )
            continue
        out = ground_fact(
            f,
            evidence[f.source_page],
            period_end=period_end,
            doc_scale=doc_scale,
            contract_scale=contract_scale,
        )
        outcomes[idx] = out
        for sev, cat, msg in out.issues:
            details = {"needs_review": True} if cat == "GROUNDING_OCR" else {}
            add(
                _issue(
                    _sev(sev),
                    cat,
                    msg,
                    [f.source_page],
                    concept_id=f.concept_id,
                    details=details,
                )
            )

    def grounded(idx: int) -> bool:
        o = outcomes.get(idx)
        return o is not None and o.ok and o.kind in _GROUNDED_KINDS

    # -------------------------------------------------------------
    # Anti-synthetic rules: SYNTHETIC_LABEL and SYNTHETIC_SPLIT
    # -------------------------------------------------------------
    by_concept_pt: dict[tuple[str, str | None], list[int]] = {}
    for idx, f in enumerate(payload.facts):
        by_concept_pt.setdefault((_normalize_concept(f.concept_id), resolved_pt[idx]), []).append(
            idx
        )

    for (cid, _pt), idxs in by_concept_pt.items():
        children = [i for i in idxs if payload.facts[i].segment]
        unsegmented = [i for i in idxs if not payload.facts[i].segment]

        for ci in children:
            child = payload.facts[ci]
            labels = [normalize_for_match(s) for s in segment_strings(child.segment)]
            placeholder = next((lb for lb in labels if lb in PLACEHOLDER_SEGMENT_LABELS), None)
            if placeholder is None and len(children) == 1:
                placeholder = next(
                    (lb for lb in labels if lb in ONLY_CHILD_PLACEHOLDER_LABELS), None
                )
            if placeholder is None:
                continue
            row_label = normalize_for_match(child.source_label_original or "")
            if grounded(ci) and placeholder in row_label:
                continue  # the placeholder is the printed row label next to the grounded number
            add(
                _issue(
                    ERROR,
                    "SYNTHETIC_LABEL",
                    f"Placeholder segment label '{placeholder}' on '{cid}' is rejected unless it is the "
                    f"printed row label next to the grounded number on source page {child.source_page}.",
                    [child.source_page],
                    concept_id=cid,
                )
            )

        if len(children) >= 2:
            parent_val = (
                payload.facts[unsegmented[0]].value_numeric
                if unsegmented
                else sum((payload.facts[c].value_numeric for c in children), Decimal(0))
            )
            if parent_val != 0 and all(
                _is_round_fraction(payload.facts[c].value_numeric, parent_val) for c in children
            ):
                ungrounded = [c for c in children if not grounded(c)]
                if ungrounded:
                    add(
                        _issue(
                            ERROR,
                            "SYNTHETIC_SPLIT",
                            f"Breakdown for concept '{cid}' rejected as synthetic split: all "
                            f"{len(children)} children are round multiples of 5% (±0.5 pp) of the total "
                            f"({parent_val:,.0f}) and {len(ungrounded)} of them are not grounded in page "
                            f"evidence. Every child of a round split must be cell- or text-grounded.",
                            [payload.facts[c].source_page for c in children],
                            concept_id=cid,
                        )
                    )

    # -------------------------------------------------------------
    # Narratives, guidance and causal links: verbatim quotes on the cited page
    # -------------------------------------------------------------
    segment_names = sorted(
        {s for f in payload.facts for s in segment_strings(f.segment) if len(s) >= 3}
    )
    seen_narratives: set[str] = set()

    def page_text_for(page: int, what: str) -> str | None:
        if page < 1 or (page_count is not None and page > page_count):
            add(
                _issue(
                    ERROR,
                    "PROVENANCE",
                    f"{what} source_page {page} is out of document bounds "
                    f"(valid: 1..{page_count or 'N/A'}).",
                    [page],
                )
            )
            return None
        if evidence is None:
            return None
        if page not in evidence:
            add(
                _issue(
                    ERROR,
                    "PROVENANCE",
                    f"{what} cites source_page {page}, which is not in the document's page index.",
                    [page],
                )
            )
            return None
        return evidence[page].page_text

    for n in payload.narratives:
        page_text = page_text_for(n.source_page, "Narrative")
        snippet = n.text_original[:80]
        n_hash = narrative_md5(n.text_original)

        bp = boilerplate_match(n.text_original)
        if bp is not None:
            add(
                _issue(
                    ERROR,
                    "NARRATIVE_BOILERPLATE",
                    f"Narrative chunk on page {n.source_page} matches known boilerplate / disclaimer "
                    f"text: '{snippet}...'.",
                    [n.source_page],
                )
            )

        if page_text is not None:
            ok, score = is_verbatim(n.text_original, page_text)
            if not ok:
                add(
                    _issue(
                        ERROR,
                        "NARRATIVE_NOT_VERBATIM",
                        f"Narrative chunk cited on page {n.source_page} is not a verbatim quote of that "
                        f"page (best match {score:.0f}/100, need ≥90): '{snippet}...'. text_original "
                        f"must be copied from the page; put any translation in text_en.",
                        [n.source_page],
                        details={"match_score": round(score, 1)},
                    )
                )

        if n_hash in seen_narratives:
            add(
                _issue(
                    WARNING,
                    "NARRATIVE_DUPLICATE_IN_PAYLOAD",
                    f"Narrative chunk on page {n.source_page} is repeated in this payload; it will be "
                    f"stored once.",
                    [n.source_page],
                )
            )
        seen_narratives.add(n_hash)

        if cross_issuer_narrative_hashes and n_hash in cross_issuer_narrative_hashes:
            committed_ticker = cross_issuer_narrative_hashes[n_hash]
            if committed_ticker != payload.ticker.upper():
                add(
                    _issue(
                        ERROR,
                        "NARRATIVE_DUPLICATE",
                        f"Narrative chunk on page {n.source_page} duplicates committed narrative from "
                        f"different issuer '{committed_ticker}'.",
                        [n.source_page],
                    )
                )

        if n.section.upper() == "MDA":
            anchor = issuer_anchor(n.text_original, page_text or "", segment_names)
            if anchor is None:
                add(
                    _issue(
                        ERROR,
                        "NARRATIVE_GENERIC",
                        f"MD&A narrative chunk on page {n.source_page} lacks any issuer anchor that also "
                        f"appears on the cited page (a reported number, a named segment/product, or a "
                        f"proper name): '{snippet}...'.",
                        [n.source_page],
                    )
                )

    for g in payload.guidance:
        page_text = page_text_for(g.source_page, f"Guidance '{g.metric}'")
        if page_text is not None and g.context_statement:
            ok, score = is_verbatim(g.context_statement, page_text)
            if not ok:
                add(
                    _issue(
                        ERROR,
                        "GUIDANCE_NOT_VERBATIM",
                        f"Guidance '{g.metric}' context_statement is not a verbatim quote of page "
                        f"{g.source_page} (best match {score:.0f}/100, need ≥90).",
                        [g.source_page],
                    )
                )

    for link in payload.causal_links:
        page_text_for(link.source_page, f"Causal link for '{link.metric_affected}'")

    # -------------------------------------------------------------
    # LEVEL 2: Accounting Math Equations & Tie-Outs
    # -------------------------------------------------------------
    unit_tol = contract_scale if contract_scale is not None else Decimal(1)

    # 1. Segment sum-to-parent (SUM_MISMATCH), per concept + period type + breakdown signature
    for (cid, _pt), idxs in by_concept_pt.items():
        child_facts = [payload.facts[i] for i in idxs if payload.facts[i].segment]
        parent_facts = [payload.facts[i] for i in idxs if not payload.facts[i].segment]
        if not child_facts or not parent_facts:
            continue
        parent_fact = parent_facts[0]
        parent_val = parent_fact.value_numeric

        groups: dict[str, list[ExtractedFactItem]] = {}
        for child_fact in child_facts:
            groups.setdefault(_segment_signature(child_fact.segment or {}), []).append(child_fact)

        for dim, dim_children in groups.items():
            dim_sum = sum((c.value_numeric for c in dim_children), Decimal(0))
            tol = max(unit_tol, Decimal("0.001") * abs(parent_val))
            diff = dim_sum - parent_val
            if abs(diff) > tol:
                child_pages = sorted({c.source_page for c in dim_children if c.source_page})
                add(
                    _issue(
                        ERROR,
                        "SUM_MISMATCH",
                        f"Children of '{cid}' for segment dimension '{dim}' sum to {dim_sum:,.0f} IDR, "
                        f"which does not match parent total ({parent_val:,.0f} IDR from "
                        f"p.{parent_fact.source_page}). Difference: {diff:+,.0f} IDR (tolerance: "
                        f"{tol:,.0f} IDR). Please re-check the breakdown rows on pages {child_pages}.",
                        [*child_pages, parent_fact.source_page],
                        concept_id=cid,
                        details={
                            "parent_value": float(parent_val),
                            "children_sum": float(dim_sum),
                            "discrepancy": float(diff),
                            "dimension": dim,
                        },
                    )
                )

    # 2. Cross-statement tie-outs from YAML, regardless of the submitted `statement` label
    for to_rule in load_tie_out_rules():
        src_cid = _normalize_concept(to_rule["source_concept"])
        tgt_cid = _normalize_concept(to_rule["target_concept"])
        if src_cid == tgt_cid:
            continue  # same concept twice is a DUPLICATE_FACT, checked above
        src_fact = unsegmented_facts_by_concept.get(src_cid)
        tgt_fact = unsegmented_facts_by_concept.get(tgt_cid)
        if src_fact is None or tgt_fact is None:
            continue
        tol = max(
            unit_tol,
            Decimal("0.001") * max(abs(src_fact.value_numeric), abs(tgt_fact.value_numeric)),
        )
        diff = src_fact.value_numeric - tgt_fact.value_numeric
        if abs(diff) > tol:
            add(
                _issue(
                    ERROR,
                    "TIE_OUT",
                    f"Cross-statement tie-out failure ({to_rule.get('name', to_rule.get('id'))}): "
                    f"'{src_fact.concept_id}' ({src_fact.statement or 'NOTE'}, "
                    f"{src_fact.value_numeric:,.0f} IDR from p.{src_fact.source_page}) does not match "
                    f"'{tgt_fact.concept_id}' ({tgt_fact.statement or 'BS'}, "
                    f"{tgt_fact.value_numeric:,.0f} IDR from p.{tgt_fact.source_page}). "
                    f"Difference: {diff:+,.0f} IDR. Check you used the current-period column.",
                    [src_fact.source_page, tgt_fact.source_page],
                    concept_id=src_fact.concept_id,
                    details={
                        "rule": to_rule.get("id"),
                        "source_concept": src_fact.concept_id,
                        "source_value": float(src_fact.value_numeric),
                        "target_concept": tgt_fact.concept_id,
                        "target_value": float(tgt_fact.value_numeric),
                        "difference": float(diff),
                    },
                )
            )

    assets = unsegmented_facts_by_concept.get("ifrs:Assets")
    liabilities = unsegmented_facts_by_concept.get("ifrs:Liabilities")
    equity = unsegmented_facts_by_concept.get("ifrs:Equity")
    is_bank = "BANK" in sector.upper()
    syirkah = (
        unsegmented_facts_by_concept.get("idx:TemporarySyirkahFunds")
        or unsegmented_facts_by_concept.get("idx:SyirkahFunds")
        if is_bank
        else None
    )
    syirkah_v = syirkah.value_numeric if syirkah else Decimal("0")

    if assets and liabilities and equity:
        ast_v = assets.value_numeric
        liab_v = liabilities.value_numeric
        eq_v = equity.value_numeric
        rhs = liab_v + eq_v + syirkah_v
        diff = ast_v - rhs

        tol = abs(ast_v) * Decimal("0.0005") if ast_v != 0 else Decimal("1")
        if abs(diff) > tol:
            is_scale_error = False
            if abs(ast_v - (liab_v + eq_v * Decimal("1000"))) <= tol:
                feedback = (
                    f"Scale Mismatch Detected: Total Equity appears to be extracted in thousands "
                    f"instead of millions. Assets: {ast_v:,.0f} IDR (p.{assets.source_page}), "
                    f"Liabilities: {liab_v:,.0f} IDR (p.{liabilities.source_page}), Equity: "
                    f"{eq_v:,.0f} IDR (p.{equity.source_page}). Multiply Equity by 1,000 to match "
                    f"full IDR scale."
                )
                is_scale_error = True
            elif abs(ast_v - (liab_v * Decimal("1000") + eq_v * Decimal("1000"))) <= tol:
                feedback = (
                    f"Scale Mismatch Detected: Liabilities and Equity are 1,000x smaller than Total "
                    f"Assets. Assets: {ast_v:,.0f} IDR (p.{assets.source_page}), Liab+Eq: "
                    f"{rhs:,.0f} IDR. Please apply uniform scaling across all Balance Sheet pages."
                )
                is_scale_error = True
            else:
                feedback = (
                    f"Balance Sheet Unbalanced: Total Assets ({ast_v:,.0f} IDR from "
                    f"p.{assets.source_page}) does not equal Total Liabilities ({liab_v:,.0f} IDR "
                    f"from p.{liabilities.source_page}) + Total Equity ({eq_v:,.0f} IDR from "
                    f"p.{equity.source_page})"
                    + (
                        f" + Dana Syirkah Temporer ({syirkah_v:,.0f} IDR from p.{syirkah.source_page})"
                        if syirkah
                        else ""
                    )
                    + f". Discrepancy: {diff:+,.0f} IDR. Please re-check the Balance Sheet on pages "
                    f"{assets.source_page}, {liabilities.source_page}, {equity.source_page}."
                )

            eq_formula = (
                "Total Assets == Total Liabilities + Total Equity"
                if syirkah is None
                else "Total Assets == Total Liabilities + Dana Syirkah Temporer + Total Equity"
            )
            add(
                _issue(
                    ERROR,
                    "BALANCE_SHEET_UNBALANCED" if not is_scale_error else "SCALE_MISMATCH",
                    feedback,
                    [
                        assets.source_page,
                        liabilities.source_page,
                        equity.source_page,
                        syirkah.source_page if syirkah else None,
                    ],
                    equation=eq_formula,
                    details={
                        "assets": float(ast_v),
                        "liabilities": float(liab_v),
                        "equity": float(eq_v),
                        "syirkah_funds": float(syirkah_v),
                        "discrepancy": float(diff),
                    },
                )
            )

    ca = unsegmented_facts_by_concept.get("ifrs:CurrentAssets")
    nca = unsegmented_facts_by_concept.get("ifrs:NonCurrentAssets")
    if assets and ca and nca:
        sum_ast = ca.value_numeric + nca.value_numeric
        diff_ast = assets.value_numeric - sum_ast
        tol_ast = (
            abs(assets.value_numeric) * Decimal("0.0005")
            if assets.value_numeric != 0
            else Decimal("1")
        )
        if abs(diff_ast) > tol_ast:
            add(
                _issue(
                    ERROR,
                    "ASSET_SUM_MISMATCH",
                    f"Current Assets ({ca.value_numeric:,.0f} IDR from p.{ca.source_page}) + "
                    f"Non-Current Assets ({nca.value_numeric:,.0f} IDR from p.{nca.source_page}) = "
                    f"{sum_ast:,.0f} IDR, which does not match Total Assets "
                    f"({assets.value_numeric:,.0f} IDR from p.{assets.source_page}). Difference: "
                    f"{diff_ast:+,.0f} IDR. Please re-verify line items on pages {ca.source_page} "
                    f"and {nca.source_page}.",
                    [ca.source_page, nca.source_page, assets.source_page],
                    equation="Current Assets + Non-Current Assets == Total Assets",
                    details={
                        "assets": float(assets.value_numeric),
                        "current_assets": float(ca.value_numeric),
                        "non_current_assets": float(nca.value_numeric),
                    },
                )
            )

    cl_f = unsegmented_facts_by_concept.get("ifrs:CurrentLiabilities")
    ncl = unsegmented_facts_by_concept.get("ifrs:NonCurrentLiabilities")
    if liabilities and cl_f and ncl:
        sum_liab = cl_f.value_numeric + ncl.value_numeric
        diff_liab = liabilities.value_numeric - sum_liab
        tol_liab = (
            abs(liabilities.value_numeric) * Decimal("0.0005")
            if liabilities.value_numeric != 0
            else Decimal("1")
        )
        if abs(diff_liab) > tol_liab:
            add(
                _issue(
                    ERROR,
                    "LIABILITY_SUM_MISMATCH",
                    f"Current Liabilities ({cl_f.value_numeric:,.0f} IDR from p.{cl_f.source_page}) + "
                    f"Non-Current Liabilities ({ncl.value_numeric:,.0f} IDR from p.{ncl.source_page}) "
                    f"= {sum_liab:,.0f} IDR, which does not match Total Liabilities "
                    f"({liabilities.value_numeric:,.0f} IDR from p.{liabilities.source_page}). "
                    f"Difference: {diff_liab:+,.0f} IDR. Please re-verify liability rows on pages "
                    f"{cl_f.source_page} and {ncl.source_page}.",
                    [cl_f.source_page, ncl.source_page, liabilities.source_page],
                    equation="Current Liabilities + Non-Current Liabilities == Total Liabilities",
                    details={
                        "liabilities": float(liabilities.value_numeric),
                        "current_liabilities": float(cl_f.value_numeric),
                        "non_current_liabilities": float(ncl.value_numeric),
                    },
                )
            )

    rev = unsegmented_facts_by_concept.get("ifrs:Revenue")
    cos = unsegmented_facts_by_concept.get("ifrs:CostOfSales")
    gp = unsegmented_facts_by_concept.get("ifrs:GrossProfit")
    if rev and cos and gp:
        calc_gp = rev.value_numeric - abs(cos.value_numeric)
        diff_gp = gp.value_numeric - calc_gp
        tol_gp = (
            abs(rev.value_numeric) * Decimal("0.0005") if rev.value_numeric != 0 else Decimal("1")
        )
        if abs(diff_gp) > tol_gp:
            add(
                _issue(
                    ERROR,
                    "GROSS_PROFIT_MISMATCH",
                    f"Gross Profit mismatch: Revenue ({rev.value_numeric:,.0f} IDR from "
                    f"p.{rev.source_page}) - Cost of Sales ({cos.value_numeric:,.0f} IDR from "
                    f"p.{cos.source_page}) = {calc_gp:,.0f} IDR, but extracted Gross Profit is "
                    f"{gp.value_numeric:,.0f} IDR from p.{gp.source_page}. Please re-check the "
                    f"Income Statement on pages {rev.source_page} and {gp.source_page}.",
                    [rev.source_page, cos.source_page, gp.source_page],
                    equation="Revenue - Cost of Sales == Gross Profit",
                    details={
                        "revenue": float(rev.value_numeric),
                        "cost_of_sales": float(cos.value_numeric),
                        "gross_profit": float(gp.value_numeric),
                    },
                )
            )

    # -------------------------------------------------------------
    # LEVEL 3: Sector Specific Constraints
    # -------------------------------------------------------------
    if is_bank:
        deposits = unsegmented_facts_by_concept.get("idx:CustomerDeposits")
        loans = unsegmented_facts_by_concept.get("idx:LoansAndAdvances")
        if deposits and liabilities and deposits.value_numeric > liabilities.value_numeric:
            add(
                _issue(
                    ERROR,
                    "BANKING_DEPOSITS_EXCEED_LIABILITIES",
                    f"Customer Deposits ({deposits.value_numeric:,.0f} IDR from "
                    f"p.{deposits.source_page}) cannot exceed Total Liabilities "
                    f"({liabilities.value_numeric:,.0f} IDR from p.{liabilities.source_page}).",
                    [deposits.source_page, liabilities.source_page],
                    concept_id="idx:CustomerDeposits",
                )
            )
        if loans and assets and loans.value_numeric > assets.value_numeric:
            add(
                _issue(
                    ERROR,
                    "BANKING_LOANS_EXCEED_ASSETS",
                    f"Loans and Advances ({loans.value_numeric:,.0f} IDR from p.{loans.source_page}) "
                    f"cannot exceed Total Assets ({assets.value_numeric:,.0f} IDR from "
                    f"p.{assets.source_page}).",
                    [loans.source_page, assets.source_page],
                    concept_id="idx:LoansAndAdvances",
                )
            )

    # -------------------------------------------------------------
    # Retry context: on attempt >= 2, prepend a summary of prior misses
    # -------------------------------------------------------------
    prior_misses = previous_attempt_misses or []
    if retry_attempt >= 2 and prior_misses:
        still_missing = [
            c for c in prior_misses if c in (coverage.critical.missing + coverage.high.missing)
        ]
        if still_missing:
            issues.insert(
                0,
                _issue(
                    ERROR,
                    "RETRY_STILL_MISSING",
                    f"Attempt {retry_attempt}/3. You still have not extracted: "
                    f"{', '.join(still_missing)}. For each: re-read the hinted note sections, or "
                    f"explicitly justify with search_pages_checked.",
                ),
            )

    errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
    warnings = [i for i in issues if i.severity == IssueSeverity.WARNING]

    # INVALID if any errors exist OR any CRITICAL metric is missing/unjustified.
    # GENERIC_DISCLOSURE announcements have no CRITICAL fields (all HIGH). Design §4.3.
    is_generic_disclosure = getattr(contract, "sector", "").upper() == "UNIVERSAL" and not any(
        r.importance == "CRITICAL" for r in contract.required_facts
    )
    unjustified_critical = list(coverage.critical.missing)
    if is_generic_disclosure:
        status = "VALID" if not errors else "INVALID"
    else:
        status = "VALID" if (not errors and not unjustified_critical) else "INVALID"

    return ValidationReport(
        status=status,
        submission_id=submission_id,
        doc_id=payload.doc_id,
        ticker=payload.ticker.upper(),
        fiscal_period=payload.fiscal_period.upper(),
        errors_count=len(errors),
        warnings_count=len(warnings),
        can_retry=retry_attempt < 3,
        retry_attempt=retry_attempt,
        max_retries=3,
        issues=issues,
        coverage=coverage,
        previous_attempt_misses=prior_misses,
    )
