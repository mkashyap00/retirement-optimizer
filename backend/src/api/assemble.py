"""Assemble optimizer inputs from a persisted household.

``build_optimizer_inputs`` reads a household from the database and constructs
the ``(State, Settings, Constraints)`` triple required by ``run_optimization``.

Simplifications (documented):
- ``magi_two_years_ago`` and ``magi_last_year`` are approximated as the sum of
  salary + pension + rental + interest + social_security (the IRMAA look-back income
  proxy); no actual historical AGI is stored in the database.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from src.api.models import ConstraintsIn
from src.data.database import Database
from src.engines.social_security import SocialSecurityCalculator
from src.optimization.claiming import ClaimInputError, receiving_error
from src.optimization.state import Constraints, IncomeEntry, Settings, State, resolve_income
from src.optimization.transition import household_social_security

_SS_CALC = SocialSecurityCalculator()
_ZERO = Decimal("0")


def constraints_from_model(cin: ConstraintsIn) -> Constraints:
    """Map a :class:`~src.api.models.ConstraintsIn` Pydantic model to the
    :class:`~src.optimization.state.Constraints` dataclass used by the optimizer.

    ``min_conversion`` is not exposed in the API model; the optimizer default
    (1 000) is used.

    Sign convention: all optional Decimal fields are already typed as
    ``Decimal | None`` in ``ConstraintsIn``, so they pass through directly.
    """
    return Constraints(
        irmaa_policy=cin.irmaa_policy,
        conversion_window=cin.conversion_window,
        marginal_rate_limit=cin.marginal_rate_limit,
        max_conversion_per_year=cin.max_conversion_per_year,
        target_estate=cin.target_estate,
        preserve_taxable=cin.preserve_taxable,
    )


def _age(birth_date: date, today: date) -> int:
    """Return the age attained in *today*'s calendar year.

    The simulation steps in tax years, and the tax rules key on the age
    reached during the year: the first RMD is for the year you turn 73, the
    age-65 deduction applies for the year you turn 65. Completed age as of
    today undercounts by one for anyone whose birthday is still to come.
    """
    return today.year - birth_date.year


def _to_date(raw: object) -> date:
    """Coerce a DuckDB date column value to a :class:`datetime.date`."""
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


def claim_preview_inputs(preview, today: date) -> tuple[State, Settings]:
    """Minimal (State, Settings) for :func:`claiming.claim_age_preview` from an
    unsaved plan (a :class:`~src.api.models.ClaimPreviewIn`). Ages and the
    income schedule are built exactly as :func:`build_optimizer_inputs` builds
    them; balances are irrelevant to eligibility and left at zero."""
    hh = preview.household
    self_birth = hh.self_birth_date
    spouse_birth = hh.spouse_birth_date if hh.filing_status == "joint" else None
    income_schedule = [
        IncomeEntry(category=i.category, amount=Decimal(str(i.amount)),
                    start_year=i.start_year, end_year=i.end_year, owner=i.owner or "joint")
        for i in preview.income
    ]
    settings = Settings(
        start_year=today.year, required_spending=Decimal("1"),
        ss_pia_self=preview.ss_pia_self, ss_claim_age_self=preview.ss_claim_age_self,
        ss_receiving_self=preview.ss_receiving_self,
        ss_pia_spouse=preview.ss_pia_spouse if spouse_birth else None,
        ss_claim_age_spouse=preview.ss_claim_age_spouse if spouse_birth else None,
        ss_receiving_spouse=preview.ss_receiving_spouse if spouse_birth else None,
        birth_year_self=self_birth.year,
        birth_year_spouse=spouse_birth.year if spouse_birth else None,
        income_schedule=income_schedule,
    )
    state = State(
        year=today.year, age_self=_age(self_birth, today),
        age_spouse=_age(spouse_birth, today) if spouse_birth else None,
        balance_taxable=_ZERO, balance_traditional=_ZERO, balance_roth=_ZERO,
        basis_taxable=_ZERO, filing_status=hh.filing_status, state_code=hh.state,
    )
    return state, settings


def build_optimizer_inputs(
    db: Database,
    household_id: str,
    today: date,
) -> tuple[State, Settings, Constraints]:
    """Build ``(State, Settings, Constraints)`` from a persisted household.

    Parameters
    ----------
    db:
        Database connection (DuckDB wrapper).
    household_id:
        UUID string identifying the household to load.
    today:
        Reference date for age calculations and the simulation start year.

    Returns
    -------
    Tuple ``(State, Settings, Constraints)`` ready to pass to
    :func:`~src.optimization.optimizer.run_optimization`.

    Raises
    ------
    KeyError
        If the household (or its settings row) is not found in the database.
        The caller should map this to a 404 HTTP response.

    Notes
    -----
    **MAGI proxy** — ``magi_two_years_ago`` and ``magi_last_year`` are set
    to ``salary + pension + rental + interest + social_security``.  This is the best
    available approximation without storing historical AGI.  IRMAA
    calculations in years 1–2 of the simulation may be slightly off if the
    real prior-year income differed substantially.
    """
    # ------------------------------------------------------------------
    # Load household
    # ------------------------------------------------------------------
    hh = db.fetch_one(
        "SELECT filing_status, self_birth_date, spouse_birth_date, state, "
        "self_death_age, spouse_death_age "
        "FROM households WHERE id = ?",
        [household_id],
    )
    if hh is None:
        raise KeyError(f"Household {household_id!r} not found")

    (
        filing_status,
        self_birth_raw,
        spouse_birth_raw,
        state_code,
        self_death_age,
        spouse_death_age,
    ) = hh

    self_birth = _to_date(self_birth_raw)
    age_self = _age(self_birth, today)

    spouse_birth = _to_date(spouse_birth_raw) if spouse_birth_raw is not None else None
    age_spouse: int | None = _age(spouse_birth, today) if spouse_birth else None

    # ------------------------------------------------------------------
    # Simulation years — "Plan through age N" is INCLUSIVE (the table's
    # last row is the year that person turns N), and the household plans
    # to the LONGER of the two horizons when both death ages are given.
    # ------------------------------------------------------------------
    horizons: list[int] = []
    if self_death_age is not None:
        horizons.append(int(self_death_age) - age_self + 1)
    if spouse_death_age is not None and age_spouse is not None:
        horizons.append(int(spouse_death_age) - age_spouse + 1)
    simulation_years = max(10, max(horizons)) if horizons else 30

    # ------------------------------------------------------------------
    # Aggregate account balances by type; track earliest Roth open year
    # ------------------------------------------------------------------
    accounts = db.fetch_all(
        "SELECT account_type, owner, balance, basis, roth_opened_year "
        "FROM accounts WHERE household_id = ?",
        [household_id],
    )
    balance_taxable = _ZERO
    basis_taxable = _ZERO
    balance_traditional = _ZERO
    basis_traditional = _ZERO
    balance_traditional_spouse = _ZERO
    balance_roth = _ZERO
    roth_earliest_opened_year: int | None = None

    for acc_type, owner, balance, basis, roth_opened_year in accounts:
        bal = Decimal(str(balance))
        bas = Decimal(str(basis)) if basis is not None else _ZERO
        if acc_type == "taxable":
            balance_taxable += bal
            basis_taxable += bas
        elif acc_type == "traditional":
            balance_traditional += bal
            basis_traditional += bas
            # Each owner's RMD runs on their own balance and age. An IRA
            # cannot be joint, so a row saying so (or NULL) stays self's.
            if owner == "spouse" and spouse_birth is not None:
                balance_traditional_spouse += bal
        elif acc_type == "roth":
            balance_roth += bal
            if roth_opened_year is not None:
                if (
                    roth_earliest_opened_year is None
                    or int(roth_opened_year) < roth_earliest_opened_year
                ):
                    roth_earliest_opened_year = int(roth_opened_year)

    # ------------------------------------------------------------------
    # Build income schedule (respects start_year / end_year per source)
    # ------------------------------------------------------------------
    # Owner decides whose death stops a stream (salary, a single-life pension).
    # Dropping it made every stream joint, so the deceased's income kept
    # arriving for the rest of the plan. Rows saved before owners existed are
    # NULL and stay joint — the behaviour they always had.
    income_rows = db.fetch_all(
        "SELECT category, amount, start_year, end_year, owner "
        "FROM income_sources WHERE household_id = ?",
        [household_id],
    )
    income_schedule: list[IncomeEntry] = [
        IncomeEntry(
            category=cat,
            amount=Decimal(str(amt)),
            start_year=int(sy) if sy is not None else None,
            end_year=int(ey) if ey is not None else None,
            owner=owner or "joint",
        )
        for cat, amt, sy, ey, owner in income_rows
    ]

    # Every category straight from resolve_income, the same mapping the
    # transition uses for later years. Copying fields one by one left interest
    # out of the first year only.
    year0 = resolve_income(income_schedule, today.year)

    # ------------------------------------------------------------------
    # Load settings and constraints
    # ------------------------------------------------------------------
    sett = db.fetch_one(
        "SELECT required_spending, inflation, nominal_return, "
        "ss_pia_self, ss_claim_age_self, ss_pia_spouse, ss_claim_age_spouse, "
        "heir_tax_rate, estate_weight, spending_rule, spending_floor, "
        "constraints_json, ss_cola, ss_receiving_self, ss_receiving_spouse, "
        "capital_gains_json "
        "FROM settings WHERE household_id = ?",
        [household_id],
    )
    if sett is None:
        raise KeyError(f"Settings not found for household {household_id!r}")

    (
        required_spending,
        inflation,
        nominal_return,
        ss_pia_self,
        ss_claim_age_self,
        ss_pia_spouse,
        ss_claim_age_spouse,
        heir_tax_rate,
        _estate_weight,  # stored for old snapshots; no longer part of the objective
        spending_rule,
        spending_floor,
        constraints_json,
        ss_cola,
        ss_receiving_self,
        ss_receiving_spouse,
        capital_gains_json,
    ) = sett

    # Gains already realized and the loss carried in belong to one tax year.
    # They apply only when that year is the plan's first; entered for an
    # earlier year they are stale (that year is over) and the report says so.
    gains = json.loads(capital_gains_json) if capital_gains_json else None
    stale_gains_year = None
    year0_gains: dict[str, Decimal] = {}
    if gains is not None:
        if int(gains["tax_year"]) == today.year:
            year0_gains = {
                "realized_st_gain": Decimal(str(gains.get("short_term", 0))),
                "realized_lt_gain": Decimal(str(gains.get("long_term", 0))),
                "loss_carryover_st": Decimal(str(gains.get("carryover_short_term", 0))),
                "loss_carryover_lt": Decimal(str(gains.get("carryover_long_term", 0))),
            }
            # A state that figures its own carryover starts from the one
            # entered (the federal figure), then figures it on state income.
            year0_gains["state_loss_carryover_st"] = year0_gains["loss_carryover_st"]
            year0_gains["state_loss_carryover_lt"] = year0_gains["loss_carryover_lt"]
        elif int(gains["tax_year"]) < today.year:
            stale_gains_year = int(gains["tax_year"])

    # A stored plan can go stale: "not yet receiving, claim at 67" is a
    # contradiction once that person is 68. Refuse rather than guess which
    # half is out of date.
    for person, age, claim, receiving in (
        ("self", age_self, ss_claim_age_self, ss_receiving_self),
        ("spouse", age_spouse, ss_claim_age_spouse, ss_receiving_spouse),
    ):
        err = receiving_error(person, age, claim, receiving)
        if err:
            raise ClaimInputError(err)

    # ------------------------------------------------------------------
    # Construct Settings
    # ------------------------------------------------------------------
    settings = Settings(
        start_year=today.year,
        required_spending=Decimal(str(required_spending)),
        inflation=Decimal(str(inflation)),
        nominal_return=Decimal(str(nominal_return)),
        simulation_years=simulation_years,
        # SS claiming config: lets simulate_year ACTIVATE benefits when each
        # person reaches their claim age (the t0 State only carries benefits
        # for people already claiming today).
        ss_pia_self=Decimal(str(ss_pia_self)) if ss_pia_self is not None else None,
        ss_claim_age_self=ss_claim_age_self,
        ss_pia_spouse=Decimal(str(ss_pia_spouse)) if ss_pia_spouse is not None else None,
        ss_claim_age_spouse=ss_claim_age_spouse,
        ss_receiving_self=ss_receiving_self,
        ss_receiving_spouse=ss_receiving_spouse,
        # NULL = follow inflation (floored at 0); an explicit 0 holds benefits flat.
        **({"ss_cola": Decimal(str(ss_cola))} if ss_cola is not None else {}),
        # Real birth year, not year - age: the SECURE 2.0 RMD applicable age
        # turns on the 1959/1960 boundary, where an off-by-one is wrong by two
        # full years of forced distributions.
        birth_year_self=self_birth.year,
        # Needed once a death is modelled: the survivor's RMD cohort (SECURE
        # 2.0 turns on 1959/1960) and the deceased's age at death, which decides
        # which of their benefits the survivor inherits.
        birth_year_spouse=spouse_birth.year if spouse_birth is not None else None,
        income_schedule=income_schedule,
        stale_capital_gains_year=stale_gains_year,
        # Heir tax rate — dataclass default 0.25 when not provided. The stored
        # estate_weight is no longer read: the objective has no priority knob.
        **(
            {"heir_tax_rate": Decimal(str(heir_tax_rate))}
            if heir_tax_rate is not None
            else {}
        ),
        # Dynamic spending — NULL columns keep the dataclass defaults
        # ("fixed", no floor), which is how every pre-v5 plan behaved.
        **({"spending_rule": spending_rule} if spending_rule else {}),
        **(
            {"spending_floor": Decimal(str(spending_floor))}
            if spending_floor is not None and spending_rule == "guardrails"
            else {}
        ),
    )

    # ------------------------------------------------------------------
    # Social Security — this year's household benefit for people already
    # claiming, from the same pure helper the simulator uses every later
    # year (spousal top-up included, start-year dollars).
    # ------------------------------------------------------------------
    social_security = household_social_security(
        _SS_CALC, settings, age_self, age_spouse, today.year
    ) or _ZERO

    # ------------------------------------------------------------------
    # Medicare flags (age >= 65)
    # ------------------------------------------------------------------
    medicare_self = age_self >= 65
    medicare_spouse = age_spouse is not None and age_spouse >= 65

    # ------------------------------------------------------------------
    # MAGI proxy (V1: salary + pension + rental + interest + SS + ordinary dividends)
    # ------------------------------------------------------------------
    magi_proxy = (
        year0["salary"] + year0["pension"] + year0["rental"] + year0["interest"]
        + social_security + year0["dividends_ordinary"]
    )

    # ------------------------------------------------------------------
    # Construct State
    # ------------------------------------------------------------------
    state = State(
        year=today.year,
        age_self=age_self,
        age_spouse=age_spouse,
        balance_taxable=balance_taxable,
        balance_traditional=balance_traditional,
        balance_roth=balance_roth,
        basis_taxable=basis_taxable,
        basis_traditional=basis_traditional,
        balance_traditional_spouse=balance_traditional_spouse,
        filing_status=filing_status,
        state_code=state_code,
        **year0,
        **year0_gains,
        social_security=social_security,
        medicare_self=medicare_self,
        medicare_spouse=medicare_spouse,
        magi_two_years_ago=magi_proxy,
        magi_last_year=magi_proxy,
        roth_earliest_opened_year=roth_earliest_opened_year,
    )

    # ------------------------------------------------------------------
    # Construct Constraints from stored JSON
    # ------------------------------------------------------------------
    cj: dict = json.loads(constraints_json) if constraints_json else {}

    marginal_rate_limit = (
        Decimal(str(cj["marginal_rate_limit"]))
        if cj.get("marginal_rate_limit") is not None
        else None
    )
    max_conversion_per_year = (
        Decimal(str(cj["max_conversion_per_year"]))
        if cj.get("max_conversion_per_year") is not None
        else None
    )
    target_estate = (
        Decimal(str(cj["target_estate"]))
        if cj.get("target_estate") is not None
        else None
    )

    constraints = Constraints(
        irmaa_policy=cj.get("irmaa_policy", "soft"),
        conversion_window=cj.get("conversion_window", "anytime"),
        marginal_rate_limit=marginal_rate_limit,
        min_conversion=Decimal(str(cj.get("min_conversion", "1000"))),
        max_conversion_per_year=max_conversion_per_year,
        target_estate=target_estate,
        preserve_taxable=cj.get("preserve_taxable", False),
    )

    return state, settings, constraints
