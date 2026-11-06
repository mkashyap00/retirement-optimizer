"""Scenario comparison endpoint.

Routes:
  POST /compare  → run two scenarios, return both results and a delta summary.

The endpoint builds optimizer inputs once (shared State) then applies each
scenario's Constraints and Settings overrides (spending, Social Security
claim ages, estate weight, forced policy) and runs run_optimization twice
with the same Monte Carlo seed so that stochastic variation does not
confound the comparison.

Delta convention: ``delta = a − b`` (positive means Scenario A is larger).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.assemble import build_optimizer_inputs, constraints_from_model
from src.api.dependencies import get_db
from src.api.models import MAX_MONTE_CARLO_RUNS, ConstraintsIn
from src.data.database import Database
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.claiming import require_claim_ages, with_claim_ages
from src.optimization.optimizer import run_optimization
from src.optimization.search import search
from src.optimization.state import Engines

router = APIRouter(tags=["compare"])

# ---------------------------------------------------------------------------
# Module-level engines — same pattern as optimization.py
# ---------------------------------------------------------------------------

_rules = TaxRules()
_ENGINES = Engines(
    federal=FederalTaxEngine(_rules),
    state=StateTaxEngine(_rules),
    irmaa=IRMAACalculator(_rules),
    rmd=RMDCalculator(_rules),
    ss=SocialSecurityCalculator(),
    rules=_rules,
)


def _today() -> date:
    """Return today's date. Tests can monkeypatch this for deterministic behavior."""
    return date.today()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class ScenarioOverridesIn(BaseModel):
    """Per-scenario what-if overrides applied on top of the stored household.

    Every field is optional; ``None`` means "use the stored value".  Claim-age
    overrides only take effect when the stored settings carry the matching PIA
    (without a PIA the benefit never activates regardless of claim age).
    ``policy_id`` forces that scenario's conversion strategy instead of letting
    the optimizer choose.
    """

    required_spending: Decimal | None = Field(None, gt=0)
    ss_claim_age_self: int | None = Field(None, ge=62, le=70)
    ss_claim_age_spouse: int | None = Field(None, ge=62, le=70)
    # Deprecated and ignored: the objective no longer has a taxes-vs-estate
    # priority. Still accepted so older clients keep working.
    estate_weight: Decimal | None = Field(None, ge=0, le=1)
    policy_id: str | None = None
    # Death transition, deliberately offered HERE rather than in the wizard.
    # Modelling a death needs a year, and that is a guess; it belongs in a
    # comparison the user asked for, not silently inside their plan of record.
    # The age is the DECEASED person's, converted to a calendar year below.
    first_death_age: int | None = Field(None, ge=50, le=120)
    first_death_is_spouse: bool = True
    # Dynamic spending. Overridable so a scenario can ask "what if we were
    # willing to cut back?" — and, just as importantly, so the page can SHOW
    # which rule a stored plan uses instead of inheriting it invisibly.
    spending_rule: Literal["fixed", "guardrails"] | None = None
    spending_floor: Decimal | None = Field(None, ge=0)


class CompareRequest(BaseModel):
    """Request body for POST /compare."""

    household_id: str
    constraints_a: ConstraintsIn = ConstraintsIn()
    constraints_b: ConstraintsIn = ConstraintsIn()
    overrides_a: ScenarioOverridesIn = ScenarioOverridesIn()
    overrides_b: ScenarioOverridesIn = ScenarioOverridesIn()
    # Match /optimize (300, OptimizeRequest) so an unchanged scenario reproduces
    # the standalone run's winner rather than flipping on a near-tie.
    monte_carlo_runs: int = Field(300, ge=0, le=MAX_MONTE_CARLO_RUNS)


