"""
Pydantic v2 request/response models for the retirement optimizer API.

Domain validators are embedded directly in the models (no separate validator
module needed). The joint-requires-spouse-birthdate rule was originally in
backend/src/validators/household.py (now deleted).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from src.data.tax_rules.state import SUPPORTED_STATES

# ---------------------------------------------------------------------------
# HouseholdIn
# ---------------------------------------------------------------------------


class HouseholdIn(BaseModel):
    """Household descriptor for a planning request."""

    filing_status: Literal["single", "joint"]
    self_birth_date: date
    spouse_birth_date: date | None = None
    state: str
    nickname: str | None = None
    self_death_age: int | None = None
    spouse_death_age: int | None = None

    @field_validator("self_death_age", "spouse_death_age")
    @classmethod
    def death_age_within_bounds(cls, v: int | None) -> int | None:
        """Planning-horizon end age must be a plausible value (40–120)."""
        if v is None:
            return None
        if not (40 <= v <= 120):
            raise ValueError("death age must be between 40 and 120")
        return v

    @field_validator("state")
    @classmethod
    def state_must_be_two_uppercase(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z]{2}", v):
            raise ValueError(
                "state must be exactly 2 uppercase letters (e.g. 'CA', 'NY')"
            )
        # Two letters is not enough: an unknown code gets no state tax at all.
        if v not in SUPPORTED_STATES:
            raise ValueError(f"state {v!r} is not a US state or DC")
        return v

    @field_validator("nickname", mode="before")
    @classmethod
    def validate_nickname(cls, v: str | None) -> str | None:
        """Strip whitespace; empty-after-strip becomes None; max 60 chars."""
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        if len(stripped) > 60:
            raise ValueError("nickname must be 60 characters or fewer")
        return stripped

    @model_validator(mode="after")
    def joint_requires_spouse_birthdate(self) -> HouseholdIn:
        """Port of validators/household.py joint-requires-spouse rule."""
        if self.filing_status == "joint" and self.spouse_birth_date is None:
            raise ValueError(
                "spouse_birth_date is required when filing_status is 'joint'"
            )
        return self

    @model_validator(mode="after")
    def spouse_death_age_requires_spouse(self) -> HouseholdIn:
        """A spouse death age only makes sense when a spouse is present."""
        if self.spouse_death_age is not None and self.spouse_birth_date is None:
            raise ValueError(
                "spouse_death_age requires spouse_birth_date to be set"
            )
        return self


# ---------------------------------------------------------------------------
# AccountIn
# ---------------------------------------------------------------------------


class AccountIn(BaseModel):
    """A financial account belonging to a household."""

    account_type: Literal["taxable", "traditional", "roth"]
    owner: Literal["self", "spouse", "joint"]
    balance: Decimal = Field(ge=0)
    basis: Decimal | None = None
    roth_opened_year: int | None = None

    @model_validator(mode="after")
    def validate_basis_rules(self) -> AccountIn:
        """
        - taxable: basis is required, and may exceed the balance -- that is
          an ordinary unrealized loss (sales from it realize no taxable gain)
        - traditional: basis is optional (Form 8606 after-tax; defaults to 0
          downstream) and cannot exceed the balance
        - both: when set, basis must be >= 0
        - roth: basis not relevant, no constraint
        """
        if self.account_type == "taxable" and self.basis is None:
            raise ValueError(
                "basis is required for taxable accounts (cost basis for cap-gains calc)"
            )
        if self.basis is not None:
            if self.basis < Decimal("0"):
                raise ValueError("basis must be >= 0")
            if self.account_type == "traditional" and self.basis > self.balance:
                raise ValueError(
                    "basis must be <= balance "
                    f"(got basis={self.basis}, balance={self.balance})"
                )
        return self


# ---------------------------------------------------------------------------
# IncomeIn
# ---------------------------------------------------------------------------


class IncomeIn(BaseModel):
    """An income stream (salary, pension, rental, interest, dividends) for planning."""

    category: Literal[
        "salary", "pension", "rental", "interest", "qualified_dividend", "nonqualified_dividend"
    ]
    owner: Literal["self", "spouse", "joint"]
    amount: Decimal = Field(ge=0)
    start_year: int | None = None
    end_year: int | None = None

    @model_validator(mode="after")
    def start_not_after_end(self) -> IncomeIn:
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.start_year > self.end_year
        ):
            raise ValueError(
                f"start_year ({self.start_year}) is after end_year ({self.end_year})"
            )
        return self


# ---------------------------------------------------------------------------
# CapitalGainsIn
# ---------------------------------------------------------------------------


class CapitalGainsIn(BaseModel):
    """Capital gains already realized in *tax_year*, and the capital loss
    carried into it from the year before.

    Tax figures only, never cash: the proceeds of those sales are already in
    the account balances. They apply when *tax_year* is the plan's first year;
    a plan run in a later year ignores them and says so.
    """

    tax_year: int = Field(ge=2000, le=2100)
    # Net for the year so far; negative is a net loss.
    short_term: Decimal = Field(Decimal("0"), ge=-1_000_000_000, le=1_000_000_000)
    long_term: Decimal = Field(Decimal("0"), ge=-1_000_000_000, le=1_000_000_000)
    # Loss carried in from the prior year's return (Schedule D lines 6 and 14).
    carryover_short_term: Decimal = Field(Decimal("0"), ge=0)
    carryover_long_term: Decimal = Field(Decimal("0"), ge=0)


# ---------------------------------------------------------------------------
# SettingsIn
# ---------------------------------------------------------------------------


class SettingsIn(BaseModel):
    """Economic assumptions and Social Security parameters."""

    required_spending: Decimal = Field(gt=0)
    # Rates as fractions. Bounds are generous -- room for a deflation or a
    # bear-market what-if -- but exclude a percentage typed as a whole number.
    inflation: Decimal = Field(Decimal("0.03"), ge=Decimal("-0.1"), le=1)
    nominal_return: Decimal = Field(Decimal("0.06"), ge=Decimal("-0.5"), le=1)
    ss_pia_self: Decimal = Field(ge=0)
    # None = no age chosen: allowed only for a claim-age search, which then has
    # no "your ages" comparison (claiming.require_claim_ages refuses the rest).
    ss_claim_age_self: int | None = Field(67, ge=62, le=70)
    ss_pia_spouse: Decimal | None = Field(None, ge=0)
    ss_claim_age_spouse: int | None = None
    # Already receiving benefits? None = not stated (the legacy reading). The
    # claim age must agree with it: see claiming.receiving_error.
    ss_receiving_self: bool | None = None
    ss_receiving_spouse: bool | None = None
    # Marginal income-tax rate heirs would pay on an inherited traditional
    # IRA — drives the estate adjustment (a traditional dollar counts as
    # (1 − rate) in the objective). Default 25%.
    heir_tax_rate: Decimal | None = Field(None, ge=0, le=1)
    # Deprecated and ignored by the optimizer since October 2026: the objective
    # is PV(after-tax estate) less the weighted consumption gap, with taxes
    # reported rather than scored. Still accepted and stored so plans and run
    # snapshots saved earlier keep loading and keep their label.
    estate_weight: Decimal | None = Field(None, ge=0, le=1)
    # Dynamic spending. "fixed" spends the inflated target every year;
    # "guardrails" cuts (and later restores) it as the withdrawal rate drifts.
    spending_rule: Literal["fixed", "guardrails"] | None = None
    # Essential spending, today's dollars, after-tax. Guardrail cuts stop here,
    # and it splits the consumption gap into discretionary and essential tiers.
    # None = no discretionary band, the strict pre-dynamic-spending reading.
    spending_floor: Decimal | None = Field(None, ge=0)
    # Projected annual Social Security COLA as a fraction. None = follow the
    # inflation assumption (floored at 0); 0 = benefits flat in nominal terms.
    ss_cola: Decimal | None = Field(None, ge=0, le=Decimal("0.2"))

    @field_validator("ss_claim_age_self", mode="before")
    @classmethod
    def validate_self_claim_age(cls, v: int | None) -> int | None:
        if v is not None and (v < 62 or v > 70):
            raise ValueError(
                f"ss_claim_age_self must be between 62 and 70, got {v}"
            )
        return v

    @field_validator("ss_claim_age_spouse", mode="before")
    @classmethod
    def validate_spouse_claim_age(cls, v: int | None) -> int | None:
        if v is not None and (v < 62 or v > 70):
            raise ValueError(
                f"ss_claim_age_spouse must be between 62 and 70, got {v}"
            )
        return v


# ---------------------------------------------------------------------------
# ConstraintsIn
# ---------------------------------------------------------------------------


class ConstraintsIn(BaseModel):
    """Optimization constraints and policy preferences."""

    irmaa_policy: Literal["ignore", "soft", "strict", "avoid"] = "soft"
    conversion_window: Literal[
        "anytime", "pre_medicare", "pre_rmd", "pre_ss"
    ] = "anytime"
    marginal_rate_limit: Decimal | None = Field(None, ge=0, le=1)
    max_conversion_per_year: Decimal | None = Field(None, ge=0)
    target_estate: Decimal | None = Field(None, ge=0)
    preserve_taxable: bool = False


# ---------------------------------------------------------------------------
# HouseholdPayload (composite request body)
# ---------------------------------------------------------------------------


class HouseholdPayload(BaseModel):
    """Full planning request payload."""

    household: HouseholdIn
    accounts: list[AccountIn]
    income: list[IncomeIn] = Field(default_factory=list)
    settings: SettingsIn
    constraints: ConstraintsIn = Field(default_factory=ConstraintsIn)
    capital_gains: CapitalGainsIn | None = None

    @model_validator(mode="after")
    def spouse_items_need_a_spouse(self) -> HouseholdPayload:
        """A spouse-owned account or income has no owner without a spouse:
        no age for its RMDs, no death to stop it at."""
        if self.household.spouse_birth_date is not None:
            return self
        if any(a.owner == "spouse" for a in self.accounts) or any(
            i.owner == "spouse" for i in self.income
        ):
            raise ValueError(
                "an account or income owned by the spouse needs spouse_birth_date"
            )
        return self

    @model_validator(mode="after")
    def claim_age_agrees_with_receiving(self) -> HouseholdPayload:
        """An actual claim cannot lie in the future, nor a planned one in the
        past. Ages are this calendar year's, as assembly computes them."""
        from src.optimization.claiming import receiving_error

        year = date.today().year
        h, s = self.household, self.settings
        people = [("self", h.self_birth_date, s.ss_claim_age_self, s.ss_receiving_self)]
        if h.spouse_birth_date is not None:
            people.append(
                ("spouse", h.spouse_birth_date, s.ss_claim_age_spouse, s.ss_receiving_spouse)
            )
        for person, birth, claim, receiving in people:
            err = receiving_error(person, year - birth.year, claim, receiving)
            if err:
                raise ValueError(err)
        return self


