"""Seeded Monte Carlo simulation with risk-adjusted scoring for Roth-conversion policies.

`score_policies` evaluates a list of `Policy` objects under stochastic return
scenarios and ranks them on the mean per-path objective:

    score = mean( objective_value(path) )
          = mean( PV(estate) − shortfall_weight × shortfall_pv
                  − discretionary_shortfall_weight × discretionary_shortfall_pv )

The same ``objective_value`` ranks policies in the deterministic search.

There is deliberately no variance term. `std_value` is still reported as a
diagnostic but never scored — standard deviation is symmetric, so it penalised
strategies for occasionally producing a LARGER estate, and the quantity it was
taken over already contained the shortfall charge.

`compare_paired` compares two scored policies path by path, which is far more
precise than comparing their means independently (measured 3.8x tighter),
because every policy sees the same return sequences.

Common Random Numbers (CRN)
---------------------------
Each run ``r`` draws an INDEPENDENT return for every simulated year:

    Random(seed + r) → [gauss(mu, sigma) for each year of the horizon]

The SAME per-year sequence is used for every policy in run ``r``, guaranteeing
fair comparison and variance reduction across the policy set. Independent
per-year draws (rather than one return held constant for the whole horizon)
are what make this a real sequence-of-returns model: a bad year is offset by
others, so the horizon-average return clusters near the mean instead of
inheriting the full annual volatility.

Quantisation
------------
``mean_value``, ``std_value``, and ``score`` are quantised to cents ($0.01).
``success_probability`` is quantised to 4 decimal places (0.0001).

Special case: runs=0
--------------------
Deterministic passthrough — score is the single-path objective, std is 0,
success is 1 if feasible else 0.
"""
from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from src.optimization.evaluate import objective_value, simulate_path
from src.optimization.search import Policy
from src.optimization.state import Constraints, Engines, Settings, State

if TYPE_CHECKING:
    from src.optimization.claiming import Candidate

_ZERO = Decimal("0")
_ONE = Decimal("1")
_CENT = Decimal("0.01")
_FOUR_PLACES = Decimal("0.0001")
_TENTH = Decimal("0.1")   # years-reduced averages; a tenth of a year is plenty

# Standard deviation of each year's return. Fixed, not a user setting; every
# result records it (``market_model``) so the page states what the run used.
VOLATILITY = Decimal("0.12")


def market_model(settings: Settings, runs: int, volatility: Decimal = VOLATILITY) -> dict:
    """How the run's market scenarios were drawn, as the result records it."""
    return {
        "scenarios": runs,
        "mean_return": float(settings.nominal_return),
        "volatility": float(volatility),
        "distribution": "normal",
        "independent_years": True,
    }


def _make_paths(
    start: int, end: int, settings: Settings, volatility: Decimal, seed: int
) -> list[list[Decimal]]:
    """Return-sequences for path indices ``[start, end)``.

    Path *r* is drawn from ``Random(seed + r)``, so it is identical no matter
    how many paths are requested. That is what makes staging safe: stage 2
    EXTENDS stage 1's sample rather than replacing it, so paired comparisons
    keep the common random numbers that make them ~4x tighter.
    """
    mu = float(settings.nominal_return)
    vol = float(volatility)
    n_years = settings.simulation_years
    out: list[list[Decimal]] = []
    for r in range(start, end):
        rng = random.Random(seed + r)
        out.append([Decimal(str(rng.gauss(mu, vol))) for _ in range(n_years)])
    return out


# Per-path objective components: (estate_pv, shortfall_pv,
# discretionary_shortfall_pv, taxes_pv). The objective is linear in the first
# three, so their means reconcile with the score exactly.
_Components = tuple[Decimal, Decimal, Decimal, Decimal]
_Acc = tuple[list[Decimal], list[bool], int, list[int], list[_Components]]


