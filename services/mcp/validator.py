"""Multi-tier accounting validation and actionable feedback generator for EMIMIND MCP Server."""

from __future__ import annotations

import hashlib
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from services.mcp.grounding import check_cell_grounding, check_text_grounding, resolve_scale
from services.mcp.types import (
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
    "lain-lain",
}


def _extract_segment_label(f: ExtractedFactItem) -> str:
    if f.segment and isinstance(f.segment, dict):
        for key in ("segment", "label", "name"):
            val = f.segment.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    if f.source_label_original and f.source_label_original.strip():
        return f.source_label_original.strip()
    return ""


def _is_round_fraction(child_val: Decimal, parent_val: Decimal) -> bool:
    if parent_val == 0:
        return False
    pct = (child_val / parent_val) * Decimal(100)
    rounded_pct = round(pct)
    if (
        abs(pct - rounded_pct) < Decimal("1e-4")
        and int(rounded_pct) % 5 == 0
        and 0 < int(rounded_pct) < 100
    ):
        return True
    return False


def _is_child_grounded(
    c: ExtractedFactItem,
    evidence: dict[int, PageEvidence] | None,
    default_scale: Decimal,
) -> bool:
    if evidence is None or c.source_page is None or c.source_page not in evidence:
        return False
    page_ev = evidence[c.source_page]
    if c.cell_ref is not None:
        is_g, _, _, _ = check_cell_grounding(c, page_ev, default_scale=default_scale)
        return is_g
    is_g, _ = check_text_grounding(c, page_ev, default_scale=default_scale)
    return is_g


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


