"""Typed containers for tax rule data. All figures Decimal, all classes frozen."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Bracket:
    upper: Decimal | None  # None = top bracket (no upper bound)
    rate: Decimal


@dataclass(frozen=True)
class SeniorBonus:
    """OBBBA §70103 additional senior deduction (TY2025-2028).
    Applies per person 65+, regardless of itemizing; phases out at
    phaseout_rate per dollar of MAGI above phaseout_start."""
    amount_per_person: Decimal
    phaseout_start: dict[str, Decimal]
    phaseout_rate: Decimal
    first_year: int
    last_year: int


@dataclass(frozen=True)
class SaltRule:
    """OBBBA enhanced SALT cap with MAGI phase-down (never below floor)."""
    cap: dict[str, Decimal]
    phase_down_start: Decimal
    phase_down_rate: Decimal
    floor: Decimal


@dataclass(frozen=True)
class NiitRule:
    rate: Decimal
    threshold: dict[str, Decimal]


@dataclass(frozen=True)
class FederalTaxYear:
    year: int
    source: str
    brackets: dict[str, list[Bracket]]        # keys: "single", "joint"
    ltcg_brackets: dict[str, list[Bracket]]
    standard_deduction: dict[str, Decimal]
    # IRC §63(f) additional standard deduction for each filer or spouse aged
    # 65+, keyed by filing status: "single" is the unmarried amount, "joint"
    # the per-spouse amount. Permanent, and only with the standard deduction.
    aged_addition: dict[str, Decimal]
    senior_bonus: SeniorBonus
    salt: SaltRule
    niit: NiitRule


@dataclass(frozen=True)
class IrmaaTier:
    magi_upper: Decimal | None   # None = top tier
    part_b_monthly: Decimal      # total Part B premium at this tier
    part_d_monthly: Decimal      # Part D surcharge (IRMAA add-on only)


@dataclass(frozen=True)
class IrmaaYear:
    year: int                    # premium/coverage year (MAGI lookback is year-2)
    source: str
    part_b_standard: Decimal
    tiers: dict[str, list[IrmaaTier]]   # keys: "single", "joint"