def _apply_overrides(settings, overrides: ScenarioOverridesIn, state=None):
    """Return a Settings copy with the scenario's non-None overrides applied.

    Claim ages here change Settings only; ``_scenario_inputs`` also moves
    year-0 Social Security, which year 0's conversion sizing reads from State.
    """
    changes: dict = {}
    if overrides.required_spending is not None:
        changes["required_spending"] = overrides.required_spending
    if overrides.ss_claim_age_self is not None:
        changes["ss_claim_age_self"] = overrides.ss_claim_age_self
    if overrides.ss_claim_age_spouse is not None:
        changes["ss_claim_age_spouse"] = overrides.ss_claim_age_spouse
    if overrides.spending_rule is not None:
        changes["spending_rule"] = overrides.spending_rule
    if overrides.spending_floor is not None:
        changes["spending_floor"] = overrides.spending_floor
    elif "spending_floor" in overrides.model_fields_set:
        # Sent as an explicit null: CLEAR the stored floor. Omitted keeps it.
        # Without the distinction a saved floor could never be removed here.
        changes["spending_floor"] = None
    if overrides.first_death_age is not None and state is not None:
        # Age -> calendar year, using the dying person's age today. A death
        # already in the past is dropped rather than applied retroactively:
        # the simulation starts this year and cannot un-live earlier ones.
        age_now = (
            state.age_spouse if overrides.first_death_is_spouse else state.age_self
        )
        if age_now is not None:
            death_year = state.year + max(0, overrides.first_death_age - age_now)
            changes["first_death_year"] = death_year
            changes["first_death_is_spouse"] = overrides.first_death_is_spouse
    # The floor belongs to "cut back, then recover". The page hides it when
    # spending is kept the same but keeps what was typed, so it can arrive here.
    if changes.get("spending_rule", settings.spending_rule) != "guardrails":
        changes["spending_floor"] = None
    return dataclasses.replace(settings, **changes)


def _scenario_inputs(state, settings, overrides: ScenarioOverridesIn):
    """(State, Settings) for one scenario.

    A claim-age override goes through ``claiming.with_claim_ages``, so this
    year's benefit follows it too (including stopping one already being paid
    under the stored age); the MAGI look-back keeps the stored-claim value.
    These are what-ifs: unlike a pinned /optimize run they are not checked
    against claim-age eligibility, and the result says so.
    """
    settings = _apply_overrides(settings, overrides, state)
    state, settings = with_claim_ages(
        state, settings, _ENGINES, overrides.ss_claim_age_self, overrides.ss_claim_age_spouse
    )
    require_claim_ages(state, settings)
    return state, settings