def normalize_narrative_text(text: str) -> str:
    """Normalizes narrative text: lowercase, whitespace-collapsed, digits kept."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def narrative_md5(text: str) -> str:
    """Computes MD5 hash of normalized narrative text."""
    norm = normalize_narrative_text(text)
    return hashlib.md5(norm.encode("utf-8"), usedforsecurity=False).hexdigest()


_BOILERPLATE_HASHES: set[str] | None = None


def load_narrative_boilerplate_hashes() -> set[str]:
    """Loads and caches boilerplate narrative MD5 hashes from db/seeds/narrative_boilerplate.txt."""
    global _BOILERPLATE_HASHES
    if _BOILERPLATE_HASHES is None:
        hashes: set[str] = set()
        txt_path = (
            Path(__file__).resolve().parents[2] / "db" / "seeds" / "narrative_boilerplate.txt"
        )
        if not txt_path.is_file():
            txt_path = Path("db/seeds/narrative_boilerplate.txt").resolve()
        if txt_path.is_file():
            with open(txt_path, encoding="utf-8") as f:
                for line in f:
                    line_s = line.strip()
                    if not line_s or line_s.startswith("#"):
                        continue
                    if len(line_s) == 32 and all(c in "0123456789abcdefABCDEF" for c in line_s):
                        hashes.add(line_s.lower())
                    else:
                        hashes.add(narrative_md5(line_s))
        _BOILERPLATE_HASHES = hashes
    return _BOILERPLATE_HASHES


def _normalize_concept(cid: str) -> str:
    """Returns canonical concept ID if alias exists, otherwise returns original."""
    return CONCEPT_ALIASES.get(cid.lower(), cid)


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
) -> ValidationReport:
    """Performs rigorous multi-tier accounting validation on draft financial extraction payload.

    Callers must build the contract via services.mcp.contracts.build_extraction_contract
    and pass it here so the validator uses the same source-of-truth ontology snapshot as
    the LLM did during priming.
    """
    submission_id = f"sub_{uuid.uuid4().hex[:8]}"
    issues: list[ValidationIssue] = []

    # Map concepts to both all facts and unsegmented total facts
    all_facts_by_concept: dict[str, ExtractedFactItem] = {}
    unsegmented_facts_by_concept: dict[str, ExtractedFactItem] = {}

    for f in payload.facts:
        norm_cid = _normalize_concept(f.concept_id)
        if norm_cid not in all_facts_by_concept:
            all_facts_by_concept[norm_cid] = f
        if f.concept_id not in all_facts_by_concept:
            all_facts_by_concept[f.concept_id] = f

        if not f.segment:
            unsegmented_facts_by_concept[norm_cid] = f
            unsegmented_facts_by_concept[f.concept_id] = f

    facts_by_concept: dict[str, ExtractedFactItem] = {
        **all_facts_by_concept,
        **unsegmented_facts_by_concept,
    }

    # -------------------------------------------------------------
    # LEVEL 1: Schema & Completeness Validation
    # -------------------------------------------------------------
    valid_statements = {"BS", "IS", "CF", "EQ", "NOTE"}
    valid_period_types = {
        "instant",
        "duration_qtd",
        "duration_ytd",
        "duration_q",
        "duration_12m",
        "duration",
    }
    for f in payload.facts:
        if not f.statement or f.statement not in valid_statements:
            issues.append(
                ValidationIssue(
                    category="SCHEMA",
                    severity=IssueSeverity.ERROR,
                    feedback_message=(
                        f"Fact '{f.concept_id}' missing required 'statement'. "
                        f"Expected one of: {sorted(valid_statements)}."
                    ),
                    target_pages=[f.source_page] if f.source_page else [],
                )
            )

        if f.period_type is not None and f.period_type not in valid_period_types:
            issues.append(
                ValidationIssue(
                    category="SCHEMA",
                    severity=IssueSeverity.ERROR,
                    feedback_message=(
                        f"Fact '{f.concept_id}' has invalid period_type '{f.period_type}'. "
                        f"Expected one of: {sorted(valid_period_types)}."
                    ),
                    target_pages=[f.source_page] if f.source_page else [],
                )
            )

    omitted_by_concept = {}
    for item in payload.omitted_kpis:
        norm_id = _normalize_concept(item.metric_id)
        omitted_by_concept[norm_id] = item
        omitted_by_concept[item.metric_id] = item

    coverage = ExtractionCoverage()
    bucket_map = {
        "CRITICAL": coverage.critical,
        "HIGH": coverage.high,
        "OPTIONAL": coverage.optional,
    }

    for rule in contract.required_facts:
        # Only EXTRACTED_RAW metrics count toward extraction coverage. Derived
        # (CALCULATED_DETERMINISTIC) and computed-with-fallback (HYBRID_FALLBACK)
        # metrics are handled by the derive pipeline, not the LLM.
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
            # Optional metrics: neither found nor omitted is fine
            continue

        if is_declared_omitted:
            omitted_item = (
                omitted_by_concept.get(norm_rule_id) or omitted_by_concept[rule.concept_id]
            )
            expl_lower = omitted_item.explanation.lower()
            hints = _hint_search_pages(rule, contract)
            hints_str = "; ".join(hints) if hints else "(no additional hints)"

            if len(omitted_item.explanation.strip()) < 15:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="INSUFFICIENT_OMISSION_EXPLANATION",
                        concept_id=rule.concept_id,
                        feedback_message=(
                            f"Omission explanation for '{rule.label}' ({rule.concept_id}) is too brief "
                            f"('{omitted_item.explanation}'). Please provide a substantive explanation, and "
                            f"re-check these locations first: {hints_str}."
                        ),
                        target_pages=omitted_item.search_pages_checked,
                    )
                )
                bucket.missing.append(rule.concept_id)
            elif not omitted_item.search_pages_checked:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="MISSING_SEARCH_PAGES_AUDIT",
                        concept_id=rule.concept_id,
                        feedback_message=(
                            f"Omission entry for '{rule.label}' ({rule.concept_id}) must specify "
                            f"'search_pages_checked' as a list of page numbers you searched. "
                            f"Typical locations for this metric: {hints_str}."
                        ),
                        target_pages=[],
                    )
                )
                bucket.missing.append(rule.concept_id)
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
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="CONTRADICTORY_OMISSION",
                        concept_id=rule.concept_id,
                        feedback_message=(
                            f"Contradictory Omission for '{rule.label}' ({rule.concept_id}): the explanation "
                            f"says the metric is disclosed ('{omitted_item.explanation}'). Any metric found in "
                            f"the report — including MD&A / Operational Highlights — MUST be extracted into "
                            f"the 'facts' array with exact value, unit, and source_page, NOT declared in "
                            f"omitted_kpis. Re-extract from: {hints_str}."
                        ),
                        target_pages=omitted_item.search_pages_checked,
                    )
                )
                bucket.missing.append(rule.concept_id)
            elif hints and not _pages_overlap(rule, omitted_item.search_pages_checked, contract):
                # The LLM claimed to have searched, but their pages don't include ANY hinted locations.
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="INSUFFICIENT_SEARCH_SCOPE",
                        concept_id=rule.concept_id,
                        feedback_message=(
                            f"Omission for '{rule.label}' ({rule.concept_id}) claims pages "
                            f"{omitted_item.search_pages_checked} were searched, but none of the typical "
                            f"locations for this metric were checked. Search these first: {hints_str}."
                        ),
                        target_pages=omitted_item.search_pages_checked,
                    )
                )
                bucket.missing.append(rule.concept_id)
            else:
                bucket.omitted_with_justification += 1
        else:
            hints = _hint_search_pages(rule, contract)
            hints_str = "; ".join(hints) if hints else "(no additional hints)"
            is_critical = rule.importance == "CRITICAL"
            severity_label = "CRITICAL" if is_critical else "HIGH-priority"
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR if is_critical else IssueSeverity.WARNING,
                    category="MISSING_MANDATORY_METRIC_OR_EXPLANATION",
                    concept_id=rule.concept_id,
                    feedback_message=(
                        f"Missing {severity_label} metric '{rule.label}' ({rule.concept_id}). "
                        f"Typical locations: {hints_str}. "
                        f"Extract it into 'facts' with source_page; or, if truly not disclosed, add to "
                        f"'omitted_kpis' with 'reason', a 15+ char 'explanation', and "
                        f"'search_pages_checked' proving you looked at the hinted locations."
                    ),
                    target_pages=[],
                )
            )
            bucket.missing.append(rule.concept_id)

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
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.WARNING,
                    category="MISSING_GRANULAR_REVENUE_BREAKDOWN",
                    concept_id="ifrs:Revenue",
                    feedback_message=(
                        "Revenue was submitted only as an unsegmented total. Extract the product line / division "
                        "breakdown from the 'Segment Information' note as ExtractedFactItems with "
                        "segment={'segment': '<Product/Service>', 'type': 'product'}. If the issuer operates in a "
                        "single line with no breakdown, declare this in 'omitted_kpis'."
                    ),
                    target_pages=[facts_by_concept["ifrs:Revenue"].source_page],
                )
            )

    default_contract_scale = resolve_scale(None, getattr(contract, "scaling_rules", None))

    for f in payload.facts:
        if f.segment and (f.source_page is None or f.source_page <= 0):
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="SEGMENT_PROVENANCE",
                    concept_id=f.concept_id,
                    feedback_message=(
                        f"Segmented fact '{f.concept_id}' must cite its own disclosure note source_page (got {f.source_page})."
                    ),
                    target_pages=[],
                )
            )
            continue

        if (
            f.source_page is None
            or f.source_page < 1
            or (page_count is not None and f.source_page > page_count)
        ):
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="PROVENANCE",
                    concept_id=f.concept_id,
                    feedback_message=(
                        f"Fact '{f.concept_id}' source_page {f.source_page} is out of document bounds "
                        f"(valid: 1..{page_count or 'N/A'})."
                    ),
                    target_pages=[f.source_page] if f.source_page else [],
                )
            )
            continue

        if evidence is not None:
            if f.source_page not in evidence:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="PROVENANCE",
                        concept_id=f.concept_id,
                        feedback_message=(
                            f"Fact '{f.concept_id}' cites source_page {f.source_page} which has no evidence loaded."
                        ),
                        target_pages=[f.source_page],
                    )
                )
                continue

            page_ev = evidence[f.source_page]
            if f.cell_ref is not None:
                is_grounded, err_msg, _conf, _bbox = check_cell_grounding(
                    f, page_ev, default_scale=default_contract_scale
                )
                if not is_grounded:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.ERROR,
                            category="GROUNDING_CELL",
                            concept_id=f.concept_id,
                            feedback_message=err_msg
                            or f"Fact '{f.concept_id}' failed cell grounding.",
                            target_pages=[f.source_page],
                        )
                    )
            elif page_ev.text_source == "pdf_text":
                is_grounded, err_msg = check_text_grounding(
                    f, page_ev, default_scale=default_contract_scale
                )
                if not is_grounded:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.ERROR,
                            category="GROUNDING_TEXT",
                            concept_id=f.concept_id,
                            feedback_message=err_msg
                            or f"Fact '{f.concept_id}' value not found in text on page {f.source_page}.",
                            target_pages=[f.source_page],
                        )
                    )
            elif page_ev.text_source == "ocr":
                is_grounded, _ = check_text_grounding(
                    f, page_ev, default_scale=default_contract_scale
                )
                if not is_grounded:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.WARNING,
                            category="GROUNDING_OCR",
                            concept_id=f.concept_id,
                            details={"needs_review": True},
                            feedback_message=(
                                f"Fact '{f.concept_id}' on OCR page {f.source_page} could not be confirmed "
                                f"in OCR text; flagged for review."
                            ),
                            target_pages=[f.source_page],
                        )
                    )

    # Group facts by concept
    facts_by_concept_grouped: dict[str, list[ExtractedFactItem]] = {}
    for f in payload.facts:
        facts_by_concept_grouped.setdefault(f.concept_id, []).append(f)

    # Anti-synthetic rules: SYNTHETIC_LABEL and SYNTHETIC_SPLIT
    if evidence is not None:
        for cid, c_facts in facts_by_concept_grouped.items():
            children = [f for f in c_facts if f.segment]
            unsegmented = [f for f in c_facts if not f.segment]

            # 1. SYNTHETIC_LABEL
            for child in children:
                seg_label = _extract_segment_label(child)
                norm_label = seg_label.lower().strip()
                is_placeholder = norm_label in PLACEHOLDER_SEGMENT_LABELS
                if (
                    not is_placeholder
                    and len(children) == 1
                    and norm_label in ONLY_CHILD_PLACEHOLDER_LABELS
                ):
                    is_placeholder = True

                if is_placeholder:
                    verbatim_found = False
                    if child.source_page is not None and child.source_page in evidence:
                        page_text = evidence[child.source_page].page_text
                        if norm_label in page_text.lower():
                            verbatim_found = True

                    if not verbatim_found:
                        issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.ERROR,
                                category="SYNTHETIC_LABEL",
                                concept_id=cid,
                                feedback_message=(
                                    f"Placeholder segment label '{seg_label}' on '{cid}' is rejected "
                                    f"unless found verbatim on source page {child.source_page}."
                                ),
                                target_pages=[child.source_page] if child.source_page else [],
                            )
                        )

            # 2. SYNTHETIC_SPLIT
            if len(children) >= 2:
                parent_val = (
                    unsegmented[0].value_numeric
                    if unsegmented
                    else sum((c.value_numeric for c in children), Decimal(0))
                )
                if parent_val != 0:
                    all_round = all(
                        _is_round_fraction(c.value_numeric, parent_val) for c in children
                    )
                    if all_round:
                        any_grounded = any(
                            _is_child_grounded(c, evidence, default_contract_scale)
                            for c in children
                        )
                        if not any_grounded:
                            issues.append(
                                ValidationIssue(
                                    severity=IssueSeverity.ERROR,
                                    category="SYNTHETIC_SPLIT",
                                    concept_id=cid,
                                    feedback_message=(
                                        f"Breakdown for concept '{cid}' rejected as synthetic split: "
                                        f"all {len(children)} children are exact round multiples of 5% of total ({parent_val:,.0f}) "
                                        f"and none is grounded in page evidence."
                                    ),
                                    target_pages=list(
                                        {c.source_page for c in children if c.source_page}
                                    ),
                                )
                            )

    boilerplate_hashes = load_narrative_boilerplate_hashes()

    # Pre-extract anchors for MDA generic checks
    product_anchors: set[str] = set()
    for f in payload.facts:
        if f.segment and isinstance(f.segment, dict):
            for v in f.segment.values():
                if isinstance(v, str) and len(v.strip()) >= 2:
                    v_clean = v.strip().lower()
                    product_anchors.add(v_clean)
                    for word in re.split(r"[/\-, ]+", v_clean):
                        if len(word) >= 4 and word not in ("type", "segment", "item"):
                            product_anchors.add(word)
        if f.source_label_original and len(f.source_label_original.strip()) >= 2:
            s_clean = f.source_label_original.strip().lower()
            product_anchors.add(s_clean)
            for word in re.split(r"[/\-, ]+", s_clean):
                if len(word) >= 4:
                    product_anchors.add(word)

    period_pattern = re.compile(
        r"\b(20\d\d|19\d\d|q[1-4]|tw[1-4]|fy|1h|2h|semester|triwulan|tahunan|annual)\b",
        re.IGNORECASE,
    )

    for n in payload.narratives:
        if n.source_page < 1 or (page_count is not None and n.source_page > page_count):
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="PROVENANCE",
                    feedback_message=f"Narrative source_page {n.source_page} is out of document bounds.",
                    target_pages=[n.source_page],
                )
            )
        elif evidence is not None and n.source_page not in evidence:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="PROVENANCE",
                    feedback_message=f"Narrative cites source_page {n.source_page} which has no evidence loaded.",
                    target_pages=[n.source_page],
                )
            )

        n_hash = narrative_md5(n.text_original)

        # 1. NARRATIVE_BOILERPLATE
        if n_hash in boilerplate_hashes:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="NARRATIVE_BOILERPLATE",
                    feedback_message=(
                        f"Narrative chunk on page {n.source_page} matches known boilerplate / disclaimer text: "
                        f"'{n.text_original[:80]}...'."
                    ),
                    target_pages=[n.source_page] if n.source_page else [],
                )
            )

        # 2. NARRATIVE_DUPLICATE (cross-issuer)
        if cross_issuer_narrative_hashes and n_hash in cross_issuer_narrative_hashes:
            committed_ticker = cross_issuer_narrative_hashes[n_hash]
            if committed_ticker != payload.ticker:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="NARRATIVE_DUPLICATE",
                        feedback_message=(
                            f"Narrative chunk on page {n.source_page} duplicates committed narrative from "
                            f"different issuer '{committed_ticker}'."
                        ),
                        target_pages=[n.source_page] if n.source_page else [],
                    )
                )

        # 3. NARRATIVE_GENERIC (for MDA chunks)
        if n.section.upper() == "MDA":
            has_digit = bool(re.search(r"\d", n.text_original))
            has_period = bool(period_pattern.search(n.text_original))
            if payload.fiscal_period and payload.fiscal_period.lower() in n.text_original.lower():
                has_period = True
            has_product = any(anchor in n.text_original.lower() for anchor in product_anchors)
            has_ticker = payload.ticker.lower() in n.text_original.lower()
            has_company = False
            if contract and getattr(contract, "company_name", None):
                clean_name = re.sub(r"[^\w\s]", " ", contract.company_name.lower())
                clean_name = re.sub(r"\b(pt|tbk|persero)\b", "", clean_name)
                clean_name = re.sub(r"\s+", " ", clean_name).strip()
                clean_text = re.sub(r"[^\w\s]", " ", n.text_original.lower())
                clean_text = re.sub(r"\s+", " ", clean_text).strip()
                if len(clean_name) >= 3 and clean_name in clean_text:
                    has_company = True

            if not (has_digit or has_period or has_product or has_ticker or has_company):
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="NARRATIVE_GENERIC",
                        feedback_message=(
                            f"MD&A narrative chunk on page {n.source_page} lacks any issuer anchor "
                            f"(no numbers, no named products/segments, and no period references): "
                            f"'{n.text_original[:80]}...'."
                        ),
                        target_pages=[n.source_page] if n.source_page else [],
                    )
                )

    # -------------------------------------------------------------
    # LEVEL 2: Accounting Math Equations & Tie-Outs
    # -------------------------------------------------------------

    # 1. Segment sum-to-parent tie-out (SUM_MISMATCH)
    for cid, c_facts in facts_by_concept_grouped.items():
        children = [f for f in c_facts if f.segment]
        unsegmented = [f for f in c_facts if not f.segment]
        if not children or not unsegmented:
            continue

        parent_fact = unsegmented[0]
        parent_val = parent_fact.value_numeric

        # Group children by dimension
        children_by_dim: dict[str, list[ExtractedFactItem]] = {}
        for child in children:
            seg = child.segment or {}
            dim = seg.get("type") or seg.get("dimension") or "default"
            children_by_dim.setdefault(str(dim), []).append(child)

        for dim, dim_children in children_by_dim.items():
            dim_sum = sum((c.value_numeric for c in dim_children), Decimal(0))
            tol = max(default_contract_scale, Decimal("0.001") * abs(parent_val))
            diff = dim_sum - parent_val
            if abs(diff) > tol:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="SUM_MISMATCH",
                        concept_id=cid,
                        details={
                            "parent_value": float(parent_val),
                            "children_sum": float(dim_sum),
                            "discrepancy": float(diff),
                            "dimension": dim,
                        },
                        feedback_message=(
                            f"Children of '{cid}' for segment dimension '{dim}' sum to {dim_sum:,.0f} IDR, "
                            f"which does not match parent total ({parent_val:,.0f} IDR from p.{parent_fact.source_page}). "
                            f"Difference: {diff:+,.0f} IDR (tolerance: {tol:,.0f} IDR). "
                            f"Please re-check the breakdown rows on pages {sorted({c.source_page for c in dim_children if c.source_page})}."
                        ),
                        target_pages=list(
                            {c.source_page for c in dim_children if c.source_page}
                            | ({parent_fact.source_page} if parent_fact.source_page else set())
                        ),
                    )
                )

    # 2. Cross-statement tie-out validation from YAML (TIE_OUT)
    tie_out_rules = load_tie_out_rules()
    for to_rule in tie_out_rules:
        src_cid = _normalize_concept(to_rule["source_concept"])
        tgt_cid = _normalize_concept(to_rule["target_concept"])
        src_stmt = to_rule.get("source_statement")
        tgt_stmt = to_rule.get("target_statement")

        src_candidates = [
            f
            for f in payload.facts
            if _normalize_concept(f.concept_id) == src_cid
            and not f.segment
            and (src_stmt is None or f.statement == src_stmt)
        ]
        tgt_candidates = [
            f
            for f in payload.facts
            if _normalize_concept(f.concept_id) == tgt_cid
            and not f.segment
            and (tgt_stmt is None or f.statement == tgt_stmt)
        ]

        if src_candidates and tgt_candidates:
            src_fact = src_candidates[0]
            tgt_fact = tgt_candidates[0]
            if src_fact is tgt_fact:
                continue

            tol = max(
                default_contract_scale,
                Decimal("0.001") * max(abs(src_fact.value_numeric), abs(tgt_fact.value_numeric)),
            )
            diff = src_fact.value_numeric - tgt_fact.value_numeric
            if abs(diff) > tol:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        category="TIE_OUT",
                        concept_id=src_fact.concept_id,
                        details={
                            "source_concept": src_fact.concept_id,
                            "source_value": float(src_fact.value_numeric),
                            "target_concept": tgt_fact.concept_id,
                            "target_value": float(tgt_fact.value_numeric),
                            "difference": float(diff),
                        },
                        feedback_message=(
                            f"Cross-statement tie-out failure: '{src_fact.concept_id}' ({src_fact.statement or 'NOTE'}, "
                            f"{src_fact.value_numeric:,.0f} IDR from p.{src_fact.source_page}) does not match "
                            f"'{tgt_fact.concept_id}' ({tgt_fact.statement or 'BS'}, {tgt_fact.value_numeric:,.0f} IDR from p.{tgt_fact.source_page}). "
                            f"Difference: {diff:+,.0f} IDR. Check you used the current-period column."
                        ),
                        target_pages=list(
                            {
                                p
                                for p in (src_fact.source_page, tgt_fact.source_page)
                                if p is not None
                            }
                        ),
                    )
                )
    assets = facts_by_concept.get("ifrs:Assets")
    liabilities = facts_by_concept.get("ifrs:Liabilities")
    equity = facts_by_concept.get("ifrs:Equity")
    syirkah = facts_by_concept.get("idx:TemporarySyirkahFunds") or facts_by_concept.get("idx:SyirkahFunds")
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
                    f"Scale Mismatch Detected: Total Equity appears to be extracted in thousands instead of millions. "
                    f"Assets: {ast_v:,.0f} IDR (p.{assets.source_page}), Liabilities: {liab_v:,.0f} IDR (p.{liabilities.source_page}), "
                    f"Equity: {eq_v:,.0f} IDR (p.{equity.source_page}). Multiply Equity by 1,000 to match full IDR scale."
                )
                is_scale_error = True
            elif abs(ast_v - (liab_v * Decimal("1000") + eq_v * Decimal("1000"))) <= tol:
                feedback = (
                    f"Scale Mismatch Detected: Liabilities and Equity are 1,000x smaller than Total Assets. "
                    f"Assets: {ast_v:,.0f} IDR (p.{assets.source_page}), Liab+Eq: {rhs:,.0f} IDR. "
                    f"Please apply uniform scaling across all Balance Sheet pages."
                )
                is_scale_error = True
            else:
                feedback = (
                    f"Balance Sheet Unbalanced: Total Assets ({ast_v:,.0f} IDR from p.{assets.source_page}) "
                    f"does not equal Total Liabilities ({liab_v:,.0f} IDR from p.{liabilities.source_page}) + "
                    f"Total Equity ({eq_v:,.0f} IDR from p.{equity.source_page})"
                    + (f" + Dana Syirkah Temporer ({syirkah_v:,.0f} IDR from p.{syirkah.source_page})" if syirkah else "")
                    + f". Discrepancy: {diff:+,.0f} IDR. Please re-check the Balance Sheet on pages {assets.source_page}, {liabilities.source_page}, {equity.source_page}."
                )

            eq_formula = (
                "Total Assets == Total Liabilities + Total Equity"
                if syirkah is None
                else "Total Assets == Total Liabilities + Dana Syirkah Temporer + Total Equity"
            )
            target_pgs = {assets.source_page, liabilities.source_page, equity.source_page}
            if syirkah and syirkah.source_page:
                target_pgs.add(syirkah.source_page)

            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="BALANCE_SHEET_UNBALANCED" if not is_scale_error else "SCALE_MISMATCH",
                    equation=eq_formula,
                    details={
                        "assets": float(ast_v),
                        "liabilities": float(liab_v),
                        "equity": float(eq_v),
                        "syirkah_funds": float(syirkah_v),
                        "discrepancy": float(diff),
                    },
                    feedback_message=feedback,
                    target_pages=list(target_pgs),
                )
            )

    ca = facts_by_concept.get("ifrs:CurrentAssets")
    nca = facts_by_concept.get("ifrs:NonCurrentAssets")
    if assets and ca and nca:
        sum_ast = ca.value_numeric + nca.value_numeric
        diff_ast = assets.value_numeric - sum_ast
        tol_ast = (
            abs(assets.value_numeric) * Decimal("0.0005")
            if assets.value_numeric != 0
            else Decimal("1")
        )
        if abs(diff_ast) > tol_ast:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="ASSET_SUM_MISMATCH",
                    equation="Current Assets + Non-Current Assets == Total Assets",
                    details={
                        "assets": float(assets.value_numeric),
                        "current_assets": float(ca.value_numeric),
                        "non_current_assets": float(nca.value_numeric),
                    },
                    feedback_message=(
                        f"Current Assets ({ca.value_numeric:,.0f} IDR from p.{ca.source_page}) + "
                        f"Non-Current Assets ({nca.value_numeric:,.0f} IDR from p.{nca.source_page}) = {sum_ast:,.0f} IDR, "
                        f"which does not match Total Assets ({assets.value_numeric:,.0f} IDR from p.{assets.source_page}). "
                        f"Difference: {diff_ast:+,.0f} IDR. Please re-verify line items on pages {ca.source_page} and {nca.source_page}."
                    ),
                    target_pages=list({ca.source_page, nca.source_page, assets.source_page}),
                )
            )

    cl = facts_by_concept.get("ifrs:CurrentLiabilities")
    ncl = facts_by_concept.get("ifrs:NonCurrentLiabilities")
    if liabilities and cl and ncl:
        sum_liab = cl.value_numeric + ncl.value_numeric
        diff_liab = liabilities.value_numeric - sum_liab
        tol_liab = (
            abs(liabilities.value_numeric) * Decimal("0.0005")
            if liabilities.value_numeric != 0
            else Decimal("1")
        )
        if abs(diff_liab) > tol_liab:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="LIABILITY_SUM_MISMATCH",
                    equation="Current Liabilities + Non-Current Liabilities == Total Liabilities",
                    details={
                        "liabilities": float(liabilities.value_numeric),
                        "current_liabilities": float(cl.value_numeric),
                        "non_current_liabilities": float(ncl.value_numeric),
                    },
                    feedback_message=(
                        f"Current Liabilities ({cl.value_numeric:,.0f} IDR from p.{cl.source_page}) + "
                        f"Non-Current Liabilities ({ncl.value_numeric:,.0f} IDR from p.{ncl.source_page}) = {sum_liab:,.0f} IDR, "
                        f"which does not match Total Liabilities ({liabilities.value_numeric:,.0f} IDR from p.{liabilities.source_page}). "
                        f"Difference: {diff_liab:+,.0f} IDR. Please re-verify liability rows on pages {cl.source_page} and {ncl.source_page}."
                    ),
                    target_pages=list({cl.source_page, ncl.source_page, liabilities.source_page}),
                )
            )

    rev = facts_by_concept.get("ifrs:Revenue")
    cos = facts_by_concept.get("ifrs:CostOfSales")
    gp = facts_by_concept.get("ifrs:GrossProfit")
    if rev and cos and gp:
        calc_gp = rev.value_numeric - abs(cos.value_numeric)
        diff_gp = gp.value_numeric - calc_gp
        tol_gp = (
            abs(rev.value_numeric) * Decimal("0.0005") if rev.value_numeric != 0 else Decimal("1")
        )
        if abs(diff_gp) > tol_gp:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="GROSS_PROFIT_MISMATCH",
                    equation="Revenue - Cost of Sales == Gross Profit",
                    details={
                        "revenue": float(rev.value_numeric),
                        "cost_of_sales": float(cos.value_numeric),
                        "gross_profit": float(gp.value_numeric),
                    },
                    feedback_message=(
                        f"Gross Profit mismatch: Revenue ({rev.value_numeric:,.0f} IDR from p.{rev.source_page}) - "
                        f"Cost of Sales ({cos.value_numeric:,.0f} IDR from p.{cos.source_page}) = {calc_gp:,.0f} IDR, "
                        f"but extracted Gross Profit is {gp.value_numeric:,.0f} IDR from p.{gp.source_page}. "
                        f"Please re-check the Income Statement on pages {rev.source_page} and {gp.source_page}."
                    ),
                    target_pages=list({rev.source_page, cos.source_page, gp.source_page}),
                )
            )

    # -------------------------------------------------------------
    # LEVEL 3: Sector Specific Constraints
    # -------------------------------------------------------------
    if "BANK" in sector.upper():
        deposits = facts_by_concept.get("idx:CustomerDeposits")
        loans = facts_by_concept.get("idx:LoansAndAdvances")
        if deposits and liabilities and deposits.value_numeric > liabilities.value_numeric:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="BANKING_DEPOSITS_EXCEED_LIABILITIES",
                    concept_id="idx:CustomerDeposits",
                    feedback_message=f"Customer Deposits ({deposits.value_numeric:,.0f} IDR from p.{deposits.source_page}) cannot exceed Total Liabilities ({liabilities.value_numeric:,.0f} IDR from p.{liabilities.source_page}).",
                    target_pages=[deposits.source_page, liabilities.source_page],
                )
            )
        if loans and assets and loans.value_numeric > assets.value_numeric:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="BANKING_LOANS_EXCEED_ASSETS",
                    concept_id="idx:LoansAndAdvances",
                    feedback_message=f"Loans and Advances ({loans.value_numeric:,.0f} IDR from p.{loans.source_page}) cannot exceed Total Assets ({assets.value_numeric:,.0f} IDR from p.{assets.source_page}).",
                    target_pages=[loans.source_page, assets.source_page],
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
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="RETRY_STILL_MISSING",
                    feedback_message=(
                        f"Attempt {retry_attempt}/3. You still have not extracted: {', '.join(still_missing)}. "
                        f"For each: re-read the hinted note sections, or explicitly justify with search_pages_checked."
                    ),
                    target_pages=[],
                ),
            )

    errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
    warnings = [i for i in issues if i.severity == IssueSeverity.WARNING]

    # A submission is INVALID if any errors exist OR any CRITICAL metric is missing/unjustified.
    # Exception: GENERIC_DISCLOSURE announcements have no CRITICAL fields (all HIGH) — accept
    # partial extractions as long as there are no schema errors. Design §4.3.
    is_generic_disclosure = getattr(contract, "sector", "").upper() == "UNIVERSAL" and not any(
        r.importance == "CRITICAL" for r in contract.required_facts
    )
    unjustified_critical = [c for c in coverage.critical.missing]
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


def _pages_overlap(
    rule: ExtractionFactRule, searched_pages: list[int], contract: ExtractionContract
) -> bool:
    """Heuristic: does the LLM's searched-pages list include ANY location that hint text suggests?

    Since we don't know the document's ToC page numbers, we treat non-empty searched_pages as
    'attempted' and only flag INSUFFICIENT_SEARCH_SCOPE when the LLM claims very few pages
    (< 2) or supplies obviously perfunctory input. This function is intentionally lenient
    until we have per-document ToC data — better to accept a good-faith omission than nag.
    """
    if not searched_pages:
        return False
    return len(searched_pages) >= 2