# ---------------------------------------------------------------------------
# OptimizeRequest
# ---------------------------------------------------------------------------


# Upper bound on a run's scenarios: ten times the default.
MAX_MONTE_CARLO_RUNS = 3000


class OptimizeRequest(BaseModel):
    """Trigger an optimize run against an already-stored household."""

    household_id: str
    # Raised from 100 with adaptive staging (score_policies_adaptive): only
    # the contenders are carried to the full count, so the extra precision
    # costs far less than 3x. At 100 runs a 70% success reading carried
    # ~+/-9 points and moved 6-8 points on the random seed alone.
    # 0 = deterministic only. The cap keeps a typo from tying up the server.
    monte_carlo_runs: int = Field(300, ge=0, le=MAX_MONTE_CARLO_RUNS)
    # Force a specific policy (e.g. "fill_22") instead of letting the search
    # pick — used to inspect an alternative's full year-by-year plan.
    policy_id: str | None = None
    # Run at these claim ages instead of the stored ones (None = stored). The
    # stored plan is not changed, and an ineligible age is a 422 (see
    # claiming.check_pinned_ages).
    ss_claim_age_self: int | None = Field(None, ge=62, le=70)
    ss_claim_age_spouse: int | None = Field(None, ge=62, le=70)


class ClaimAgeControlIn(BaseModel):
    """One person's claim age in a joint search: ``fixed`` at *age* (None =
    the stored age) or ``search`` over every eligible age."""

    mode: Literal["fixed", "search"] = "fixed"
    age: int | None = Field(None, ge=62, le=70)


