"""Search over Roth-conversion policies: named rules, and those rules cut short.

`search` builds three families of candidate policies and scores every one on
the same full-horizon objective:

1. **Bracket-fill rule** — apply one named bracket-fill rule
   (`fill_10/12/22/24/32`) *every allowed year across the full horizon* until
   the IRA is exhausted or the conversion window closes: "fill the 22% bracket
   every year". Labelled `<rule>_annual`.

2. **Level-dollar rule** — convert one fixed dollar amount every allowed year,
   sized once as 5%, 10% or 20% of the starting traditional balance
   (`level_5pct/10pct/20pct`): "convert about $90,000 a year", an amount
   between two brackets that no fill rule can say. Also `<rule>_annual`.

3. **Limited-duration rule** — either rule applied through year N and never
   again: "convert hard for a few years, then stop". Labelled
   `<rule>_thru_<YYYY>` (YYYY = last year that applies the rule).

Plus the `none` baseline. Each rule is walked once (one `generate_conversions`
per year); its duration variants are prefixes of that walk, so the only cost
per variant is one `simulate_path`.

Greedy rollouts (a year-0 seed, then each later year picked over a 5-year
lookahead) were removed after the October 2026 gate showed these families
match them: see `backend/benchmarks/`, which keeps a reference copy.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from decimal import Decimal

from src.optimization.actions import generate_conversions
from src.optimization.evaluate import PathResult, simulate_path
from src.optimization.state import Constraints, Engines, Settings, State
from src.optimization.transition import simulate_year

_ZERO = Decimal("0")

# Consistent-rule policies apply one named bracket-fill rule EVERY allowed year
# across the full horizon (until the IRA is exhausted or the window closes) —
# the interpretable "fill the 22% bracket every year" strategy.
#
# Covers every bracket in actions._FILL_RATES. 10 and 32 were missing once,
# which made a plain "compare 12 / 22 / 24 / 32 every year" impossible.
_ANNUAL_RULE_IDS = ("fill_10", "fill_12", "fill_22", "fill_24", "fill_32")

# Level-dollar rules convert one fixed dollar amount every allowed year, sized
# once from the STARTING traditional balance (5% / 10% / 20%, the shares the
# level_25/50/100 candidates take in year 0). They express "convert about
# $90,000 a year", which sits between two brackets and which no fill rule can
# say; the widow benchmark case needed exactly that. Each gets an `_annual`
# policy and `_thru_<YYYY>` variants like the fill rules. The amount is a
# requested maximum: the year's caps, affordability cut and IRMAA /
# marginal-rate filters still apply.
_LEVEL_RULES = (
    ("level_5pct", Decimal("0.05")),
    ("level_10pct", Decimal("0.10")),
    ("level_20pct", Decimal("0.20")),
)

_THRU_RE = re.compile(r"^(?P<rule>.+)_thru_(?P<year>\d{4})$")


def rule_of(policy_id: str) -> str | None:
    """The rule a rule-family policy applies, else None.

    ``fill_22_annual`` and ``fill_22_thru_2031`` both give ``fill_22``, and
    ``level_5pct_thru_2029`` gives ``level_5pct``; ``none`` gives None.
    """
    if policy_id.endswith("_annual"):
        return policy_id[: -len("_annual")]
    m = _THRU_RE.match(policy_id)
    return m.group("rule") if m else None


def thru_year_of(policy_id: str) -> int | None:
    """The last year a ``<rule>_thru_<YYYY>`` policy converts in, else None."""
    m = _THRU_RE.match(policy_id)
    return int(m.group("year")) if m else None


@dataclass(frozen=True)
class Policy:
    """An evaluated Roth-conversion policy."""

    policy_id: str                    # "none", "<rule>_annual" or "<rule>_thru_<YYYY>"
    conversions: tuple[Decimal, ...]  # full-horizon conversion schedule
    result: PathResult                # full-horizon evaluation


def search(
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
) -> list[Policy]:
    """Policy search; returns policies sorted best-first by path_value.

    Parameters
    ----------
    state:
        Starting simulation state (not mutated).
    engines, settings, constraints:
        Passed unchanged to every engine call.

    Returns
    -------
    list[Policy]
        Sorted descending by ``result.path_value``.  Policies with identical
        ``conversions`` tuples are deduplicated (first occurrence kept).
        Always contains the ``"none"`` baseline — an all-zero schedule that
        never converts — which callers rely on as the counterfactual.
    """
    seen_schedules: set[tuple[Decimal, ...]] = set()
    policies: list[Policy] = []

    def _add_policy(policy_id: str, schedule: list[Decimal]) -> None:
        # Dedup on the trailing-zero-trimmed schedule, so a duration variant
        # that only adds zero years collapses into the one before it.
        key = _dedup_key(schedule)
        if key in seen_schedules:
            return
        seen_schedules.add(key)
        result = simulate_path(state, list(schedule), engines, settings, constraints)
        policies.append(
            Policy(policy_id=policy_id, conversions=tuple(schedule), result=result)
        )

    # ── True "never convert" baseline ───────────────────────────────────────
    # Registered FIRST so it owns the "none" id with a genuinely all-zero
    # schedule.  This matters beyond labelling: run_optimization uses the
    # "none" policy as the counterfactual baseline for BETR, marginal-cost
    # rate, and projected_future_marginal_rate.  A "baseline" that itself
    # converts silently corrupts all three — and the UI renders "none" as
    # "No conversions", which must be true of the schedule it names.
    _add_policy("none", [])

    # ── Consistent-rule policies: apply one bracket-fill rule every year ────
    # Every `_annual` rule is registered before any duration variant, so a
    # variant that equals another rule's full schedule keeps that rule's name.
    rule_schedules: list[tuple[str, list[Decimal]]] = []
    for rule_id in _ANNUAL_RULE_IDS:
        schedule, feasible = _build_rule_schedule(
            state, rule_id, engines, settings, constraints
        )
        # Skip if infeasible in year 0, or if the rule never converts anything
        # (e.g. baseline already above the bracket, or the window blocks it) —
        # that would just duplicate the "none" baseline.
        if not feasible or _dedup_key(schedule) == ():
            continue
        rule_schedules.append((rule_id, schedule))
        _add_policy(f"{rule_id}_annual", schedule)

    # ── Level-dollar rules: one fixed amount every year, then its variants ───
    for rule_id, share in _LEVEL_RULES:
        requested = {rule_id: share * state.balance_traditional}
        schedule, feasible = _build_rule_schedule(
            state, rule_id, engines, settings, constraints, requested=requested
        )
        if not feasible or _dedup_key(schedule) == ():
            continue
        rule_schedules.append((rule_id, schedule))
        _add_policy(f"{rule_id}_annual", schedule)

    # ── Limited-duration rules: the rule through year N, then stop ──────────
    for rule_id, schedule in rule_schedules:
        for thru_year, variant in _duration_variants(schedule, settings.start_year):
            _add_policy(f"{rule_id}_thru_{thru_year}", variant)

    policies.sort(key=lambda p: p.result.path_value, reverse=True)
    return policies


def _dedup_key(schedule: list[Decimal]) -> tuple[Decimal, ...]:
    """Schedule identity for deduplication: trailing zeros stripped."""
    s = list(schedule)
    while s and s[-1] == _ZERO:
        s.pop()
    return tuple(s)


def _duration_variants(
    schedule: list[Decimal], start_year: int
) -> list[tuple[int, list[Decimal]]]:
    """``(last_year, schedule[:n] + zeros)`` for every n that stops early.

    A rule's amount in a year depends only on the state that year, and the
    state depends only on earlier conversions, so the first n years of the
    full schedule are exactly what "apply the rule through year n" converts --
    no re-simulation is needed to build the variant. n runs from 1 to the
    index of the last non-zero year (n = that index + 1 is the full rule);
    variants that only add a zero year collapse in ``_add_policy``'s dedup.
    """
    last_nonzero = max(
        (i for i, amt in enumerate(schedule) if amt != _ZERO), default=-1
    )
    return [
        (start_year + n - 1, list(schedule[:n]) + [_ZERO] * (len(schedule) - n))
        for n in range(1, last_nonzero + 1)
    ]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_rule_schedule(
    state: State,
    rule_id: str,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    requested: dict[str, Decimal] | None = None,
) -> tuple[list[Decimal], bool]:
    """Return (schedule, feasible) for applying *rule_id* every allowed year.

    Walks the full ``settings.simulation_years`` horizon. Each year it
    regenerates candidates on the evolved state and takes *rule_id*'s amount
    (0 when the rule isn't offered — window closed, bracket already exceeded,
    or the IRA exhausted). Because it reuses ``generate_conversions``, the
    window gate, ``max_conversion_per_year``, IRMAA-avoid, and
    ``marginal_rate_limit`` all apply automatically.

    *requested* is passed to ``generate_conversions`` for a rule it does not
    size itself (a level-dollar rule's fixed amount).

    ``feasible`` is False if the very first year cannot be funded.
    """
    schedule: list[Decimal] = []
    current_state = copy.deepcopy(state)

    for year_idx in range(settings.simulation_years):
        # Undeduplicated: under a cap, fill_10 and fill_22 can size to the
        # same amount, and the deduplicated list keeps only fill_10's entry.
        candidates = dict(
            generate_conversions(
                current_state, engines, settings, constraints, dedupe=False,
                requested=requested, only=rule_id,
            )
        )
        amount = candidates.get(rule_id, _ZERO)
        schedule.append(amount)

        current_state, step_ledger = simulate_year(
            current_state, amount, engines, settings, constraints
        )
        if step_ledger.shortfall > _ZERO:
            if year_idx == 0:
                return [], False
            break  # unfundable later year — simulate_path prices the shortfall

    return schedule, True


def rebuild_policy(
    policy_id: str,
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
) -> Policy:
    """Re-walk the rule *policy_id* names under different inputs (a longer or
    shorter horizon, a death year) and evaluate it there.

    ``<rule>_annual`` applies the rule every allowed year of the new horizon;
    ``<rule>_thru_<YYYY>`` applies it through the same YYYY and stops;
    ``none`` stays none. Nothing is re-chosen: no other bracket, no other stop
    year. A rule that cannot fund its first year under the new inputs
    converts nothing.
    """
    rule = rule_of(policy_id)
    schedule: list[Decimal] = []
    if rule is not None:
        share = dict(_LEVEL_RULES).get(rule)
        requested = {rule: share * state.balance_traditional} if share is not None else None
        schedule, feasible = _build_rule_schedule(
            state, rule, engines, settings, constraints, requested=requested
        )
        if not feasible:
            schedule = []
        thru = thru_year_of(policy_id)
        if thru is not None:
            keep = max(0, thru - settings.start_year + 1)
            schedule = schedule[:keep] + [_ZERO] * max(0, len(schedule) - keep)
    result = simulate_path(state, list(schedule), engines, settings, constraints)
    return Policy(policy_id=policy_id, conversions=tuple(schedule), result=result)