def _run_paths(
    pol: Policy,
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    paths: list[list[Decimal]],
) -> _Acc:
    """Simulate one policy over the given return sequences."""
    target_estate = constraints.target_estate
    objectives: list[Decimal] = []
    feasible: list[bool] = []
    successes = 0
    reduced: list[int] = []
    components: list[_Components] = []
    for returns in paths:
        pr = simulate_path(
            state, list(pol.conversions), engines, settings, constraints,
            annual_returns=returns,
        )
        objectives.append(_objective(pr, settings))
        feasible.append(pr.feasible)
        reduced.append(pr.years_reduced)
        components.append((
            pr.terminal_estate_pv, pr.shortfall_pv,
            pr.discretionary_shortfall_pv, pr.lifetime_taxes_pv,
        ))
        if pr.feasible and (
            target_estate is None or pr.terminal_estate >= target_estate
        ):
            successes += 1
    return objectives, feasible, successes, reduced, components


def _mean_components(components: Sequence[_Components]) -> ScoreComponents | None:
    if not components:
        return None
    n = Decimal(len(components))
    sums = [sum((c[i] for c in components), _ZERO) for i in range(4)]
    return ScoreComponents(*((v / n).quantize(_CENT) for v in sums))


def _build_scored(
    pol: Policy,
    objectives: list[Decimal],
    feasible: list[bool],
    successes: int,
    reduced: list[int],
    components: Sequence[_Components] = (),
    candidate: Candidate | None = None,
) -> ScoredPolicy:
    n = Decimal(len(objectives))
    mean = sum(objectives, _ZERO) / n
    variance = sum(((v - mean) ** 2 for v in objectives), _ZERO) / n
    mean_q = mean.quantize(_CENT)
    return ScoredPolicy(
        policy=pol,
        mean_value=mean_q,
        std_value=variance.sqrt().quantize(_CENT),
        score=mean_q,           # no variance term — see module docstring
        success_probability=(Decimal(successes) / n).quantize(_FOUR_PLACES),
        mean_years_reduced=(Decimal(sum(reduced)) / n).quantize(_TENTH),
        path_objectives=tuple(objectives),
        path_feasible=tuple(feasible),
        candidate=candidate,
        mean_components=_mean_components(components),
    )


def _extend(acc: _Acc, more: _Acc) -> _Acc:
    return (acc[0] + more[0], acc[1] + more[1], acc[2] + more[2],
            acc[3] + more[3], acc[4] + more[4])


