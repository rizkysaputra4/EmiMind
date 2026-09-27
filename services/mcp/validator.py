"""Multi-tier accounting validation and actionable feedback generator for EMIMIND MCP Server."""

from __future__ import annotations

import uuid
from decimal import Decimal

from services.mcp.types import (
    DraftSubmissionPayload,
    ExtractedFactItem,
    ExtractionContract,
    ExtractionCoverage,
    ExtractionFactRule,
    IssueSeverity,
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
        if rule.concept_id in module.target_concepts or _normalize_concept(rule.concept_id) in module.target_concepts:
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
    retry_attempt: int = 1,
    previous_attempt_misses: list[str] | None = None,
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

    facts_by_concept: dict[str, ExtractedFactItem] = {**all_facts_by_concept, **unsegmented_facts_by_concept}

    # -------------------------------------------------------------
    # LEVEL 1: Schema & Completeness Validation
    # -------------------------------------------------------------
    valid_statements = {"BS", "IS", "CF", "EQ", "NOTE"}
    valid_period_types = {"instant", "duration_qtd", "duration_ytd", "duration_q", "duration_12m", "duration"}
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
    bucket_map = {"CRITICAL": coverage.critical, "HIGH": coverage.high, "OPTIONAL": coverage.optional}

    for rule in contract.required_facts:
        # Only EXTRACTED_RAW metrics count toward extraction coverage. Derived
        # (CALCULATED_DETERMINISTIC) and computed-with-fallback (HYBRID_FALLBACK)
        # metrics are handled by the derive pipeline, not the LLM.
        if rule.extraction_mode != "EXTRACTED_RAW":
            continue

        bucket = bucket_map.get(rule.importance.upper(), coverage.high)
        bucket.expected += 1

        norm_rule_id = _normalize_concept(rule.concept_id)
        is_present_in_facts = (rule.concept_id in facts_by_concept) or (norm_rule_id in facts_by_concept)
        is_declared_omitted = (rule.concept_id in omitted_by_concept) or (norm_rule_id in omitted_by_concept)

        if is_present_in_facts:
            bucket.found += 1
            continue

        if not rule.required:
            # Optional metrics: neither found nor omitted is fine
            continue

        if is_declared_omitted:
            omitted_item = omitted_by_concept.get(norm_rule_id) or omitted_by_concept[rule.concept_id]
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
        segmented_rev = [f for f in payload.facts if f.concept_id == "ifrs:Revenue" and f.segment is not None]
        if not segmented_rev and "REVENUE_BREAKDOWN" not in omitted_by_concept and "ifrs:Revenue_SEGMENTS" not in omitted_by_concept:
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

    for f in payload.facts:
        if f.source_page < 1:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="INVALID_PROVENANCE",
                    concept_id=f.concept_id,
                    feedback_message=f"Fact '{f.concept_id}' has an invalid source_page ({f.source_page}). Must be >= 1.",
                    target_pages=[f.source_page],
                )
            )

    # -------------------------------------------------------------
    # LEVEL 2: Accounting Math Equations
    # -------------------------------------------------------------
    assets = facts_by_concept.get("ifrs:Assets")
    liabilities = facts_by_concept.get("ifrs:Liabilities")
    equity = facts_by_concept.get("ifrs:Equity")

    if assets and liabilities and equity:
        ast_v = assets.value_numeric
        liab_v = liabilities.value_numeric
        eq_v = equity.value_numeric
        rhs = liab_v + eq_v
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
                    f"Total Equity ({eq_v:,.0f} IDR from p.{equity.source_page}). "
                    f"Discrepancy: {diff:+,.0f} IDR. Please re-check the Balance Sheet on pages {assets.source_page}, {liabilities.source_page}, {equity.source_page}."
                )

            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="BALANCE_SHEET_UNBALANCED" if not is_scale_error else "SCALE_MISMATCH",
                    equation="Total Assets == Total Liabilities + Total Equity",
                    details={
                        "assets": float(ast_v),
                        "liabilities": float(liab_v),
                        "equity": float(eq_v),
                        "discrepancy": float(diff),
                    },
                    feedback_message=feedback,
                    target_pages=list({assets.source_page, liabilities.source_page, equity.source_page}),
                )
            )

    ca = facts_by_concept.get("ifrs:CurrentAssets")
    nca = facts_by_concept.get("ifrs:NonCurrentAssets")
    if assets and ca and nca:
        sum_ast = ca.value_numeric + nca.value_numeric
        diff_ast = assets.value_numeric - sum_ast
        tol_ast = abs(assets.value_numeric) * Decimal("0.0005") if assets.value_numeric != 0 else Decimal("1")
        if abs(diff_ast) > tol_ast:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="ASSET_SUM_MISMATCH",
                    equation="Current Assets + Non-Current Assets == Total Assets",
                    details={"assets": float(assets.value_numeric), "current_assets": float(ca.value_numeric), "non_current_assets": float(nca.value_numeric)},
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
        tol_liab = abs(liabilities.value_numeric) * Decimal("0.0005") if liabilities.value_numeric != 0 else Decimal("1")
        if abs(diff_liab) > tol_liab:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="LIABILITY_SUM_MISMATCH",
                    equation="Current Liabilities + Non-Current Liabilities == Total Liabilities",
                    details={"liabilities": float(liabilities.value_numeric), "current_liabilities": float(cl.value_numeric), "non_current_liabilities": float(ncl.value_numeric)},
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
        tol_gp = abs(rev.value_numeric) * Decimal("0.0005") if rev.value_numeric != 0 else Decimal("1")
        if abs(diff_gp) > tol_gp:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="GROSS_PROFIT_MISMATCH",
                    equation="Revenue - Cost of Sales == Gross Profit",
                    details={"revenue": float(rev.value_numeric), "cost_of_sales": float(cos.value_numeric), "gross_profit": float(gp.value_numeric)},
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
        still_missing = [c for c in prior_misses if c in (coverage.critical.missing + coverage.high.missing)]
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


def _pages_overlap(rule: ExtractionFactRule, searched_pages: list[int], contract: ExtractionContract) -> bool:
    """Heuristic: does the LLM's searched-pages list include ANY location that hint text suggests?

    Since we don't know the document's ToC page numbers, we treat non-empty searched_pages as
    'attempted' and only flag INSUFFICIENT_SEARCH_SCOPE when the LLM claims very few pages
    (< 2) or supplies obviously perfunctory input. This function is intentionally lenient
    until we have per-document ToC data — better to accept a good-faith omission than nag.
    """
    if not searched_pages:
        return False
    return len(searched_pages) >= 2
