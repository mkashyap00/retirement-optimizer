"""Rationale generator: derive per-year decision facts from optimizer ledgers.

Entry point: ``build_rationale()``.  The ``narrative`` field of the returned
``DecisionRationale`` is always set to ``""``; Task 3 fills it via a separate
renderer so this module stays lean and stateless.
"""
from __future__ import annotations

from decimal import Decimal

from src.data.tax_rules.rmd import RMD_START_AGE, applicable_rmd_age
from src.data.tax_rules.rules import TaxRules
from src.optimization.betr import compute_betr
from src.optimization.state import Settings, YearLedger
from src.rationale.models import (
    BracketFacts,
    ConversionRationale,
    DecisionRationale,
    ThresholdWarning,
    WithdrawalRationale,
)

_ZERO = Decimal("0")
_TEN_K = Decimal("10000")
_BETR_BAND = Decimal("0.02")
_TWELVE = Decimal("12")
_TWO = Decimal("2")


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def _years_to_rmds(age_self: int, settings: Settings) -> int:
    """Years until RMDs force the money out: BETR's drawdown horizon.

    Uses the SECURE 2.0 age for the owner's birth year (73 for 1951-1959, 75
    for 1960+) -- the same rule the RMD engine applies -- rather than a flat
    73, which shortened the horizon by two years for anyone born 1960 or
    later. At least one year, so a conversion at or past RMD age still has a
    horizon to grow over.
    """
    rmd_age = (
        RMD_START_AGE
        if settings.birth_year_self is None
        else applicable_rmd_age(settings.birth_year_self)
    )
    return max(1, rmd_age - age_self)


def build_rationale(
    ledger: YearLedger,
    zero_ledger: YearLedger | None,
    action_id: str,
    rules: TaxRules,
    settings: Settings,
    filing_status: str,
    projected_future_marginal_rate: Decimal,
) -> DecisionRationale:
    """Derive per-year decision facts from optimizer ledgers.

    Args:
        ledger: the actual simulated ledger for this year.
        zero_ledger: counterfactual ledger re-run with conversion=0, or None
            when the counterfactual is unavailable (first year, no-conversion paths).
        action_id: action label e.g. ``"fill_22"`` or ``"none"``.
        rules: :class:`TaxRules` facade (injected; not re-instantiated here).
        settings: economic assumptions — ``nominal_return``, ``dividend_yield``, etc.
        filing_status: ``"single"`` or ``"joint"``.
        projected_future_marginal_rate: expected peak marginal rate on the
            baseline path (from Plan 04 Task 8 Step 3); used for the BETR verdict.

    Returns:
        :class:`DecisionRationale` with ``narrative=""`` (filled by Task 3).
    """
    bracket = _build_bracket_facts(ledger, rules, filing_status, settings.inflation)
    conversion = _build_conversion_rationale(
        ledger,
        zero_ledger,
        action_id,
        settings,
        projected_future_marginal_rate,
        bracket,
    )
    withdrawal = _build_withdrawal_rationale(ledger)
    warnings = _build_warnings(ledger, rules, filing_status, settings.inflation)

    return DecisionRationale(
        year=ledger.year,
        age_self=ledger.age_self,
        bracket=bracket,
        conversion=conversion,
        withdrawal=withdrawal,
        warnings=warnings,
        narrative="",
    )


# ---------------------------------------------------------------------------
# BracketFacts
# ---------------------------------------------------------------------------


def _ordinary_taxable_income(ledger: YearLedger) -> Decimal:
    """Ordinary taxable income — the income that actually fills the ordinary
    brackets.

    AGI is the wrong measure whenever the year realizes capital gains or
    qualified dividends: those sit in AGI but are taxed at LTCG rates and do NOT
    push ordinary income up a bracket.

    Reads the audit's ``taxable_ordinary_income``, which ``simulate_year``
    records on every ledger. This used to compute ``ordinary_income −
    deduction``, but ``ordinary_income`` is a sum line that ``run_optimization``
    adds only AFTER the rationale is built — so the lookup always missed, fell
    back to AGI, and a year funded by selling taxable assets reported $0 of
    headroom with $33,000 of the 12% bracket still open. Legacy ledgers built
    outside ``simulate_year`` carry no audit and fall back to AGI.
    """
    audit = ledger.audit
    if audit is None or "taxable_ordinary_income" not in audit:
        return ledger.agi
    return Decimal(str(audit["taxable_ordinary_income"]))


