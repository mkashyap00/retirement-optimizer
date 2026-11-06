"""Social Security full retirement age (FRA) by birth year.

FRA is not a flat 67. It is 67 only for those born 1960 or later; the 1955-1959
cohorts reach it at 66 plus 2 to 10 months, and survivor benefits use a
separate table shifted two years later. Using 67 for everyone treated someone
born in 1958 who claims at their real FRA (66 and 8 months) as claiming early,
and gave a 67-year-old claimant none of the delayed credits they had earned.

Sources (SSA):
  * Retirement and spousal benefits — "Benefits Planner: Retirement | Born in
    1960 or later / Full Retirement Age",
    https://www.ssa.gov/benefits/retirement/planner/agereduction.html
  * Survivor benefits — "Survivors Planner: Full Retirement Age for Survivors",
    https://www.ssa.gov/benefits/survivors/survivorchartred.html

Simplification: SSA treats anyone born on 1 January as born the previous year.
Only the birth YEAR is stored here, so that one-day edge is not modelled.

Values are years as an exact Decimal (66 and 8 months = 66 + 8/12); the
benefit engine converts the gap to whole months.
"""
from __future__ import annotations

from decimal import Decimal

_TWELVE = Decimal("12")
# Without a birth year, keep the long-standing default rather than guess.
DEFAULT_FRA = Decimal("67")


def _years_months(years: int, months: int) -> Decimal:
    return Decimal(years) + Decimal(months) / _TWELVE


def full_retirement_age(birth_year: int | None) -> Decimal:
    """FRA for retirement and spousal benefits."""
    if birth_year is None:
        return DEFAULT_FRA
    if birth_year <= 1937:
        return _years_months(65, 0)
    if birth_year <= 1942:
        return _years_months(65, 2 * (birth_year - 1937))
    if birth_year <= 1954:
        return _years_months(66, 0)
    if birth_year <= 1959:
        return _years_months(66, 2 * (birth_year - 1954))
    return _years_months(67, 0)


def survivor_full_retirement_age(birth_year: int | None) -> Decimal:
    """FRA for survivor benefits: the same steps, two birth years later."""
    if birth_year is None:
        return DEFAULT_FRA
    if birth_year <= 1939:
        return _years_months(65, 0)
    if birth_year <= 1944:
        return _years_months(65, 2 * (birth_year - 1939))
    if birth_year <= 1956:
        return _years_months(66, 0)
    if birth_year <= 1961:
        return _years_months(66, 2 * (birth_year - 1956))
    return _years_months(67, 0)
