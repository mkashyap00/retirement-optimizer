"""Optimizer state/action/ledger dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine


class IncomeEntry(NamedTuple):
    """A single income stream with optional start/end year bounds."""

    # salary | pension | rental | interest | qualified_dividend | nonqualified_dividend
    category: str
    amount: Decimal
    start_year: int | None  # None = active from the beginning
    end_year: int | None  # None = active forever
    # "self" | "spouse" | "joint". Defaults to joint so schedules built before
    # ownership existed keep paying — without this a deceased spouse's salary
    # would go on arriving for the rest of the plan. `income_sources.owner` has
    # been in the schema all along; only the optimizer never carried it.
    owner: str = "joint"


_ZERO = Decimal("0")


def resolve_income(
    schedule: list[IncomeEntry],
    year: int,
    deceased_owner: str | None = None,
) -> dict[str, Decimal]:
    """Sum income by category for *year*, respecting start/end bounds.

    Returns a dict with keys: salary, pension, rental, interest,
    dividends_qualified, dividends_ordinary.

    ``deceased_owner`` ("self" or "spouse") drops that person's streams — their
    salary and pension stop at death. **Joint income continues**, which is the
    deliberate choice: joint rental or interest is usually survivorship
    property. A single-life pension that dies with its owner should be entered
    as owned by that person, not as joint.
    """
    totals: dict[str, Decimal] = {
        "salary": _ZERO,
        "pension": _ZERO,
        "rental": _ZERO,
        "interest": _ZERO,
        "dividends_qualified": _ZERO,
        "dividends_ordinary": _ZERO,
    }
    for entry in schedule:
        if entry.start_year is not None and year < entry.start_year:
            continue
        if entry.end_year is not None and year > entry.end_year:
            continue
        if deceased_owner is not None and entry.owner == deceased_owner:
            continue
        key = _CATEGORY_TO_KEY.get(entry.category, entry.category)
        totals[key] = totals.get(key, _ZERO) + entry.amount
    return totals


_CATEGORY_TO_KEY: dict[str, str] = {
    "qualified_dividend": "dividends_qualified",
    "nonqualified_dividend": "dividends_ordinary",
}


@dataclass
class State:
    """Mutable state snapshot for a single year in the simulation."""

    year: int
    age_self: int
    age_spouse: int | None
    balance_taxable: Decimal
    balance_traditional: Decimal
    balance_roth: Decimal
    basis_taxable: Decimal
    filing_status: str  # "single" | "joint"
    state_code: str
    basis_traditional: Decimal = Decimal("0")  # Form 8606 after-tax basis in trad IRA
    # The part of balance_traditional in the SPOUSE's IRAs; the rest is self's.
    # Each owner's RMD is their own balance over the factor for their own age,
    # so the household total alone cannot price them. Zero once widowed: the
    # survivor (always the `self` slot) rolls the deceased's IRA into their own.
    balance_traditional_spouse: Decimal = Decimal("0")
    # income streams for THIS year (pre-action)
    salary: Decimal = Decimal("0")
    pension: Decimal = Decimal("0")
    rental: Decimal = Decimal("0")
    social_security: Decimal = Decimal("0")
    interest: Decimal = Decimal("0")
    dividends_qualified: Decimal = Decimal("0")
    dividends_ordinary: Decimal = Decimal("0")
    # Net capital gains already realized THIS year by sales made before the
    # plan starts (negative = a net loss), apart from the plan's own sales.
    # Set for the first year only and zero after it. They are tax figures, not
    # cash: the sale proceeds are already in the entered balances.
    realized_st_gain: Decimal = Decimal("0")
    realized_lt_gain: Decimal = Decimal("0")
    # Capital loss carried INTO this year (>= 0): entered for the first year,
    # then whatever the year before could not deduct (capital_gains.py).
    loss_carryover_st: Decimal = Decimal("0")
    loss_carryover_lt: Decimal = Decimal("0")
    # The state's carryover: the federal one for most states; CA and WI figure
    # their own on state income, so it drifts; PA and NJ allow none.
    state_loss_carryover_st: Decimal = Decimal("0")
    state_loss_carryover_lt: Decimal = Decimal("0")
    # status
    medicare_self: bool = False
    medicare_spouse: bool = False
    magi_two_years_ago: Decimal = Decimal("0")
    magi_last_year: Decimal = Decimal("0")
    # Roth 5-year rule: earliest year any Roth account was opened (None = unknown)
    roth_earliest_opened_year: int | None = None
    # --- Dynamic spending (guardrails) -------------------------------------
    # Guardrail cuts PERSIST, so the current spending level has to travel with
    # the state rather than being recomputed from Settings each year. Both are
    # seeded by the first simulate_year call that sees None, from the same
    # starting state for every policy — which is what keeps the comparison fair.
    #
    # spending_base is in TODAY's dollars (inflation is applied on top), so a
    # 10% guardrail cut stays a 10% cut in real terms for the rest of the plan.
    spending_base: Decimal | None = None
    # The Guyton-Klinger anchor: the withdrawal rate in year 0. Guardrails are
    # a band around THIS, not around an absolute rate like 4%.
    initial_withdrawal_rate: Decimal | None = None


@dataclass(frozen=True)
class Action:
    """Immutable action representing withdrawals/conversions for a year."""

    conversion: Decimal
    withdrawal_taxable: Decimal = Decimal("0")
    withdrawal_traditional: Decimal = Decimal("0")  # beyond RMD
    withdrawal_roth: Decimal = Decimal("0")
    action_id: str = "none"  # "none" | "fill_12" | "fill_22" | ... (set by actions.py)


@dataclass(frozen=True)
class YearLedger:
    """Immutable full accounting for one simulated year."""

    year: int
    age_self: int
    age_spouse: int | None
    rmd: Decimal
    conversion: Decimal
    withdrawal_taxable: Decimal
    withdrawal_traditional: Decimal
    withdrawal_roth: Decimal
    realized_gains: Decimal
    agi: Decimal
    magi: Decimal
    federal_tax: Decimal
    state_tax: Decimal
    irmaa: Decimal
    total_tax: Decimal
    net_spendable: Decimal
    # What the plan TRIED to fund this year. Under the default "fixed" rule
    # this is the inflated target; under guardrails it is the reduced amount
    # the rule allowed, so `net_spendable >= required_spending` remains the
    # funding identity either way.
    required_spending: Decimal
    # Involuntary gap: max(0, required_spending - net_spendable). Zero on a year
    # the plan funded, even if the rule had already cut that year's spending.
    shortfall: Decimal
    marginal_rate: Decimal
    end_taxable: Decimal
    end_traditional: Decimal
    end_roth: Decimal
    # Per-year tax derivation (worksheet lines) for the Tax Audit sheet;
    # None only for ledgers built outside simulate_year (legacy tests).
    audit: dict | None = None
    # --- Dynamic spending ---------------------------------------------------
    # The un-cut goal: Settings.required_spending inflated to this year,
    # ignoring any guardrail cut. Equals required_spending under "fixed".
    # Defaults to 0 only for ledgers hand-built in legacy tests.
    target_spending: Decimal = Decimal("0")
    # Voluntary reduction the spending rule chose: target_spending -
    # required_spending, >= 0. Real lost consumption, priced by the objective
    # at discretionary_shortfall_weight rather than treated as free safety.
    discretionary_cut: Decimal = Decimal("0")


@dataclass(frozen=True)
class Settings:
    """Immutable simulation configuration and economic assumptions."""

    start_year: int
    required_spending: Decimal  # annual, today's dollars, after-tax
    inflation: Decimal = Decimal("0.03")
    nominal_return: Decimal = Decimal("0.06")
    discount_rate: Decimal = Decimal("0.02")
    simulation_years: int = 30
    heir_tax_rate: Decimal = Decimal("0.25")
    dividend_yield: Decimal = Decimal("0.02")  # taxable-account tax drag
    # Social Security claiming config. When PIAs are provided, simulate_year
    # activates each person's benefit in the year they reach their claim age.
    # PIAs are in START-YEAR dollars and grow by the COLA below every year from
    # start_year, before and after claiming alike (an unclaimed PIA is indexed
    # too). When absent (None), State.social_security is carried forward
    # unchanged.
    ss_pia_self: Decimal | None = None
    ss_claim_age_self: int | None = None
    ss_pia_spouse: Decimal | None = None
    ss_claim_age_spouse: int | None = None
    # Whether each person is already receiving benefits. True: the stored claim
    # age is an actual claim (≤ today's age). False: it is a plan (≥ today's
    # age, or 70 for someone over 70 who has not filed). None: unknown — the
    # legacy reading infers "receiving" from age ≥ claim age, which fixed-age
    # runs label and the joint claim-age search refuses (see claiming.py).
    ss_receiving_self: bool | None = None
    ss_receiving_spouse: bool | None = None
    # Projected annual Social Security COLA. None = follow `inflation`, floored
    # at 0 (SSA pays no COLA when the price index falls). Decimal("0") holds
    # benefits flat in nominal terms — the behaviour before October 2026.
    # A planning assumption, not a forecast of the statutory CPI-W COLA.
    ss_cola: Decimal | None = None
    # λ — shortfall COST WEIGHT, not risk aversion. How many dollars of
    # estate one PV dollar of unfunded essential spending costs. The objective
    # (evaluate.objective_value) is PV(heir-adjusted estate) − λ·shortfall_pv −
    # λ_d·discretionary_shortfall_pv, for search and Monte Carlo alike.
    shortfall_weight: Decimal = Decimal("1")
    # Birth year of the traditional-account owner. Drives the SECURE 2.0 §107
    # RMD applicable age (73 for 1951-1959, 75 for 1960+). It cannot be derived
    # safely from year - age: for a birthday later in the calendar year that is
    # off by one, which is exactly wrong at the 1959/1960 cohort boundary.
    birth_year_self: int | None = None
    # Birth year of the spouse. Needed for two things once a death is modelled:
    # the SECURE 2.0 RMD applicable age when SELF dies and the spouse survives
    # (the 1959/1960 boundary is worth two full years of forced distributions),
    # and the deceased's age at death when pricing the survivor benefit.
    birth_year_spouse: int | None = None
    income_schedule: list[IncomeEntry] = field(default_factory=list)
    # The tax year of capital gains entered for an earlier year than the
    # plan's first: they were not applied, and the report says so.
    stale_capital_gains_year: int | None = None

    # --- Death transition (a what-if, never a default) ----------------------
    # Calendar year of the FIRST death. None = nobody dies, which is today's
    # behaviour and stays the default for every plan of record: modelling a
    # death requires guessing a year, and that guess belongs in a comparison
    # the user asked for, not silently inside their plan.
    #
    # Timing: a death during year Y still files JOINTLY for Y (matching IRS
    # treatment of the year of death) and single from Y+1. That falls out of
    # applying the transition when building `next_state`.
    first_death_year: int | None = None
    # Who dies first. Do not assume self outlives spouse.
    first_death_is_spouse: bool = True

    # --- Dynamic spending ---------------------------------------------------
    # "fixed"      — spend the inflated target every year, come what may.
    # "guardrails" — Guyton-Klinger: watch the withdrawal rate and cut (or
    #                restore) the spending base when it drifts out of band.
    spending_rule: str = "fixed"
    # Essential spending, today's dollars, after-tax — the part that is not
    # negotiable. Two jobs: guardrail cuts never go below it, and it splits the
    # consumption gap into a discretionary tier (floor..target, priced at
    # discretionary_shortfall_weight) and an essential tier (below the floor,
    # priced at the full shortfall_weight).
    #
    # None means "no discretionary band": the floor IS the target, every gap is
    # essential, and pricing is identical to the pre-Step-5 behaviour. That is
    # deliberate — a user who has not told us what is negotiable gets the
    # strict reading, not a generous one.
    spending_floor: Decimal | None = None
    # λ_d — cost of one PV dollar of spending given up while still above the
    # essential floor. Below λ because trimming travel is genuinely less bad
    # than not affording care; ABOVE zero because it is not free, which is the
    # whole reason dynamic spending cannot simply be waved through as safety.
    discretionary_shortfall_weight: Decimal = Decimal("0.5")
    # Guyton-Klinger's published parameters: act when the current withdrawal
    # rate sits more than 20% away from the initial rate, and move spending by
    # 10% when you do. Exposed for testing rather than for the UI.
    guardrail_band: Decimal = Decimal("0.20")
    guardrail_adjustment: Decimal = Decimal("0.10")


@dataclass(frozen=True)
class Constraints:
    """Immutable constraints on action selection."""

    irmaa_policy: str = "soft"  # "ignore" | "soft" | "strict" | "avoid"
    conversion_window: str = "anytime"  # "anytime" | "pre_medicare" | "pre_rmd" | "pre_ss"
    marginal_rate_limit: Decimal | None = None
    min_conversion: Decimal = Decimal("1000")
    max_conversion_per_year: Decimal | None = None
    target_estate: Decimal | None = None
    preserve_taxable: bool = False


@dataclass(frozen=True)
class Engines:
    """Immutable bundle of tax/benefit engines."""

    federal: FederalTaxEngine
    state: StateTaxEngine
    irmaa: IRMAACalculator
    rmd: RMDCalculator
    ss: SocialSecurityCalculator
    rules: TaxRules
