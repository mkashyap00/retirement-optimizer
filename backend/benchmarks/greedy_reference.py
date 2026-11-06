"""Greedy-rollout policies, kept outside the optimizer as a benchmark reference.

A standalone copy of the search's former greedy family, so the
greedy-vs-rules benchmark keeps running whether or not production still builds
greedy policies. For each year-0 candidate from ``generate_conversions`` it
fixes that amount in year 0, then picks each later year's amount (up to
``lookahead_years``) as the candidate maximising ``objective_value`` over the
remaining horizon, assuming no conversions after it. The schedule is confined
to the lookahead window.
"""
from __future__ import annotations

import copy
import dataclasses
from decimal import Decimal

from src.optimization.actions import generate_conversions
from src.optimization.evaluate import objective_value, simulate_path
from src.optimization.search import Policy
from src.optimization.state import Constraints, Engines, Settings, State
from src.optimization.transition import simulate_year

_ZERO = Decimal("0")


def greedy_policies(
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    lookahead_years: int = 5,
) -> list[Policy]:
    """One greedy rollout per feasible year-0 candidate, deduplicated.

    Ids are the year-0 action id; the year-0 ``none`` seed is ``defer_1yr``
    (it still converts later). An all-zero rollout is dropped.
    """
    seen: set[tuple[Decimal, ...]] = {()}
    out: list[Policy] = []
    for action_id, amount in generate_conversions(state, engines, settings, constraints):
        schedule = greedy_schedule(
            state, amount, engines, settings, constraints, lookahead_years
        )
        if schedule is None:
            continue
        key = trimmed(schedule)
        if key in seen:
            continue
        seen.add(key)
        result = simulate_path(state, list(schedule), engines, settings, constraints)
        out.append(Policy(
            policy_id="defer_1yr" if action_id == "none" else action_id,
            conversions=tuple(schedule),
            result=result,
        ))
    return out


def greedy_schedule(
    state: State,
    year0_amount: Decimal,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    lookahead_years: int,
) -> list[Decimal] | None:
    """The rollout seeded with *year0_amount*; None if year 0 runs short."""
    schedule = [year0_amount]
    current, ledger = simulate_year(
        copy.deepcopy(state), year0_amount, engines, settings, constraints
    )
    if ledger.shortfall > _ZERO:
        return None

    for year_idx in range(1, lookahead_years):
        remaining = settings.simulation_years - year_idx
        if remaining <= 0:
            break
        remaining_settings = dataclasses.replace(settings, simulation_years=remaining)
        best_amount, best_value = _ZERO, None
        for _, sub_amount in generate_conversions(current, engines, settings, constraints):
            value = objective_value(
                simulate_path(current, [sub_amount], engines, remaining_settings, constraints),
                remaining_settings,
            )
            if best_value is None or value > best_value:
                best_amount, best_value = sub_amount, value
        schedule.append(best_amount)
        current, ledger = simulate_year(current, best_amount, engines, settings, constraints)
        if ledger.shortfall > _ZERO:
            break
    return schedule


def trimmed(schedule) -> tuple[Decimal, ...]:
    """Schedule identity: trailing zeros stripped."""
    s = list(schedule)
    while s and s[-1] == _ZERO:
        s.pop()
    return tuple(s)
