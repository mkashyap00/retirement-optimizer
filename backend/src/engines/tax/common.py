"""Shared tax-computation helpers used by multiple engines."""
from __future__ import annotations

from decimal import Decimal

from src.data.tax_rules.types import Bracket


def bracket_tax(taxable: Decimal, brackets: list[Bracket]) -> Decimal:
    """Walk *brackets* accumulating tax on *taxable* income.

    The final bracket must have ``upper=None`` (top bracket, no ceiling).
    Returns Decimal('0') when *taxable* is non-positive or *brackets* is empty.
    """
    if taxable <= Decimal("0") or not brackets:
        return Decimal("0")
    tax = Decimal("0")
    prev_upper = Decimal("0")
    for bracket in brackets:
        if taxable <= prev_upper:
            break
        if bracket.upper is None:
            tax += (taxable - prev_upper) * bracket.rate
            break
        in_bracket = min(taxable, bracket.upper) - prev_upper
        if in_bracket > Decimal("0"):
            tax += in_bracket * bracket.rate
        prev_upper = bracket.upper
    return tax
