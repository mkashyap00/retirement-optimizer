"""
IRS Required Minimum Distribution (RMD) data.

Source: IRS Publication 590-B, Table III — Uniform Lifetime Table
(applies to distribution calendar years beginning on or after January 1, 2022)

Ages 73–120 and their corresponding distribution period factors.
"""

from decimal import Decimal

# SECURE Act 2.0 raised the RMD start age from 72 to 73 (effective 2023).
# Retained as the fallback when a birth year is unknown; prefer
# ``applicable_rmd_age()``, which implements the full statutory rule.
RMD_START_AGE: int = 73


def applicable_rmd_age(birth_year: int) -> int:
    """Return the SECURE 2.0 §107 "applicable age" for a birth year.

    IRC §401(a)(9)(C)(v) as amended:
      * 73 for an individual attaining 72 after 2022 and 73 before 2033
        (born 1951-1959);
      * 75 for an individual attaining 74 after 2032 (born 1960 or later).

    The statute's two clauses overlap for the 1959 cohort — a genuine drafting
    glitch. The IRS proposed regulations (REG-103529-23, July 2024) resolve it
    to 73, which is what this returns.

    Anyone born 1950 or earlier reached their required beginning date under the
    pre-SECURE-2.0 age of 72; they are decades past it, but the branch is kept
    so the function is total.
    """
    if birth_year <= 1950:
        return 72
    if birth_year <= 1959:
        return 73
    return 75

# Uniform Lifetime Table — ages 73 through 120.
# Source: IRS Pub 590-B, Appendix B, Table III (Uniform Lifetime).
# Verified 2026-08-23 against the PRIMARY source: Publication 590-B (2025),
# page 67, extracted from https://www.irs.gov/pub/irs-pdf/p590b.pdf and diffed
# factor-by-factor. All 48 factors (ages 73-120) matched exactly.
# (The table also lists age 72 = 27.4, omitted here: no one still has an
# applicable age of 72 — see applicable_rmd_age above.)
UNIFORM_LIFETIME: dict[int, Decimal] = {
    73: Decimal("26.5"),
    74: Decimal("25.5"),
    75: Decimal("24.6"),
    76: Decimal("23.7"),
    77: Decimal("22.9"),
    78: Decimal("22.0"),
    79: Decimal("21.1"),
    80: Decimal("20.2"),
    81: Decimal("19.4"),
    82: Decimal("18.5"),
    83: Decimal("17.7"),
    84: Decimal("16.8"),
    85: Decimal("16.0"),
    86: Decimal("15.2"),
    87: Decimal("14.4"),
    88: Decimal("13.7"),
    89: Decimal("12.9"),
    90: Decimal("12.2"),
    91: Decimal("11.5"),
    92: Decimal("10.8"),
    93: Decimal("10.1"),
    94: Decimal("9.5"),
    95: Decimal("8.9"),
    96: Decimal("8.4"),
    97: Decimal("7.8"),
    98: Decimal("7.3"),
    99: Decimal("6.8"),
    100: Decimal("6.4"),
    101: Decimal("6.0"),
    102: Decimal("5.6"),
    103: Decimal("5.2"),
    104: Decimal("4.9"),
    105: Decimal("4.6"),
    106: Decimal("4.3"),
    107: Decimal("4.1"),
    108: Decimal("3.9"),
    109: Decimal("3.7"),
    110: Decimal("3.5"),
    111: Decimal("3.4"),
    112: Decimal("3.3"),
    113: Decimal("3.1"),
    114: Decimal("3.0"),
    115: Decimal("2.9"),
    116: Decimal("2.8"),
    117: Decimal("2.7"),
    118: Decimal("2.5"),
    119: Decimal("2.3"),
    120: Decimal("2.0"),
}