def _build_bracket_facts(
    ledger: YearLedger,
    rules: TaxRules,
    filing_status: str,
    inflation: Decimal | None = None,
) -> BracketFacts:
    """Locate the bracket the year's ordinary income lands in and its headroom.

    That is the bracket holding the LAST dollar of taxable ordinary income, not
    ``ledger.marginal_rate`` — the rate on the NEXT dollar. The two differ
    exactly where it matters: a conversion that fills the 10% bracket to its
    edge has a 12% next dollar, and matching on that labelled every fill_10 year
    "fills the 12% bracket to $100,800". A bracket's upper edge belongs to it,
    so income sitting exactly on the edge stays in the lower bracket with $0 of
    headroom. (actions.py applies the same rule to its rate-limit check.)

    Ledgers without an audit keep the old match on ``marginal_rate``.
    """
    brackets = rules.federal(ledger.year, inflation).brackets[filing_status]
    if ledger.audit is not None and "taxable_ordinary_income" in ledger.audit:
        ordinary = _ordinary_taxable_income(ledger)
        matched = next(
            (b for b in brackets if b.upper is None or ordinary <= b.upper),
            None,
        )
    else:
        matched = next((b for b in brackets if b.rate == ledger.marginal_rate), None)
    bracket_rate = matched.rate if matched is not None else ledger.marginal_rate

    if matched is None or matched.upper is None:
        # Top bracket: no finite ceiling.
        bracket_top: Decimal | None = None
        headroom_remaining = _ZERO
    else:
        bracket_top = matched.upper
        headroom_remaining = max(_ZERO, bracket_top - _ordinary_taxable_income(ledger))

    return BracketFacts(
        bracket_rate=bracket_rate,
        bracket_top=bracket_top,
        headroom_used=ledger.conversion,
        headroom_remaining=headroom_remaining,
    )


# ---------------------------------------------------------------------------
# ConversionRationale
# ---------------------------------------------------------------------------


def _build_conversion_rationale(
    ledger: YearLedger,
    zero_ledger: YearLedger | None,
    action_id: str,
    settings: Settings,
    projected_future_marginal_rate: Decimal,
    bracket: BracketFacts,
) -> ConversionRationale | None:
    """Return None when conversion == 0 or when the counterfactual ledger is absent."""
    if ledger.conversion == _ZERO or zero_ledger is None:
        return None

    marginal_cost_rate = (ledger.total_tax - zero_ledger.total_tax) / ledger.conversion
    years_to_drawdown = _years_to_rmds(ledger.age_self, settings)
    taxable_drag = settings.dividend_yield * Decimal("0.15")
    # paid_from_taxable: True when there is no Roth withdrawal funding the
    # conversion tax — i.e. the taxable account absorbs the tax bill (Scenario 2
    # in the Vanguard BETR paper, which lowers the effective BETR).
    paid_from_taxable = ledger.withdrawal_roth == _ZERO

    betr = compute_betr(
        conversion_tax_rate=marginal_cost_rate,
        years_to_drawdown=years_to_drawdown,
        pretax_return=settings.nominal_return,
        taxable_drag=taxable_drag,
        paid_from_taxable=paid_from_taxable,
    )

    if projected_future_marginal_rate > betr + _BETR_BAND:
        betr_verdict = "favorable"
    elif projected_future_marginal_rate < betr - _BETR_BAND:
        betr_verdict = "unfavorable"
    else:
        betr_verdict = "marginal"

    target_description = _format_target(bracket.bracket_rate, bracket.bracket_top)

    return ConversionRationale(
        action_id=action_id,
        amount=ledger.conversion,
        target_description=target_description,
        counterfactual_none_tax=zero_ledger.total_tax,
        marginal_cost_rate=marginal_cost_rate,
        betr=betr,
        projected_future_marginal_rate=projected_future_marginal_rate,
        betr_verdict=betr_verdict,
    )


def _format_target(rate: Decimal, bracket_top: Decimal | None) -> str:
    """Human-readable description of the conversion target.

    Example: ``"fills the 22% bracket to $206,700"``
    """
    rate_str = f"{rate:.0%}"  # e.g. "22%"
    if bracket_top is not None:
        return f"fills the {rate_str} bracket to ${bracket_top:,.0f}"
    return f"converts at {rate_str} (top bracket)"


# ---------------------------------------------------------------------------
# WithdrawalRationale
# ---------------------------------------------------------------------------


def _build_withdrawal_rationale(ledger: YearLedger) -> WithdrawalRationale:
    """Infer withdrawal ordering and its justification from the ledger."""
    order_used: list[str] = []
    if ledger.rmd > _ZERO:
        order_used.append("rmd")
    if ledger.withdrawal_taxable > _ZERO:
        order_used.append("taxable")
    if ledger.withdrawal_traditional > _ZERO:
        order_used.append("traditional")
    if ledger.withdrawal_roth > _ZERO:
        order_used.append("roth")

    has_taxable = "taxable" in order_used
    has_traditional = "traditional" in order_used

    if has_taxable and has_traditional:
        taxable_first = order_used.index("taxable") < order_used.index("traditional")
    else:
        taxable_first = False

    if taxable_first:
        reason = "taxable first: capital gains rates beat ordinary rates"
    elif has_traditional and has_taxable:
        reason = "traditional-first ordering"
    elif has_traditional:
        reason = "traditional-first ordering"
    elif has_taxable:
        reason = "taxable withdrawal (no traditional drawn)"
    elif "rmd" in order_used:
        reason = "rmd only"
    elif "roth" in order_used:
        reason = "roth withdrawal"
    else:
        reason = "no withdrawals required"

    return WithdrawalRationale(order_used=order_used, reason=reason, rmd_amount=ledger.rmd)


