"""Deterministic full-horizon path evaluation for the retirement optimizer.

`simulate_path` runs the simulation for `settings.simulation_years` years,
applying a Roth-conversion strategy defined by the `conversions` list (one entry
per year; missing tail years use conversion 0).  It returns a `PathResult`
summarising lifetime taxes, terminal estate and the objective-function value.

Objective (``objective_value``, used by search AND Monte Carlo alike):

    objective = terminal_estate / (1+d)^n
                − shortfall_weight               × shortfall_pv
                − discretionary_shortfall_weight × discretionary_shortfall_pv

where d = settings.discount_rate, n = the number of simulated years, and the
estate is heir-tax-adjusted. Taxes are NOT a separate term: every dollar of tax
already left the accounts, so the estate is net of it. Subtracting PV(taxes)
again counted them twice and, at a taxes-only priority, rewarded any plan with
less income. Lifetime taxes stay on PathResult as reported figures.

Every path runs the full horizon. A year that cannot fund required spending
funds what it can and records the gap, so an underfunded plan is scored by HOW
short it falls rather than by the fact that it fell short at all. `feasible`
only counts toward the share of scenarios with spending funded; `shortfall_pv`
prices the gap. Never drop an infeasible strategy: it stays scored and ranked.
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass
from decimal import Decimal

from src.optimization.actions import _affordable_conversion
from src.optimization.state import (
    Constraints,
    Engines,
    Settings,
    State,
    YearLedger,
)
from src.optimization.transition import simulate_year

_ZERO = Decimal("0")
_ONE = Decimal("1")
# Same tolerance simulate_year uses: below a dollar, an apparent gap is the
# tax<->withdrawal fixed point's convergence residue, not lost consumption.
_FUNDING_TOLERANCE = Decimal("1")


@dataclass(frozen=True)
class PathResult:
    ledgers: tuple[YearLedger, ...]
    lifetime_taxes_nominal: Decimal
    lifetime_taxes_pv: Decimal
    terminal_estate: Decimal        # heir-tax-adjusted, nominal
    # terminal_estate discounted to the start year.
    terminal_estate_pv: Decimal
    # Economics only: PV(heir-adjusted terminal estate), i.e. equal to
    # terminal_estate_pv. Contains NO consumption-gap charge; objective_value
    # applies those at the user's weights.
    economic_value: Decimal
    # PV of ESSENTIAL spending the plan fails to deliver — the part of the gap
    # that falls below `settings.spending_floor`. Charged at the full
    # `shortfall_weight`. With no floor set (the default) the floor IS the
    # target, so this is the whole consumption gap and the meaning is exactly
    # what it was before dynamic spending existed.
    shortfall_pv: Decimal
    # PV of spending given up while still ABOVE the essential floor, whether
    # the guardrails chose the cut or the money simply ran short. Charged at
    # `discretionary_shortfall_weight` (< 1), because trimming travel is
    # genuinely less bad than not affording care — but charged, because a
    # dollar you chose not to spend is still a dollar you did not spend.
    discretionary_shortfall_pv: Decimal
    # Years in which spending came in below target, for either reason. Reported
    # alongside success probability: with guardrails on, "the plan never failed"
    # and "the plan delivered what you asked for" stop being the same claim.
    years_reduced: int
    # objective_value(self, settings): the SAME objective Monte Carlo averages,
    # with the same shortfall weights, so the two rankings cannot disagree on
    # how a shortfall is priced. Search ranks on it.
    path_value: Decimal
    feasible: bool
    depletion_year: int | None      # first year with a shortfall


def weighted_objective(
    economic_value: Decimal,
    shortfall_pv: Decimal,
    discretionary_shortfall_pv: Decimal,
    settings: Settings,
) -> Decimal:
    """The optimizer's one objective, from its components.

    PV(heir-adjusted estate) less the consumption gap, charged in two tiers:
    spending lost below the essential floor at ``shortfall_weight`` (1.0) and
    spending given up above it at ``discretionary_shortfall_weight`` (0.5).
    The second tier is what stops dynamic spending from being free safety.
    """
    return (
        economic_value
        - settings.shortfall_weight * shortfall_pv
        - settings.discretionary_shortfall_weight * discretionary_shortfall_pv
    )


def objective_value(result: PathResult, settings: Settings) -> Decimal:
    """The objective of one evaluated path — deterministic or Monte Carlo."""
    return weighted_objective(
        result.economic_value, result.shortfall_pv,
        result.discretionary_shortfall_pv, settings,
    )


def simulate_path(
    state: State,
    conversions: list[Decimal],
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    annual_returns: list[Decimal] | None = None,
) -> PathResult:
    """Simulate the full horizon and return a PathResult.

    Parameters
    ----------
    state:
        Starting state (deep-copied internally to guarantee purity).
    conversions:
        Roth-conversion amounts, one per year from the start.  If shorter than
        ``settings.simulation_years``, the remaining years use conversion 0.
        A year that would run short of spending money converts only what it
        can spare (zero below ``min_conversion``), the same rule candidate
        generation applies; each ledger records the amount actually converted.
    engines, settings, constraints:
        Passed unchanged to ``simulate_year`` each year.
    annual_returns:
        Optional per-year nominal returns (one per simulated year). When given,
        each year grows at its own return — proper sequence-of-returns Monte
        Carlo, where a bad year is offset by others so the horizon average
        clusters near the mean. When ``None`` (the deterministic search path)
        every year uses ``settings.nominal_return`` unchanged. If shorter than
        the horizon, the last value carries forward.
    """
    current_state: State = copy.deepcopy(state)
    ledgers: list[YearLedger] = []
    feasible: bool = True
    depletion_year: int | None = None

    one_plus_d = _ONE + settings.discount_rate

    # PV of the spending the plan fails to deliver, split at the essential
    # floor. Accumulated year by year rather than extrapolated from the failure
    # point: once the accounts are empty the household still receives Social
    # Security and pensions and still pays tax on them, so simulate_year keeps
    # funding what it can and only the residual is charged here. That makes the
    # charge net-of-tax by construction.
    shortfall_pv: Decimal = _ZERO
    discretionary_shortfall_pv: Decimal = _ZERO
    years_reduced: int = 0

    # The floor as a fraction of the target. Applying it to the ledger's own
    # already-inflated target_spending avoids re-deriving the inflator here —
    # which would be wrong anyway, since search calls simulate_path on
    # mid-horizon states where the loop index is not years-since-start.
    floor_ratio = _ONE
    if settings.spending_floor is not None and settings.required_spending > _ZERO:
        floor_ratio = min(_ONE, settings.spending_floor / settings.required_spending)

    for y in range(settings.simulation_years):
        conversion = conversions[y] if y < len(conversions) else _ZERO
        if annual_returns is not None:
            r = annual_returns[y] if y < len(annual_returns) else annual_returns[-1]
            year_settings = dataclasses.replace(settings, nominal_return=r)
        else:
            year_settings = settings
        opening = current_state
        current_state, ledger = simulate_year(
            opening, conversion, engines, year_settings, constraints
        )
        # The schedule was sized so no conversion takes money the year needs
        # for spending -- but on THAT path's balances. Replayed on a path where
        # markets fell, the same dollar amount can strand spending money in
        # the Roth, and the year's shortfall would be charged to the policy
        # rather than to the market. So each year re-applies the rule to its
        # actual state: cut the conversion back to what the year can spare.
        # Only a short year pays for the check.
        if ledger.shortfall > _ZERO and conversion > _ZERO:
            _, zero = simulate_year(opening, _ZERO, engines, year_settings, constraints)
            if ledger.shortfall > zero.shortfall + _ONE:
                spared = _affordable_conversion(
                    opening, conversion, zero.shortfall, engines, year_settings,
                    constraints,
                )
                if spared < constraints.min_conversion:
                    spared = _ZERO
                current_state, ledger = simulate_year(
                    opening, spared, engines, year_settings, constraints
                )
        ledgers.append(ledger)

        # A shortfall no longer ends the path. The horizon is fixed by the
        # user's death age, not by when the money runs out, and the years after
        # depletion are exactly the ones a retiree most needs to see.
        #
        # `feasible` tracks the INVOLUNTARY gap only — whether the plan funded
        # what it set out to fund. A guardrail year that deliberately spends
        # less and succeeds is feasible; its cost is charged below, not here.
        if ledger.shortfall > _ZERO and feasible:
            feasible = False
            depletion_year = ledger.year

        # The consumption gap versus what the user actually asked for, split at
        # the essential floor. This spans BOTH causes — a guardrail cut and a
        # year the money ran out are the same loss to the person living it, so
        # they are priced by level rather than by cause.
        gap = ledger.target_spending - ledger.net_spendable
        if gap > _FUNDING_TOLERANCE:
            years_reduced += 1
            essential = max(_ZERO, ledger.target_spending * floor_ratio
                            - ledger.net_spendable)
            discount = one_plus_d ** y
            shortfall_pv += essential / discount
            discretionary_shortfall_pv += (gap - essential) / discount

    # --- Terminal estate (heir-tax-adjusted) from last completed ledger ------
    if ledgers:
        last = ledgers[-1]
        terminal_estate: Decimal = (
            last.end_roth
            + last.end_taxable
            + last.end_traditional * (_ONE - settings.heir_tax_rate)
        )
    else:
        terminal_estate = _ZERO

    # --- Lifetime taxes (nominal and PV-weighted) ----------------------------
    lifetime_taxes_nominal: Decimal = sum((entry.total_tax for entry in ledgers), _ZERO)

    lifetime_taxes_pv: Decimal = _ZERO
    for y, ledger in enumerate(ledgers):
        lifetime_taxes_pv += ledger.total_tax / (one_plus_d ** y)

    # --- Objective function ---------------------------------------------------
    # The estate is already net of every tax paid, so taxes are reported, not
    # scored. An underfunded path cannot buy its way up by paying less tax: the
    # consumption gap is charged at the user's weights.
    n = len(ledgers)
    pv_terminal = terminal_estate / (one_plus_d ** n)
    economic_value: Decimal = pv_terminal

    return PathResult(
        ledgers=tuple(ledgers),
        lifetime_taxes_nominal=lifetime_taxes_nominal,
        lifetime_taxes_pv=lifetime_taxes_pv,
        terminal_estate=terminal_estate,
        terminal_estate_pv=pv_terminal,
        economic_value=economic_value,
        shortfall_pv=shortfall_pv,
        discretionary_shortfall_pv=discretionary_shortfall_pv,
        years_reduced=years_reduced,
        path_value=weighted_objective(
            economic_value, shortfall_pv, discretionary_shortfall_pv, settings
        ),
        feasible=feasible,
        depletion_year=depletion_year,
    )