class ClaimSearchIn(BaseModel):
    self_: ClaimAgeControlIn = Field(default_factory=ClaimAgeControlIn, alias="self")
    spouse: ClaimAgeControlIn = Field(default_factory=ClaimAgeControlIn)

    model_config = {"populate_by_name": True}


class ClaimPreviewIn(BaseModel):
    """What the claim-age preview needs from an unsaved plan: ages, salaries
    and the Social Security answers -- nothing financial."""

    household: HouseholdIn
    income: list[IncomeIn] = Field(default_factory=list)
    ss_pia_self: Decimal | None = Field(None, ge=0)
    ss_claim_age_self: int | None = Field(None, ge=62, le=70)
    ss_receiving_self: bool | None = None
    ss_pia_spouse: Decimal | None = Field(None, ge=0)
    ss_claim_age_spouse: int | None = Field(None, ge=62, le=70)
    ss_receiving_spouse: bool | None = None


class OptimizeJobRequest(BaseModel):
    """Start a background joint claim-age + conversion search."""

    household_id: str
    monte_carlo_runs: int = Field(300, ge=0, le=MAX_MONTE_CARLO_RUNS)
    # Paths every candidate is screened on before finalists get the full
    # budget; normalised to at most monte_carlo_runs.
    stage1_runs: int = Field(50, ge=1, le=MAX_MONTE_CARLO_RUNS)
    # Schedules per claim pair carried into Monte Carlo (plus `none`).
    per_scenario_breadth: int = Field(3, ge=1, le=20)
    claim_search: ClaimSearchIn = Field(default_factory=ClaimSearchIn)