# ---------------------------------------------------------------------------
# ThresholdWarnings
# ---------------------------------------------------------------------------


def _build_warnings(
    ledger: YearLedger,
    rules: TaxRules,
    filing_status: str,
    inflation: Decimal | None = None,
) -> list[ThresholdWarning]:
    """Build IRMAA and NIIT threshold warnings for the given ledger."""
    warnings: list[ThresholdWarning] = []
    _add_irmaa_warnings(warnings, ledger, rules, filing_status, inflation)
    _add_niit_warning(warnings, ledger, rules, filing_status, inflation)
    return warnings


def _add_irmaa_warnings(
    warnings: list[ThresholdWarning],
    ledger: YearLedger,
    rules: TaxRules,
    filing_status: str,
    inflation: Decimal | None = None,
) -> None:
    """Append IRMAA proximity or crossed warnings in-place.

    This year's MAGI sets the premium two years out, so it is compared with
    premium year ``ledger.year + 2`` — the surcharge it would trigger.
    """
    irmaa_year = rules.irmaa(ledger.year + 2, inflation)
    tiers = irmaa_year.tiers[filing_status]
    standard_part_b = irmaa_year.part_b_standard
    persons = 1 if filing_status == "single" else 2
    couple_phrasing = "for this couple" if persons == 2 else "for a single filer"

    # --- Proximity: find the tier whose upper bound is the next threshold above magi ---
    for i, tier in enumerate(tiers):
        if tier.magi_upper is None:
            # Top (open-ended) tier — no finite ceiling to approach.
            break
        if ledger.magi < tier.magi_upper:
            # magi is within tier i; tier.magi_upper is the next crossing point.
            distance = tier.magi_upper - ledger.magi
            if _ZERO < distance <= _TEN_K:
                # The tier they would enter upon crossing is tier i+1.
                next_idx = i + 1
                if next_idx < len(tiers):
                    next_tier = tiers[next_idx]
                    monthly = (
                        next_tier.part_b_monthly - standard_part_b
                        + next_tier.part_d_monthly
                    )
                    annual = monthly * _TWELVE * persons
                    consequence = (
                        f"Part B/D surcharge of ${annual:,.2f}/yr {couple_phrasing}"
                    )
                    warnings.append(
                        ThresholdWarning(
                            kind="irmaa_tier",
                            threshold=tier.magi_upper,
                            distance=distance,
                            consequence=consequence,
                        )
                    )
            break  # magi is in tier i; no higher proximity check needed

    # --- Crossed: magi already above the first IRMAA tier threshold ---
    first_upper = tiers[0].magi_upper
    if first_upper is not None and ledger.magi > first_upper:
        distance = first_upper - ledger.magi  # negative — already crossed
        # Identify current tier to describe the surcharge actually being paid.
        current_tier = tiers[0]
        for tier in tiers:
            if tier.magi_upper is None or ledger.magi <= tier.magi_upper:
                current_tier = tier
                break
        monthly = (
            current_tier.part_b_monthly - standard_part_b + current_tier.part_d_monthly
        )
        annual = monthly * _TWELVE * persons
        consequence = (
            f"crossed into IRMAA: Part B/D surcharge of ${annual:,.2f}/yr {couple_phrasing}"
        )
        warnings.append(
            ThresholdWarning(
                kind="irmaa_tier",
                threshold=first_upper,
                distance=distance,
                consequence=consequence,
            )
        )


def _add_niit_warning(
    warnings: list[ThresholdWarning],
    ledger: YearLedger,
    rules: TaxRules,
    filing_status: str,
    inflation: Decimal | None = None,
) -> None:
    """Append a NIIT proximity or crossed warning in-place."""
    niit_threshold = rules.federal(ledger.year, inflation).niit.threshold[filing_status]
    distance = niit_threshold - ledger.magi  # positive = below threshold

    if _ZERO < distance <= _TEN_K:
        warnings.append(
            ThresholdWarning(
                kind="niit",
                threshold=niit_threshold,
                distance=distance,
                consequence="NIIT 3.8% will apply to net investment income above this threshold",
            )
        )
    elif distance <= _ZERO:
        warnings.append(
            ThresholdWarning(
                kind="niit",
                threshold=niit_threshold,
                distance=distance,
                consequence="NIIT 3.8% applies to net investment income above the threshold",
            )
        )
