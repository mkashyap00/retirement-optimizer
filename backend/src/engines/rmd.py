"""RMD (Required Minimum Distribution) calculator engine.

Implements SECURE 2.0 RMD rules using the IRS Uniform Lifetime Table.
"""
from decimal import Decimal

from src.data.tax_rules.rules import TaxRules


class RMDCalculator:
    """Calculate Required Minimum Distributions for Traditional IRAs/401(k)s.

    Uses the IRS Uniform Lifetime Table via TaxRules facade.
    RMD starts at age 73 (SECURE 2.0 requirement).
    """

    def __init__(self, rules: TaxRules) -> None:
        """Initialize with TaxRules facade.

        Args:
            rules: TaxRules instance providing rmd_factor() lookup.
        """
        self.rules = rules

    def calculate(
        self,
        balance_traditional: Decimal,
        age: int,
        birth_year: int | None = None,
    ) -> Decimal:
        """Calculate the Required Minimum Distribution (RMD).

        Args:
            balance_traditional: Traditional IRA/401(k) balance in dollars —
                the prior year-end balance, per IRS rules.
            age: Age the owner attains during the distribution year.
            birth_year: Owner's birth year. Determines the SECURE 2.0 §107
                applicable age (73 for 1951-1959, 75 for 1960+). When omitted
                the legacy flat age of 73 is used.

        Returns:
            RMD amount rounded to nearest cent, or Decimal("0") if no RMD
            is required at this age.
        """
        factor = self.rules.rmd_factor(age, birth_year)
        if factor == Decimal("0"):
            return Decimal("0")
        return (balance_traditional / factor).quantize(Decimal("0.01"))
