"""Federal tax parameters, one FederalTaxYear per tax year.

Sources:
  TY2025 brackets/LTCG: Rev. Proc. 2024-40 §2.01, §2.03
  TY2025 standard deduction: OBBBA (P.L. 119-21) §70102 — $15,750 / $31,500
  Age-65 additional standard deduction, IRC §63(f): TY2025 $2,000 unmarried /
    $1,600 per married spouse (Rev. Proc. 2024-40 §3.15(3)); TY2026 $2,050 /
    $1,650 (Rev. Proc. 2025-32 §4.14(3))
  Senior bonus deduction: OBBBA §70103 — $6,000/person 65+, 6% phaseout over
    $75,000 (single) / $150,000 (MFJ) MAGI, TY2025–TY2028
  SALT: OBBBA §70120 (IRC §164(b)(7)) — $40,000 cap / $500,000 phase-down
    threshold for 2025, $40,400 / $505,000 for 2026 (IRS Pub. 505 (2026)),
    +1%/yr through 2029, phased down 30% of MAGI over the threshold, floor
    $10,000; reverts to $10,000 in 2030. Built by indexing.statutory_salt so
    published and projected years share one schedule. (The 2026 threshold was
    $500,000 here until October 2026.)
  NIIT: IRC §1411 (thresholds not inflation-indexed)
"""
from decimal import Decimal as D

from .indexing import statutory_salt
from .types import Bracket, FederalTaxYear, NiitRule, SeniorBonus

_SENIOR_BONUS = SeniorBonus(
    amount_per_person=D("6000"),
    phaseout_start={"single": D("75000"), "joint": D("150000")},
    phaseout_rate=D("0.06"),
    first_year=2025, last_year=2028,
)
_NIIT = NiitRule(rate=D("0.038"), threshold={"single": D("200000"), "joint": D("250000")})


def _b(*pairs):  # (upper|None, rate) shorthand
    return [Bracket(None if u is None else D(u), D(r)) for u, r in pairs]


FEDERAL: dict[int, FederalTaxYear] = {
    2025: FederalTaxYear(
        year=2025,
        source="Rev. Proc. 2024-40; OBBBA P.L. 119-21",
        brackets={
            "single": _b(("11925", "0.10"), ("48475", "0.12"), ("103350", "0.22"),
                         ("197300", "0.24"), ("250525", "0.32"), ("626350", "0.35"),
                         (None, "0.37")),
            "joint": _b(("23850", "0.10"), ("96950", "0.12"), ("206700", "0.22"),
                        ("394600", "0.24"), ("501050", "0.32"), ("751600", "0.35"),
                        (None, "0.37")),
        },
        ltcg_brackets={
            "single": _b(("48350", "0"), ("533400", "0.15"), (None, "0.20")),
            "joint": _b(("96700", "0"), ("600050", "0.15"), (None, "0.20")),
        },
        standard_deduction={"single": D("15750"), "joint": D("31500")},
        aged_addition={"single": D("2000"), "joint": D("1600")},
        senior_bonus=_SENIOR_BONUS,
        salt=statutory_salt(2025),
        niit=_NIIT,
    ),
    2026: FederalTaxYear(
        year=2026,
        source="Rev. Proc. 2025-32 (verified 2026-07-02 vs irs.gov + taxfoundation.org); OBBBA P.L. 119-21",  # noqa: E501
        brackets={
            "single": _b(("12400", "0.10"), ("50400", "0.12"), ("105700", "0.22"),
                         ("201775", "0.24"), ("256225", "0.32"), ("640600", "0.35"),
                         (None, "0.37")),
            "joint": _b(("24800", "0.10"), ("100800", "0.12"), ("211400", "0.22"),
                        ("403550", "0.24"), ("512450", "0.32"), ("768700", "0.35"),
                        (None, "0.37")),
        },
        ltcg_brackets={
            "single": _b(("49450", "0"), ("545500", "0.15"), (None, "0.20")),
            "joint": _b(("98900", "0"), ("613700", "0.15"), (None, "0.20")),
        },
        standard_deduction={"single": D("16100"), "joint": D("32200")},
        aged_addition={"single": D("2050"), "joint": D("1650")},
        senior_bonus=_SENIOR_BONUS,
        salt=statutory_salt(2026),
        niit=_NIIT,
    ),
}
