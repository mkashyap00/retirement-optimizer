"""Projection of tax tables beyond the last published year.

Published tables always win. For a later year the table is projected from the
LATEST PUBLISHED table with ONE factor, ``(1 + inflation) ** (year - base)`` —
never by compounding an already-rounded projection — and each provision follows
its own statutory rule:

Federal (base: latest ``FEDERAL`` year)
  * ordinary and long-term-gain bracket thresholds: indexed, rounded down to a
    multiple of $25 (IRC §1(f)(7)); rates unchanged;
  * standard deduction and the age-65 addition: indexed, rounded down to a
    multiple of $50 (IRC §63(c)(4));
  * senior bonus deduction: not indexed; its 2025-2028 window and phase-out are
    statutory and carried unchanged;
  * NIIT thresholds: fixed by statute (IRC §1411), not indexed;
  * SALT cap: the enacted schedule (``statutory_salt``), not inflation.

IRMAA (base: latest ``IRMAA`` premium year)
  * tier MAGI thresholds: indexed, rounded to the nearest $1,000;
  * the TOP explicit tier ($500,000 single / $750,000 joint) is frozen through
    premium year 2027 and indexed from 2028 off that frozen amount (Social
    Security Act §1839(i)(5));
  * premium dollars are NOT projected (they follow Part B cost growth, not this
    formula), which understates future surcharges somewhat.

State (base: latest state CSV)
  * California only — ordinary brackets and standard deduction indexed,
    rounded to the nearest dollar (R&TC §17041(h)); the 1% Mental Health
    Services Tax threshold stays at $1,000,000 because it is a separate,
    unindexed surcharge (state.STATE_SURCHARGES).
  * Every other state keeps its latest published schedule. Their indexing
    rules differ and are not modelled; table provenance says so.

Social Security taxation thresholds ($25,000/$32,000 and $34,000/$44,000) are
fixed in law and live outside these tables.

The rate is the household's inflation assumption floored at zero — a planning
projection, not a forecast of the IRS's chained-CPI adjustments.
"""
from __future__ import annotations

import dataclasses
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from .types import Bracket, FederalTaxYear, IrmaaTier, IrmaaYear, SaltRule

_ONE = Decimal("1")
_ZERO = Decimal("0")

# Statutory IRMAA top-tier freeze: the $500k/$750k tier is not indexed for
# premium years through 2027 and is indexed from 2028.
IRMAA_TOP_TIER_FROZEN_THROUGH = 2027

# States whose projection is verified and modelled. Everything else is frozen.
INDEXED_STATES: frozenset[str] = frozenset({"CA"})


def factor(rate: Decimal, years: int) -> Decimal:
    """Cumulative growth over *years* at *rate* floored at zero."""
    if years <= 0:
        return _ONE
    rate = max(_ZERO, rate)
    return (_ONE + rate) ** years


def _floor_to(value: Decimal, step: int) -> Decimal:
    q = Decimal(step)
    return (value / q).to_integral_value(rounding=ROUND_FLOOR) * q


def _round_to(value: Decimal, step: int) -> Decimal:
    q = Decimal(step)
    return (value / q).to_integral_value(rounding=ROUND_HALF_UP) * q


def statutory_salt(year: int) -> SaltRule:
    """The enacted SALT cap schedule (OBBBA, IRC §164(b)(7)).

    $40,000 cap / $500,000 phase-down threshold for 2025, $40,400 / $505,000
    for 2026, each 101% of the prior year for 2027-2029, then the $10,000 cap
    with no phase-down from 2030. Married-filing-separately halves are not
    modelled (no MFS filing status). Not inflation-indexed.
    """
    floor = Decimal("10000")
    if year >= 2030:
        return SaltRule(cap={"single": floor, "joint": floor},
                        phase_down_start=Decimal("0"), phase_down_rate=_ZERO,
                        floor=floor)
    if year <= 2025:
        cap, start = Decimal("40000"), Decimal("500000")
    else:
        cap, start = Decimal("40400"), Decimal("505000")
        for _ in range(2027, year + 1):
            cap *= Decimal("1.01")
            start *= Decimal("1.01")
    return SaltRule(cap={"single": cap, "joint": cap}, phase_down_start=start,
                    phase_down_rate=Decimal("0.30"), floor=floor)


def _scale_brackets(brackets: list[Bracket], f: Decimal, step: int) -> list[Bracket]:
    return [
        Bracket(upper=None if b.upper is None else _floor_to(b.upper * f, step), rate=b.rate)
        for b in brackets
    ]


def project_federal_year(base: FederalTaxYear, year: int, rate: Decimal) -> FederalTaxYear:
    """*base* (a published year) projected to *year* at *rate*."""
    f = factor(rate, year - base.year)
    return dataclasses.replace(
        base,
        year=year,
        source=f"projected from {base.year} at {max(_ZERO, rate):.4f}/yr ({base.source})",
        brackets={k: _scale_brackets(v, f, 25) for k, v in base.brackets.items()},
        ltcg_brackets={k: _scale_brackets(v, f, 25) for k, v in base.ltcg_brackets.items()},
        standard_deduction={k: _floor_to(v * f, 50) for k, v in base.standard_deduction.items()},
        aged_addition={k: _floor_to(v * f, 50) for k, v in base.aged_addition.items()},
        salt=statutory_salt(year),
    )


def project_irmaa_year(base: IrmaaYear, premium_year: int, rate: Decimal) -> IrmaaYear:
    """*base* (a published premium year) projected to *premium_year* at *rate*.

    Thresholds only; premium amounts are carried unchanged.
    """
    f = factor(rate, premium_year - base.year)
    top_f = factor(rate, premium_year - max(base.year, IRMAA_TOP_TIER_FROZEN_THROUGH))
    tiers: dict[str, list[IrmaaTier]] = {}
    for status, rows in base.tiers.items():
        finite = [i for i, t in enumerate(rows) if t.magi_upper is not None]
        top = finite[-1] if finite else None
        out = []
        for i, t in enumerate(rows):
            if t.magi_upper is None:
                out.append(t)
                continue
            g = top_f if i == top else f
            out.append(dataclasses.replace(t, magi_upper=_round_to(t.magi_upper * g, 1000)))
        tiers[status] = out
    return dataclasses.replace(
        base,
        year=premium_year,
        source=f"thresholds projected from {base.year} at {max(_ZERO, rate):.4f}/yr "
               f"({base.source}); premiums not projected",
        tiers=tiers,
    )


def project_state_brackets(
    state: str, brackets: list[Bracket], base_year: int, year: int, rate: Decimal
) -> list[Bracket]:
    """Brackets for *state* in *year*; unchanged unless the state is modelled."""
    if state.upper() not in INDEXED_STATES:
        return brackets
    f = factor(rate, year - base_year)
    return [
        Bracket(upper=None if b.upper is None else _round_to(b.upper * f, 1), rate=b.rate)
        for b in brackets
    ]


def project_state_deduction(
    state: str, deduction: Decimal, base_year: int, year: int, rate: Decimal
) -> Decimal:
    if state.upper() not in INDEXED_STATES:
        return deduction
    return _round_to(deduction * factor(rate, year - base_year), 1)
