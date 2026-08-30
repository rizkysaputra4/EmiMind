"""Multi-tier accounting validation and actionable feedback generator for EMIMIND MCP Server."""

from __future__ import annotations

import uuid
from decimal import Decimal

from services.mcp.contracts import build_extraction_contract
from services.mcp.types import (
    DraftSubmissionPayload,
    IssueSeverity,
    ValidationIssue,
    ValidationReport,
)


def validate_draft_submission(
    payload: DraftSubmissionPayload,
    sector: str = "GENERIC",
    retry_attempt: int = 1,
) -> ValidationReport:
    """Performs rigorous multi-tier accounting validation on draft financial extraction payload."""
    submission_id = f"sub_{uuid.uuid4().hex[:8]}"
    issues: list[ValidationIssue] = []

    # Prefer unsegmented total facts for top-level accounting equation audits
    facts_by_concept: dict[str, ExtractedFactItem] = {}
    for f in payload.facts:
        if f.concept_id not in facts_by_concept or f.segment is None:
            facts_by_concept[f.concept_id] = f
    contract = build_extraction_contract(
        doc_id=payload.doc_id,
        ticker=payload.ticker,
        company_name=f"PT {payload.ticker} Tbk",
        sector=sector,
        fiscal_period=payload.fiscal_period,
    )

    # -------------------------------------------------------------
    # LEVEL 1: Schema & Completeness Validation
    # -------------------------------------------------------------
    omitted_by_concept = {item.metric_id: item for item in payload.omitted_kpis}

    for rule in contract.required_facts:
        if rule.required:
            is_present_in_facts = rule.concept_id in facts_by_concept
            is_declared_omitted = rule.concept_id in omitted_by_concept

            if not is_present_in_facts:
                if is_declared_omitted:
                    omitted_item = omitted_by_concept[rule.concept_id]
                    expl_lower = omitted_item.explanation.lower()

                    if len(omitted_item.explanation.strip()) < 15:
                        issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.ERROR,
                                category="INSUFFICIENT_OMISSION_EXPLANATION",
                                concept_id=rule.concept_id,
                                feedback_message=(
                                    f"Omission explanation for '{rule.label}' ({rule.concept_id}) is too brief ('{omitted_item.explanation}'). "
                                    f"Please provide a substantive explanation describing why the metric is absent in this filing."
                                ),
                                target_pages=omitted_item.search_pages_checked,
                            )
                        )
                    elif not omitted_item.search_pages_checked:
                        issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.ERROR,
                                category="MISSING_SEARCH_PAGES_AUDIT",
                                concept_id=rule.concept_id,
                                feedback_message=(
                                    f"Omission entry for '{rule.label}' ({rule.concept_id}) must specify 'search_pages_checked' "
                                    f"as a list of page numbers you searched (e.g. [22, 287, 361]) to prove search verification."
                                ),
                                target_pages=[],
                            )
                        )
                    # Contradictory omission detection: If the explanation indicates that the value is in MD&A or Highlights
                    elif any(kw in expl_lower for kw in ["disclosed in md&a", "in md&a", "in highlights", "disclosed in highlights", "is reported in", "available on page"]):
                        issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.ERROR,
                                category="CONTRADICTORY_OMISSION",
                                concept_id=rule.concept_id,
                                feedback_message=(
                                    f"Contradictory Omission for '{rule.label}' ({rule.concept_id}): You stated in the explanation that "
                                    f"this metric is disclosed in MD&A / Highlights ('{omitted_item.explanation}'). In EMIMIND, all operational "
                                    f"metrics found anywhere in the Annual Report (including MD&A / Operational Highlights pages) MUST be extracted "
                                    f"into the 'facts' array as numeric ExtractedFactItem with exact value, unit, and source_page, NOT declared in omitted_kpis!"
                                ),
                                target_pages=omitted_item.search_pages_checked,
                            )
                        )
                else:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.ERROR,
                            category="MISSING_MANDATORY_METRIC_OR_EXPLANATION",
                            concept_id=rule.concept_id,
                            feedback_message=(
                                f"Mandatory concept/KPI '{rule.label}' ({rule.concept_id}) was neither extracted in 'facts' "
                                f"nor declared in 'omitted_kpis'. You MUST search the financial notes, operational highlights, or presentation deck. "
                                f"If this metric is genuinely not disclosed in this filing, you MUST add an entry in 'omitted_kpis' with "
                                f"'reason' ('NOT_DISCLOSED_IN_REPORT'), a clear 'explanation' describing why it is missing, and 'search_pages_checked'."
                            ),
                            target_pages=[],
                        )
                    )

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
                        "Revenue was submitted only as an unsegmented total. Please extract the product line / division breakdown "
                        "from the 'Segment Information' / 'Pendapatan Usaha' note as ExtractedFactItems with "
                        "segment={'segment': '<Product/Service>', 'type': 'product'}. "
                        "If the issuer operates in a single line with no breakdown, declare this in 'omitted_kpis'."
                    ),
                    target_pages=[facts_by_concept["ifrs:Revenue"].source_page],
                )
            )

    # Check for invalid non-numeric or empty provenance
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

    # Equation 1: Balance Sheet Balance (Assets == Liabilities + Equity)
    if assets and liabilities and equity:
        ast_v = assets.value_numeric
        liab_v = liabilities.value_numeric
        eq_v = equity.value_numeric
        rhs = liab_v + eq_v
        diff = ast_v - rhs

        # Tolerance: 0.05% of total assets for rounding differences
        tol = abs(ast_v) * Decimal("0.0005") if ast_v != 0 else Decimal("1")
        if abs(diff) > tol:
            # Check if this is a 1000x unit scaling mistake
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

    # Equation 2: Asset Breakdown (CurrentAssets + NonCurrentAssets == TotalAssets)
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

    # Equation 3: Liability Breakdown (CurrentLiabilities + NonCurrentLiabilities == TotalLiabilities)
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

    # Equation 4: Gross Profit Check (Revenue - CostOfSales == GrossProfit)
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

    # Calculate status
    errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
    warnings = [i for i in issues if i.severity == IssueSeverity.WARNING]
    status = "VALID" if not errors else "INVALID"

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
    )