def score_candidates_staged(
    candidates: Sequence[Candidate],
    engines: Engines,
    constraints: Constraints,
    *,
    runs: int,
    stage1_runs: int,
    finalists: int,
    pinned: set[str] | frozenset[str] = frozenset(),
    volatility: Decimal = VOLATILITY,
    seed: int = 42,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[ScoredPolicy]:
    """Score candidates from any number of claim scenarios on ONE shared sample.

    Stage 1 runs every candidate on paths ``[0, stage1_runs)``. The top
    *finalists* by stage-1 score among ELIGIBLE candidates, plus every key in
    *pinned*, are extended to ``runs`` by appending paths
    ``[stage1_runs, runs)``. Path *r* is the same return sequence in every
    scenario, so any two candidates compare path by path.

    Winner selection is the caller's. Every candidate is returned, in input
    order, each with its own sample count (``len(path_objectives)``); a caller
    must rank only among the fully sampled, eligible ones.

    *on_progress* is called as ``(done, total)`` simulated candidate-batches.
    """
    if not candidates:
        return []
    first = candidates[0].scenario.settings
    for c in candidates:
        s = c.scenario.settings
        assert (s.simulation_years, s.nominal_return) == (
            first.simulation_years, first.nominal_return
        ), "candidates must share the horizon and mean return to share paths"

    stage1 = min(max(1, stage1_runs), runs)
    total = len(candidates)
    done = 0

    def run(c: Candidate, paths: list[list[Decimal]]) -> _Acc:
        nonlocal done
        out = _run_paths(
            c.policy, c.scenario.state, engines, c.scenario.settings, constraints, paths
        )
        done += 1
        if on_progress is not None:
            on_progress(done, total)
        return out

    paths = _make_paths(0, stage1, first, volatility, seed)
    acc = {c.key: run(c, paths) for c in candidates}

    if stage1 < runs:
        ranked = sorted(
            (c for c in candidates if c.scenario.eligible),
            key=lambda c: _build_scored(c.policy, *acc[c.key]).score,
            reverse=True,
        )
        extend_keys = [c.key for c in ranked[:finalists]]
        extend_keys += [k for k in pinned if k in acc and k not in extend_keys]
        total += len(extend_keys)
        more = _make_paths(stage1, runs, first, volatility, seed)
        by_key = {c.key: c for c in candidates}
        for k in extend_keys:
            acc[k] = _extend(acc[k], run(by_key[k], more))

    return [_build_scored(c.policy, *acc[c.key], candidate=c) for c in candidates]


def score_policies_adaptive(
    policies: list[Policy],
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    runs: int = 100,
    volatility: Decimal = VOLATILITY,
    seed: int = 42,
    survivors: int = 3,
    pinned: str | Iterable[str] | None = None,
    contenders: str | Iterable[str] | None = None,
) -> list[ScoredPolicy]:
    """Score with a staged budget, spending it on policies still in contention.

    Stage 1 scores every candidate on a cheap slice of the budget; the field is
    then narrowed to the top *survivors*, who are carried to the full budget by
    APPENDING further paths to the same common sample.

    This costs less than scoring everything at ``runs`` while giving the
    finalists — the only ones whose ranking is actually in question — a tighter
    interval. Eliminated policies are still returned, scored on the evidence
    gathered for them; the caller can see their path count.

    *pinned* names the policy (or policies) the caller will report whatever
    their rank -- a forced run's policy. They are carried to the full budget
    too, so their statistics rest on the count the run advertises -- but each
    is ranked where its stage-1 result put it: measuring it more does not
    promote it over the finalists.

    *contenders* are carried to the full budget AND ranked with the
    finalists: ``none``, the no-conversion baseline. Measured on the same
    full sample, it is as comparable as any finalist, so it may win.
    """
    if not policies:
        return []
    if runs <= 0:
        return score_policies(
            policies, state, engines, settings, constraints,
            runs=0, volatility=volatility, seed=seed,
        )

    stage1 = max(1, runs // 3)
    if len(policies) <= survivors or stage1 >= runs:
        return score_policies(
            policies, state, engines, settings, constraints,
            runs=runs, volatility=volatility, seed=seed,
        )

    from src.optimization.claiming import Candidate, ClaimScenario, scenario_key

    scenario = ClaimScenario(
        claim_age_self=settings.ss_claim_age_self,
        claim_age_spouse=settings.ss_claim_age_spouse,
        state=state, settings=settings,
        key=scenario_key(settings.ss_claim_age_self, settings.ss_claim_age_spouse),
    )
    candidates = [Candidate(scenario, p) for p in policies]
    def ids(x: str | Iterable[str] | None) -> set[str]:
        return {x} if isinstance(x, str) else set(x or ())

    contender_ids = ids(contenders)
    pinned_ids = ids(pinned) | contender_ids
    pinned_keys = {c.key for c in candidates if c.policy.policy_id in pinned_ids}
    scored = score_candidates_staged(
        candidates, engines, constraints, runs=runs, stage1_runs=stage1,
        finalists=survivors, pinned=pinned_keys, volatility=volatility, seed=seed,
    )

    # Rank finalists among THEMSELVES. Eliminated policies were measured on a
    # shorter sample, and mixing the two sorts incomparable estimates: a policy
    # dropped at stage 1 could be resurrected by a lucky 100-path mean and beat
    # a finalist measured over 300. It lost on the evidence available; a noisier
    # estimate is not grounds to reinstate it. A pinned policy is measured on
    # the full sample but ranked where its stage-1 result put it; a contender
    # is measured on it and ranked with the finalists.
    def stage1_score(sp: ScoredPolicy) -> Decimal:
        return (sum(sp.path_objectives[:stage1], _ZERO) / Decimal(stage1)).quantize(_CENT)

    # The same stable sort score_candidates_staged used to pick its finalists.
    finalists = set(sorted(range(len(scored)), key=lambda i: stage1_score(scored[i]),
                           reverse=True)[:survivors])
    finalists |= {i for i, sp in enumerate(scored) if sp.policy.policy_id in contender_ids}

    def ranked(sps: list[ScoredPolicy]) -> list[ScoredPolicy]:
        return sorted(sps, key=lambda sp: (sp.score, sp.success_probability), reverse=True)

    ranked_finalists = ranked([sp for i, sp in enumerate(scored) if i in finalists])
    # Eliminated policies are still reported — with their own (smaller) path
    # count visible — but always below the finalists.
    ranked_eliminated = ranked([sp for i, sp in enumerate(scored) if i not in finalists])
    return ranked_finalists + ranked_eliminated


def _verdict(
    mean_diff: Decimal,
    median_diff: Decimal,
    ci_low: Decimal,
    ci_high: Decimal,
    materiality: Decimal,
) -> str:
    """Three states, plus a fourth that must be earned.

    Statistical non-significance is NOT equivalence. An interval of
    [-$27k, +$146k] means "we cannot tell which is better at this simulation
    budget" — reporting that as "no material difference" would overclaim in the
    opposite direction. Only an interval contained inside an explicit
    materiality threshold earns ``equivalent``; with no threshold declared the
    honest answer is ``unresolved``.

    A decisive call additionally requires the median to share the mean's sign.
    The paired distribution is severely skewed — many modest wins against a few
    catastrophic losses — so an interval that excludes zero can still rest
    entirely on a handful of paths.
    """
    if materiality > _ZERO and -materiality <= ci_low and ci_high <= materiality:
        return "equivalent"
    if ci_low > _ZERO and median_diff > _ZERO:
        return "winner"
    if ci_high < _ZERO and median_diff < _ZERO:
        return "alternative"
    return "unresolved"


def compare_paired(
    winner: ScoredPolicy,
    alternative: ScoredPolicy,
    materiality: Decimal = Decimal("0"),
) -> PairedComparison:
    """Compare two scored policies path by path.

    Both must have been scored in the same ``score_policies`` call so that
    index *i* refers to the same return sequence for each.
    """
    a, b = winner.path_objectives, alternative.path_objectives
    fa, fb = winner.path_feasible, alternative.path_feasible
    n = min(len(a), len(b))
    if n == 0:
        return PairedComparison(
            policy_id=alternative.policy.policy_id,
            mean_difference=_ZERO, median_difference=_ZERO, std_error=_ZERO,
            ci_low=_ZERO, ci_high=_ZERO, winner_win_fraction=_ZERO,
            both_feasible=0, winner_only_feasible=0,
            alternative_only_feasible=0, both_infeasible=0,
            both_feasible_mean_difference=_ZERO, verdict="unresolved",
            **_candidate_fields(alternative),
        )

    diffs = [a[i] - b[i] for i in range(n)]
    nd = Decimal(n)
    mean = sum(diffs, _ZERO) / nd

    ordered = sorted(diffs)
    mid = n // 2
    median = (
        ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / Decimal(2)
    )

    # Population std of the paired differences, then the standard error of
    # their mean. Pairing is what makes this tight: shared return sequences
    # cancel, so this is far smaller than combining two independent SEs.
    variance = sum(((d - mean) ** 2 for d in diffs), _ZERO) / nd
    se = variance.sqrt() / nd.sqrt()
    half = Decimal("1.96") * se

    both_ok = [i for i in range(n) if fa[i] and fb[i]]
    both_f_mean = (
        sum((diffs[i] for i in both_ok), _ZERO) / Decimal(len(both_ok))
        if both_ok else _ZERO
    )

    return PairedComparison(
        policy_id=alternative.policy.policy_id,
        mean_difference=mean.quantize(_CENT),
        median_difference=median.quantize(_CENT),
        std_error=se.quantize(_CENT),
        ci_low=(mean - half).quantize(_CENT),
        ci_high=(mean + half).quantize(_CENT),
        winner_win_fraction=(
            Decimal(sum(1 for d in diffs if d > _ZERO)) / nd
        ).quantize(_FOUR_PLACES),
        both_feasible=len(both_ok),
        winner_only_feasible=sum(1 for i in range(n) if fa[i] and not fb[i]),
        alternative_only_feasible=sum(1 for i in range(n) if fb[i] and not fa[i]),
        both_infeasible=sum(1 for i in range(n) if not fa[i] and not fb[i]),
        both_feasible_mean_difference=both_f_mean.quantize(_CENT),
        verdict=_verdict(mean, median, mean - half, mean + half, materiality),
        **_candidate_fields(alternative),
    )


def _candidate_fields(sp: ScoredPolicy) -> dict:
    c = sp.candidate
    if c is None:
        return {}
    return {
        "candidate_key": c.key,
        "claim_age_self": c.scenario.claim_age_self,
        "claim_age_spouse": c.scenario.claim_age_spouse,
    }


def _objective(result, settings: Settings) -> Decimal:
    """Per-path objective — ``evaluate.objective_value``, the one objective
    deterministic search and Monte Carlo share."""
    return objective_value(result, settings)


@dataclass(frozen=True)
class ScoreComponents:
    """Means of the objective's parts over the paths a score rests on.

    ``score == estate_pv − shortfall_weight × shortfall_pv −
    discretionary_shortfall_weight × discretionary_shortfall_pv`` (to the
    cent, each mean being quantised separately). Taxes are reported, not
    scored: the estate is already net of them.
    """

    estate_pv: Decimal
    shortfall_pv: Decimal
    discretionary_shortfall_pv: Decimal
    taxes_pv: Decimal


@dataclass(frozen=True)
class ScoredPolicy:
    """A policy evaluated under Monte Carlo.

    The objective is linear in its components, so its expectation is the mean
    of the per-path objective and ``score`` is simply ``mean_value``.
    """

    policy: Policy
    mean_value: Decimal          # mean per-path objective, quantised to cents
    std_value: Decimal           # population std — REPORTED ONLY, never scored
    score: Decimal               # == mean_value
    success_probability: Decimal  # fraction of runs feasible AND terminal ≥ target_estate
    # Average number of years spending came in below target, across scenarios.
    # Reported BESIDE success probability because with guardrails on the two
    # stop meaning the same thing: a plan that cuts its way to solvency "never
    # fails" while delivering less than the household asked for. 0 under the
    # default fixed-spending rule unless the plan actually runs short.
    mean_years_reduced: Decimal = Decimal("0")
    # Per-path detail, retained so policies can be compared PATH BY PATH.
    # Every policy is simulated against the same return sequences (common
    # random numbers), so pairing cancels most market noise — measured 3.8x
    # tighter than treating the two means as independent samples.
    path_objectives: tuple[Decimal, ...] = ()
    path_feasible: tuple[bool, ...] = ()
    # The policy under a claim scenario, when scored by score_candidates_staged
    # (or the adaptive wrapper, which uses the stored claim ages).
    candidate: Candidate | None = None
    # Component means on the same paths as ``score``.
    mean_components: ScoreComponents | None = None


@dataclass(frozen=True)
class PairedComparison:
    """Winner vs. one alternative, compared on identical return sequences.

    All differences are ``winner − alternative``, so positive favours the
    winner.
    """

    policy_id: str               # the alternative
    mean_difference: Decimal
    median_difference: Decimal   # robustness check: skew makes the mean fragile
    std_error: Decimal
    ci_low: Decimal
    ci_high: Decimal
    winner_win_fraction: Decimal  # share of paths on which the winner is ahead
    # Where the difference actually comes from. On a real comparison, 73 paths
    # where both plans stayed solvent favoured converting by +$190,760 while 2
    # paths where only the winner survived swung -$2,725,024 — the mean is
    # frequently hostage to a handful of paths, and this shows when that is so.
    both_feasible: int
    winner_only_feasible: int
    alternative_only_feasible: int
    both_infeasible: int
    both_feasible_mean_difference: Decimal
    verdict: str                 # winner | alternative | unresolved | equivalent
    # The alternative's candidate key and claim ages, when it has a scenario.
    candidate_key: str | None = None
    claim_age_self: int | None = None
    claim_age_spouse: int | None = None


def score_policies(
    policies: list[Policy],
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    runs: int = 100,
    volatility: Decimal = VOLATILITY,
    seed: int = 42,
) -> list[ScoredPolicy]:
    """Score and rank policies via seeded Monte Carlo simulation.

    Parameters
    ----------
    policies:
        Candidate policies (e.g. from ``search``).
    state:
        Starting simulation state (not mutated).
    engines, settings, constraints:
        Forwarded to ``simulate_path`` for each run.
    runs:
        Number of Monte Carlo draws.  ``runs=0`` activates deterministic
        passthrough mode.
    volatility:
        Standard deviation of the annual return distribution.
    risk_aversion:
        Weight on the standard deviation penalty in the score.
    seed:
        Base random seed.  Run ``r`` uses ``seed + r``.

    Returns
    -------
    list[ScoredPolicy]
        Sorted descending by ``(score, success_probability)``.
    """
    if not policies:
        return []

    # ------------------------------------------------------------------
    # runs=0: deterministic passthrough
    # ------------------------------------------------------------------
    if runs == 0:
        result: list[ScoredPolicy] = []
        for pol in policies:
            pv = _objective(pol.result, settings)
            success = _ONE if pol.result.feasible else _ZERO
            result.append(
                ScoredPolicy(
                    policy=pol,
                    mean_value=pv.quantize(_CENT),
                    std_value=_ZERO.quantize(_CENT),
                    score=pv.quantize(_CENT),
                    success_probability=success.quantize(_FOUR_PLACES),
                    mean_years_reduced=Decimal(pol.result.years_reduced),
                    # A single deterministic "path", so pairing still works.
                    path_objectives=(pv,),
                    path_feasible=(pol.result.feasible,),
                    mean_components=_mean_components([(
                        pol.result.terminal_estate_pv, pol.result.shortfall_pv,
                        pol.result.discretionary_shortfall_pv,
                        pol.result.lifetime_taxes_pv,
                    )]),
                )
            )
        result.sort(key=lambda sp: (sp.score, sp.success_probability), reverse=True)
        return result

    # ------------------------------------------------------------------
    # Draw an INDEPENDENT return for each year of each run (Common Random
    # Numbers across policies). Drawing one return per run and holding it for
    # the whole horizon treats returns as perfectly correlated year to year,
    # which inflates the annual volatility into the horizon-average volatility
    # (~5× too wide over 27 years) and makes well-funded plans read as far
    # riskier than they are. Independent per-year draws let bad years offset
    # good ones, so the horizon average clusters near the mean.
    # ------------------------------------------------------------------
    paths = _make_paths(0, runs, settings, volatility, seed)
    # No variance term. E[E − λS] is linear, so the mean IS the objective; a
    # std penalty would be the same order as the whole tax signal and decide the
    # recommendation by itself. std is retained as a diagnostic only.
    scored = [
        _build_scored(pol, *_run_paths(pol, state, engines, settings, constraints, paths))
        for pol in policies
    ]

    scored.sort(key=lambda sp: (sp.score, sp.success_probability), reverse=True)
    return scored
