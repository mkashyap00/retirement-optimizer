"""State income tax engine.

Fixes:
  B7 — SS is NOT taxed by most states; only states in STATES_TAXING_SS include
        85% of SS in the state taxable income base.
  B8 — no DB access; consumes TaxRules provider only.

Algorithm:
  1. taxable_gross = ordinary + capital_gains_long
                     + (0.85 * social_security  if state in STATES_TAXING_SS  else 0)
  2. taxable = max(0, taxable_gross - state_standard_deduction(state, filing_status))
  3. tax = bracket_tax(taxable, state_brackets(state, filing_status))
  4. Add any fixed-threshold surcharge (STATE_SURCHARGES, e.g. California's
     1% Mental Health Services Tax over $1,000,000 of taxable income).
  5. Quantize to cents (ROUND_HALF_UP).
  6. Empty brackets (no-income-tax states) → Decimal('0').
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.data.tax_rules.rules import TaxRules
from src.data.tax_rules.state import STATE_SURCHARGES, STATES_TAXING_SS
from src.engines.tax.common import bracket_tax

_SS_INCLUSION_RATE = Decimal("0.85")


@dataclass(frozen=True)
class StateIncome:
    """Income components for state tax calculation."""

    ordinary: Decimal
    capital_gains_long: Decimal = Decimal("0")
    social_security: Decimal = Decimal("0")


class StateTaxEngine:
    """State income tax engine consuming TaxRules (no DB)."""

    def __init__(self, rules: TaxRules) -> None:
        self.rules = rules

    def calculate(
        self,
        income: StateIncome,
        state: str,
        filing_status: str,
        year: int | None = None,
        inflation: Decimal | None = None,
    ) -> Decimal:
        """Return state income tax for *income* in *state* for *filing_status*.

        Returns Decimal('0') for no-income-tax states (empty bracket list).
        """
        brackets = self.rules.state_brackets(state, filing_status, year, inflation)
        if not brackets:
            return Decimal("0")

        taxable_gross = self.gross_income(income, state)
        deduction = self.rules.state_standard_deduction(state, filing_status, year, inflation)
        taxable = max(Decimal("0"), taxable_gross - deduction)

        tax = bracket_tax(taxable, brackets)
        surcharge = STATE_SURCHARGES.get(state.upper())
        if surcharge is not None:
            threshold, rate = surcharge
            tax += max(Decimal("0"), taxable - threshold) * rate
        return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def gross_income(income: StateIncome, state: str) -> Decimal:
        """State income before the standard deduction (step 1 above)."""
        # SS inclusion: only if this state taxes Social Security
        ss_included = (
            income.social_security * _SS_INCLUSION_RATE
            if state.upper() in STATES_TAXING_SS
            else Decimal("0")
        )
        return income.ordinary + income.capital_gains_long + ss_included