def _label_claim_what_if(result: dict, overrides: ScenarioOverridesIn) -> None:
    ages = [
        f"{person} {age}"
        for person, age in (("self", overrides.ss_claim_age_self),
                            ("spouse", overrides.ss_claim_age_spouse))
        if age is not None
    ]
    if ages and isinstance(result.get("warnings"), list):
        result["warnings"].append(
            f"What-if claim ages ({', '.join(ages)}): not checked against claim-age "
            "eligibility (a benefit already being received, or a salary paid before "
            "full retirement age)."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _breakeven_year(result_a: dict, result_b: dict) -> int | None:
    """Return the first year where cumulative (taxes_a − taxes_b) changes sign.

    Returns ``None`` if the cumulative difference never changes sign (i.e., one
    scenario dominates the other in taxes throughout the horizon, or the
    difference is always zero).

    Sign of ``initial`` is computed from the first year's cumulative difference.
    If the first cumulative difference is zero the initial sign is treated as
    zero and the function returns ``None`` immediately.
    """
    plan_a = result_a.get("yearly_plan", [])
    plan_b = result_b.get("yearly_plan", [])
    n = min(len(plan_a), len(plan_b))
    if n == 0:
        return None

    cumulative = 0.0
    initial_sign: int | None = None

    for i in range(n):
        tax_a = float(plan_a[i].get("total_tax", 0))
        tax_b = float(plan_b[i].get("total_tax", 0))
        cumulative += tax_a - tax_b

        if initial_sign is None:
            if cumulative > 0:
                initial_sign = 1
            elif cumulative < 0:
                initial_sign = -1
            else:
                # First cumulative value is zero; cannot determine initial sign
                continue

        current_sign = 1 if cumulative > 0 else (-1 if cumulative < 0 else 0)
        if current_sign != 0 and current_sign != initial_sign:
            return plan_a[i]["year"]

    return None


# ---------------------------------------------------------------------------
# POST /compare
# ---------------------------------------------------------------------------


class ScenarioPoliciesRequest(BaseModel):
    """One what-if scenario's inputs, for listing the strategies it can run."""

    constraints: ConstraintsIn = ConstraintsIn()
    overrides: ScenarioOverridesIn = ScenarioOverridesIn()


@router.post("/households/{household_id}/policies", status_code=200)
def list_scenario_policies(
    household_id: str,
    payload: ScenarioPoliciesRequest,
    db: Database = Depends(get_db),
) -> dict:
    """Strategies available to ONE scenario: the stored household with that
    scenario's constraints and overrides applied.

    GET on the same path lists them for the stored plan. A scenario that
    closes the conversion window, sets a cap or changes spending prunes a
    different set, so a list fetched for the stored plan offered strategies
    the scenario could not run and hid ones it could.
    """
    try:
        state, settings, _ = build_optimizer_inputs(db, household_id, today=_today())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    s_state, s_settings = _scenario_inputs(state, settings, payload.overrides)
    policies = search(
        s_state, _ENGINES, s_settings, constraints_from_model(payload.constraints),
    )
    return {"policies": sorted({p.policy_id for p in policies})}


@router.post("/compare", status_code=200)
def compare(payload: CompareRequest, db: Database = Depends(get_db)) -> dict:
    """Run two optimization scenarios and return both results with deltas.

    Builds optimizer inputs once from the stored household (same State and
    Settings for both scenarios), then runs run_optimization with each
    scenario's Constraints.

    Returns
    -------
    ``{result_a, result_b, difference: {lifetime_taxes_delta,
    terminal_estate_delta, success_probability_delta, breakeven_year}}``

    Deltas are ``a − b``.  ``breakeven_year`` is the first calendar year where
    the sign of cumulative (taxes_a − taxes_b) flips, or ``null`` if it never
    flips.

    Raises
    ------
    404 if the household_id is not found.
    """
    try:
        state, settings, _ = build_optimizer_inputs(
            db, payload.household_id, today=_today()
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    constraints_a = constraints_from_model(payload.constraints_a)
    constraints_b = constraints_from_model(payload.constraints_b)
    state_a, settings_a = _scenario_inputs(state, settings, payload.overrides_a)
    state_b, settings_b = _scenario_inputs(state, settings, payload.overrides_b)

    # Run both scenarios with the same seed so MC variation doesn't confound comparison
    result_a = run_optimization(
        state_a,
        _ENGINES,
        settings_a,
        constraints_a,
        monte_carlo_runs=payload.monte_carlo_runs,
        seed=42,
        forced_policy=payload.overrides_a.policy_id,
    )
    result_b = run_optimization(
        state_b,
        _ENGINES,
        settings_b,
        constraints_b,
        monte_carlo_runs=payload.monte_carlo_runs,
        seed=42,
        forced_policy=payload.overrides_b.policy_id,
    )

    _label_claim_what_if(result_a, payload.overrides_a)
    _label_claim_what_if(result_b, payload.overrides_b)

    # A half-errored comparison (e.g. unknown forced policy_id) is not
    # renderable — surface it as a request error instead of a result pair.
    for label, res in (("A", result_a), ("B", result_b)):
        if res.get("status") == "error":
            detail = "; ".join(res.get("warnings") or ["optimization failed"])
            raise HTTPException(status_code=400, detail=f"Scenario {label}: {detail}")

    wp_a = result_a["winning_policy"]
    wp_b = result_b["winning_policy"]

    difference = {
        # a − b; positive means scenario A has higher taxes / estate / success
        "lifetime_taxes_delta": float(wp_a["lifetime_taxes_nominal"])
        - float(wp_b["lifetime_taxes_nominal"]),
        "terminal_estate_delta": float(wp_a["terminal_estate"])
        - float(wp_b["terminal_estate"]),
        "success_probability_delta": float(wp_a["success_probability"])
        - float(wp_b["success_probability"]),
        "breakeven_year": _breakeven_year(result_a, result_b),
    }

    return {
        "result_a": result_a,
        "result_b": result_b,
        "difference": difference,
    }
