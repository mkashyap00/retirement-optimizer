"""Federal income tax engine — brackets + deductions + senior bonus + SALT + NIIT.

Fixes B1: senior deduction is a SEPARATE deduction with MAGI phaseout,
         applying independently of standard/itemized choice.
Fixes B4: SALT capped per SaltRule with MAGI phase-down and floor.
Fixes B5: NIIT computed at 3.8% on lesser of net investment income or AGI
         above threshold; included in total_tax.
Fixes B8: no DB — consumes TaxRules provider only.

Algorithm ordering:
  1. Compute AGI
  2. Compute senior deduction (independent of standard/itemized)
  3. Choose max(standard, itemized_total) as base_deduction
     (SALT component = min(state+property, salt_cap(agi, status, year)))
  4. total_deduction = base_deduction + senior
  5. Deduction offsets ordinary first, remainder offsets preferential
  6. NIIT = rate * min(max(0, agi - threshold), investment_income)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.data.tax_rules.rules import TaxRules
from src.data.tax_rules.types import Bracket
from src.engines.tax.common import bracket_tax as _bracket_tax_shared


@dataclass(frozen=True)
class FederalIncome:
    ordinary: Decimal
    ltcg: Decimal = Decimal("0")
    qualified_dividends: Decimal = Decimal("0")
    investment_income: Decimal = Decimal("0")   # for NIIT


@dataclass(frozen=True)
class ItemizedInputs:
    state_tax_paid: Decimal = Decimal("0")
    property_tax: Decimal = Decimal("0")
    mortgage_interest: Decimal = Decimal("0")
    charity: Decimal = Decimal("0")
    medical: Decimal = Decimal("0")


@dataclass(frozen=True)
class FederalResult:
    total_tax: Decimal
    ordinary_tax: Decimal
    ltcg_tax: Decimal
    niit: Decimal
    taxable_income: Decimal
    # The part of taxable_income that sits in the ORDINARY brackets, i.e.
    # max(0, ordinary − deduction). Qualified dividends and LTCG stack above
    # it and are taxed on their own schedule, so this — not taxable_income —
    # is what a bracket's upper edge bounds.
    taxable_ordinary: Decimal
    deduction_used: Decimal
    senior_deduction: Decimal
    deduction_type: str           # "standard" | "itemized"
    marginal_rate: Decimal        # on next dollar of ordinary income
    agi: Decimal


def _bracket_tax(income: Decimal, brackets: list[Bracket]) -> Decimal:
    """Walk brackets accumulating tax; final bracket has upper=None.

    Delegates to the shared ``bracket_tax`` helper in ``common`` (DRY).
    """
    return _bracket_tax_shared(income, brackets)


def _marginal_rate(income: Decimal, brackets: list[Bracket]) -> Decimal:
    """Return the rate of the bracket in which the next dollar of income falls."""
    for bracket in brackets:
        # bracket.upper is None means top bracket — always applies for income here
        if bracket.upper is None or income < bracket.upper:
            return bracket.rate
    # Income exceeds every ceiling (unreachable with a proper top bracket)
    return brackets[-1].rate


def _stacked_ltcg_tax(
    pref_taxable: Decimal,
    floor: Decimal,
    brackets: list[Bracket],
) -> Decimal:
    """Compute LTCG/QD tax by stacking preferential income ON TOP of ordinary.

    ``floor`` is taxable_ordinary (already consumed by the ordinary brackets).
    Walk LTCG brackets from ``floor``, taxing ``pref_taxable`` dollars through
    each bracket's rate until exhausted.  Fixes B2 (unused deduction offsets
    preferential via pref_taxable) and B3 (correct stacking arithmetic).
    """
    tax, pos, remaining = Decimal("0"), floor, pref_taxable
    for b in brackets:
        if remaining <= 0:
            break
        if b.upper is not None and pos >= b.upper:
            continue
        room = remaining if b.upper is None else min(remaining, b.upper - pos)
        tax += room * b.rate
        pos += room
        remaining -= room
    return tax


class FederalTaxEngine:
    """Federal tax engine consuming TaxRules (no DB)."""

    def __init__(self, rules: TaxRules) -> None:
        self.rules = rules

    def salt_cap(
        self, magi: Decimal, filing_status: str, year: int,
        inflation: Decimal | None = None,
    ) -> Decimal:
        """Return the effective SALT cap for *filing_status* at *magi*.

        Formula: max(floor, cap[status] - phase_down_rate * max(0, magi - phase_down_start))
        """
        rule = self.rules.federal(year, inflation).salt
        raw = rule.cap[filing_status] - rule.phase_down_rate * max(
            Decimal("0"), magi - rule.phase_down_start
        )
        return max(rule.floor, raw)

    def calculate(
        self,
        income: FederalIncome,
        filing_status: str,
        year: int,
        taxpayer_age: int,
        spouse_age: int | None = None,
        itemized: ItemizedInputs | None = None,
        inflation: Decimal | None = None,
    ) -> FederalResult:
        """*inflation* projects tables for years past the latest published one
        (see TaxRules.federal); None keeps the legacy clamp."""
        fy = self.rules.federal(year, inflation)

        # 1. AGI (proxy for MAGI — no above-the-line adjustments in scope yet)
        agi = income.ordinary + income.ltcg + income.qualified_dividends

        # People aged 65+ on this return: both spouses on a joint return, the
        # filer alone otherwise.
        n_65 = (1 if taxpayer_age >= 65 else 0) + (
            1 if spouse_age is not None and spouse_age >= 65 else 0
        )
        if filing_status != "joint":
            n_65 = min(n_65, 1)

        # 2. Senior bonus — separate and independent of standard/itemized choice.
        # Schedule 1-A Part V phases out the $6,000 ONCE (line 35) and enters
        # that reduced amount for EACH eligible spouse (lines 36a/36b); phasing
        # out the pooled $12,000 instead overstated it by up to $6,000.
        senior = Decimal("0")
        if fy.senior_bonus.first_year <= year <= fy.senior_bonus.last_year:
            phaseout_start = fy.senior_bonus.phaseout_start[filing_status]
            reduction = max(
                Decimal("0"),
                (agi - phaseout_start) * fy.senior_bonus.phaseout_rate,
            )
            per_person = max(Decimal("0"), fy.senior_bonus.amount_per_person - reduction)
            senior = per_person * n_65

        # 3. Standard vs itemized (SALT capped per SaltRule with phase-down)
        if itemized is not None:
            medical_threshold = agi * Decimal("0.075")
            allowable_medical = max(
                Decimal("0"), itemized.medical - medical_threshold
            )
            salt_used = min(
                itemized.state_tax_paid + itemized.property_tax,
                self.salt_cap(agi, filing_status, year, inflation),
            )
            itemized_total = (
                salt_used
                + itemized.mortgage_interest
                + itemized.charity
                + allowable_medical
            )
        else:
            itemized_total = Decimal("0")

        # The age-65 addition is part of the STANDARD deduction (IRC §63(c)(1)(B),
        # §63(f)), so it counts in the itemize-or-not comparison and is lost by
        # itemizing — unlike the senior bonus above.
        standard = fy.standard_deduction[filing_status] + fy.aged_addition[filing_status] * n_65
        if itemized_total > standard:
            base_deduction = itemized_total
            deduction_type = "itemized"
        else:
            base_deduction = standard
            deduction_type = "standard"

        # 4. Total deduction = base + senior (senior is always additive)
        total_deduction = base_deduction + senior

        # 5. Deduction offsets ordinary first; remainder offsets preferential (B2 fix)
        taxable_income = max(Decimal("0"), agi - total_deduction)
        taxable_ordinary = max(Decimal("0"), income.ordinary - total_deduction)
        pref_taxable = taxable_income - taxable_ordinary

        # 6. Tax components
        ord_brackets = fy.brackets[filing_status]
        ordinary_tax = _bracket_tax(taxable_ordinary, ord_brackets)
        ltcg_tax = _stacked_ltcg_tax(
            pref_taxable,
            floor=taxable_ordinary,
            brackets=fy.ltcg_brackets[filing_status],
        )
        # NIIT: 3.8% on lesser of net investment income or AGI above threshold
        niit = fy.niit.rate * min(
            max(Decimal("0"), agi - fy.niit.threshold[filing_status]),
            income.investment_income,
        )

        total_tax = (ordinary_tax + ltcg_tax + niit).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return FederalResult(
            total_tax=total_tax,
            ordinary_tax=ordinary_tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            ltcg_tax=ltcg_tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            niit=niit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            taxable_income=taxable_income,
            taxable_ordinary=taxable_ordinary,
            deduction_used=total_deduction,
            senior_deduction=senior,
            deduction_type=deduction_type,
            marginal_rate=_marginal_rate(taxable_ordinary, ord_brackets),
            agi=agi,
        )
