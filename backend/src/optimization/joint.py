"""Joint search: Social Security claim ages and the conversion policy together.

Phases (``run_joint_optimization``):

1. Enumerate the claim-age scenarios (``claiming.enumerate_scenarios``).
2. Deterministic ``search`` in every scenario, each with its own federal-tax
   memo, discarded afterwards. One memo shared across a 48-scenario grid grew
   to 6.4M entries and a 10.5 GB peak for a 3–7% speed-up; Monte Carlo runs on
   the plain engines for the same reason (its paths rarely repeat an income).
3. Stage 1, on the common first ``stage1_runs`` paths: each eligible scenario
   contributes its top ``per_scenario_breadth`` schedules by path_value plus
   ``none``. The entered-age scenario contributes EVERY policy, pinned to the
   full sample, so "the benefit of choosing claim ages" is measured against
   the breadth a fixed-age run uses. Only the entered scenario gets that
   breadth: multiplying evaluate-every-policy across claim pairs is what the
   per-scenario screen exists to avoid. A searched person may have no entered
   age; then there is no entered scenario, nothing is pinned, and the result
   has no entered-age baselines (no comparison with ages nobody chose).
4. Stage 2: the top ``finalists`` by stage-1 score among ELIGIBLE candidates
   are extended to ``monte_carlo_runs``, with the pinned entered-age set.
   ``none`` at the winner's ages is then fully sampled if it was not already.
5. The winner is the best fully sampled eligible candidate — a finalist or a
   baseline that beats them. A diagnostic (ineligible) scenario never wins.
6. Sensitivity on the top ``sensitivity_finalists``: horizon −5/+5 and, for a
   couple under 78, each death at 78. Each finalist is rebuilt under the
   variant (``search.rebuild_policy``; nothing re-chosen) and scored on the
   full sample. Reported, never ranked.
7. Assemble: the winner's yearly plan from its own scenario, and the winner
   card, alternatives and warnings from the joint Monte Carlo results
   (``optimizer.build_report``) -- not a fresh fixed-age run, whose statistics
   would disagree with ``joint_winner``.

Every candidate sees the same return sequence on path *r* (``Random(seed + r)``),
so any two compare path by path, across scenarios too.
"""
from __future__ import annotations

import dataclasses
import resource
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from src.optimization.claiming import (
    Candidate,
    ClaimControls,
    enumerate_scenarios,
)
from src.optimization.evaluate import objective_value
from src.optimization.montecarlo import (
    ScoredPolicy,
    compare_paired,
    market_model,
    score_candidates_staged,
    score_policies,
)
from src.optimization.optimizer import (
    OBJECTIVE_ID,
    _MemoFederalEngine,
    _paired_dict,
    _tax_tables,
    build_report,
    materiality,
    mc_score_components,
)
from src.optimization.search import rebuild_policy, search
from src.optimization.state import Constraints, Engines, Settings, State

_ZERO = Decimal("0")
_CENT = Decimal("0.01")
_DEATH_AGE = 78
_HORIZON_STEP = 5

Progress = Callable[[str, int, int], None]


@dataclass(frozen=True)
class JointSearchParams:
    monte_carlo_runs: int = 300
    stage1_runs: int = 50
    per_scenario_breadth: int = 3
    finalists: int = 5
    sensitivity_finalists: int = 3
    seed: int = 42

    def normalised(self) -> JointSearchParams:
        """``stage1_runs`` can never exceed the budget; the normalised value is
        what every stored count and label uses (50 is a default, not a
        constant)."""
        runs = max(0, self.monte_carlo_runs)
        stage1 = min(max(1, self.stage1_runs), runs) if runs else 0
        return dataclasses.replace(self, monte_carlo_runs=runs, stage1_runs=stage1)


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _stage1_score(sp: ScoredPolicy, n: int) -> Decimal:
    return (sum(sp.path_objectives[:n], _ZERO) / Decimal(n)).quantize(_CENT)


def _rank_key(sp: ScoredPolicy) -> tuple[Decimal, Decimal]:
    return (sp.score, sp.success_probability)


def _stop_year(conversions, start_year: int) -> int | None:
    last = max((i for i, c in enumerate(conversions) if c > _ZERO), default=None)
    return None if last is None else start_year + last


def screen_scenario(policies, breadth: int) -> list:
    """Top *breadth* schedules by path_value plus ``none`` (search returns
    them sorted and deduplicated)."""
    picked = list(policies[:breadth])
    if not any(p.policy_id == "none" for p in picked):
        picked += [p for p in policies if p.policy_id == "none"]
    return picked


def _candidate_dict(sp: ScoredPolicy, runs: int) -> dict:
    c = sp.candidate
    m = sp.mean_components
    return {
        "key": c.key,
        "policy_id": c.policy.policy_id,
        "claim_age_self": c.scenario.claim_age_self,
        "claim_age_spouse": c.scenario.claim_age_spouse,
        "eligible": c.scenario.eligible,
        "conversion_stop_year": _stop_year(c.policy.conversions, c.scenario.settings.start_year),
        "total_conversions": float(sum(c.policy.conversions, _ZERO)),
        "score": float(sp.score),
        "success_probability": float(sp.success_probability),
        "monte_carlo_paths": len(sp.path_objectives),
        "fully_sampled": len(sp.path_objectives) == runs,
        "score_components": None if m is None else {
            "basis": "monte_carlo",
            "estate_pv": float(m.estate_pv),
            "shortfall_pv": float(m.shortfall_pv),
            "discretionary_shortfall_pv": float(m.discretionary_shortfall_pv),
            "taxes_pv": float(m.taxes_pv),
        },
        "deterministic": {
            "value": float(objective_value(c.policy.result, c.scenario.settings)),
        },
    }


def _sensitivity_variants(state: State, settings: Settings) -> list[tuple[str, Settings]]:
    out = [
        ("horizon_minus_5", dataclasses.replace(
            settings, simulation_years=max(1, settings.simulation_years - _HORIZON_STEP))),
        ("horizon_plus_5", dataclasses.replace(
            settings, simulation_years=settings.simulation_years + _HORIZON_STEP)),
    ]
    if state.age_spouse is not None and settings.first_death_year is None:
        if state.age_spouse < _DEATH_AGE:
            out.append(("spouse_dies_78", dataclasses.replace(
                settings, first_death_year=state.year + _DEATH_AGE - state.age_spouse,
                first_death_is_spouse=True)))
        if state.age_self < _DEATH_AGE:
            out.append(("self_dies_78", dataclasses.replace(
                settings, first_death_year=state.year + _DEATH_AGE - state.age_self,
                first_death_is_spouse=False)))
    return out


def run_joint_optimization(
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    controls: ClaimControls,
    params: JointSearchParams = JointSearchParams(),
    on_progress: Progress | None = None,
) -> dict:
    """Choose claim ages and a conversion policy together. See the module
    docstring for the phases; returns a plain, JSON-ready dict."""
    params = params.normalised()
    runs, stage1 = params.monte_carlo_runs, params.stage1_runs
    timings: dict[str, float] = {}
    rss: dict[str, float] = {}
    t_all = time.monotonic()

    def progress(phase: str, done: int, total: int) -> None:
        if on_progress is not None:
            on_progress(phase, done, total)

    # 1. Scenarios -----------------------------------------------------------
    scenarios, exclusions = enumerate_scenarios(state, settings, engines, controls)
    eligible = [s for s in scenarios if s.eligible]
    exclusion_dicts = [dataclasses.asdict(e) for e in exclusions]
    if not eligible:
        return {
            "status": "error",
            "error": "no_eligible_scenario",
            "message": "No claim-age pair is eligible for these inputs.",
            "search": {"mode": "joint", "exclusions": exclusion_dicts},
        }

    # 2. Deterministic search per scenario ------------------------------------
    t = time.monotonic()
    per_scenario: dict[str, list] = {}
    deterministic: dict[str, dict] = {}
    memo_entries = 0
    for i, sc in enumerate(scenarios):
        memo = _MemoFederalEngine(engines.federal)
        engines_memo = dataclasses.replace(engines, federal=memo)  # type: ignore[arg-type]
        pols = search(sc.state, engines_memo, sc.settings, constraints)
        memo_entries = max(memo_entries, len(memo._cache))
        per_scenario[sc.key] = pols
        deterministic[sc.key] = {
            "policy_id": pols[0].policy_id,
            "value": float(objective_value(pols[0].result, sc.settings)),
            "policies": len(pols),
        }
        progress("deterministic", i + 1, len(scenarios))
    timings["deterministic"] = time.monotonic() - t
    rss["deterministic"] = _peak_rss_mb()
    del memo, engines_memo

    entered = next((sc for sc in scenarios if sc.entered), None)

    if runs == 0:
        return _deterministic_only(
            state, engines, settings, constraints, scenarios, per_scenario,
            deterministic, exclusion_dicts, timings, rss, memo_entries, t_all,
        )

    # 3–4. Staged Monte Carlo -------------------------------------------------
    candidates: list[Candidate] = []
    for sc in scenarios:
        pols = per_scenario[sc.key]
        chosen = pols if sc.entered else screen_scenario(pols, params.per_scenario_breadth)
        candidates += [Candidate(sc, p) for p in chosen]
    pinned = {c.key for c in candidates if c.scenario.entered}
    del per_scenario

    t = time.monotonic()
    scored = score_candidates_staged(
        candidates, engines, constraints, runs=runs, stage1_runs=stage1,
        finalists=params.finalists, pinned=pinned, seed=params.seed,
        on_progress=lambda d, n: progress("monte_carlo", d, n),
    )
    by_cand = {sp.candidate.key: sp for sp in scored}

    def full(sp: ScoredPolicy) -> bool:
        return len(sp.path_objectives) == runs

    finalist_keys = [
        sp.candidate.key for sp in sorted(
            (sp for sp in scored if sp.candidate.scenario.eligible),
            key=lambda sp: _stage1_score(sp, stage1), reverse=True,
        )[: params.finalists]
    ] if stage1 < runs else [sp.candidate.key for sp in scored if sp.candidate.scenario.eligible]

    def best_eligible() -> ScoredPolicy:
        return max((sp for sp in by_cand.values()
                    if sp.candidate.scenario.eligible and full(sp)), key=_rank_key)

    winner = best_eligible()
    # `none` at the winner's ages, fully sampled; if the leader changes, again.
    for _ in range(3):
        none_key = f"none@{winner.candidate.scenario.key}"
        none_sp = by_cand.get(none_key)
        if none_sp is None or full(none_sp):
            break
        [none_full] = score_candidates_staged(
            [none_sp.candidate], engines, constraints, runs=runs, stage1_runs=runs,
            finalists=1, seed=params.seed,
        )
        by_cand[none_key] = none_full
        new_winner = best_eligible()
        if new_winner.candidate.key == winner.candidate.key:
            break
        winner = new_winner
    timings["monte_carlo"] = time.monotonic() - t
    rss["monte_carlo"] = _peak_rss_mb()

    best_at_entered = none_entered = None
    if entered is not None:
        entered_set = [sp for sp in by_cand.values()
                       if sp.candidate.scenario.key == entered.key]
        best_at_entered = max(entered_set, key=_rank_key)
        none_entered = by_cand[f"none@{entered.key}"]
    none_winner = by_cand[f"none@{winner.candidate.scenario.key}"]

    mat = materiality(state)
    finalists = [by_cand[k] for k in finalist_keys]
    compared: dict[str, ScoredPolicy] = {sp.candidate.key: sp for sp in finalists}
    # The public alternatives -- the ONE list a reader compares against: the
    # next three fully sampled eligible candidates (finalist or pinned
    # entered-age policy alike), plus every finalist, so no finalist is
    # reported only in a second table.
    ranked = sorted((sp for sp in by_cand.values()
                     if sp.candidate.scenario.eligible and full(sp)),
                    key=_rank_key, reverse=True)
    others = [sp for sp in ranked if sp.candidate.key != winner.candidate.key]
    runners_up = [sp for i, sp in enumerate(others)
                  if i < 3 or sp.candidate.key in finalist_keys]
    for sp in (best_at_entered, none_entered, none_winner, *runners_up):
        if sp is not None:
            compared[sp.candidate.key] = sp
    comparisons = {
        key: {**_paired_dict(compare_paired(winner, sp, mat)), "key": key}
        for key, sp in compared.items() if key != winner.candidate.key
    }

    # 6. Sensitivity ----------------------------------------------------------
    t = time.monotonic()
    top = ranked[: params.sensitivity_finalists]
    sensitivity = _sensitivity(top, engines, constraints, runs, params.seed, progress)
    timings["sensitivity"] = time.monotonic() - t
    rss["sensitivity"] = _peak_rss_mb()

    # 7. Assemble -------------------------------------------------------------
    t = time.monotonic()
    result = _assemble(
        winner, runners_up, none_winner.candidate.policy, engines, mat,
        paths_evaluated=sum(d["policies"] for d in deterministic.values()),
        runs=runs, t0=t_all,
    )
    timings["assemble"] = time.monotonic() - t
    timings["total"] = time.monotonic() - t_all

    scenario_rows = []
    for sc in scenarios:
        mine = [sp for sp in by_cand.values() if sp.candidate.scenario.key == sc.key]
        s1 = max(mine, key=lambda sp: _stage1_score(sp, stage1))
        fulls = [sp for sp in mine if full(sp)]
        f = max(fulls, key=_rank_key) if fulls else None
        scenario_rows.append({
            "key": sc.key,
            "claim_age_self": sc.claim_age_self,
            "claim_age_spouse": sc.claim_age_spouse,
            "eligible": sc.eligible,
            "entered": sc.entered,
            "deterministic": deterministic[sc.key],
            "stage1": {"policy_id": s1.candidate.policy.policy_id,
                       "score": float(_stage1_score(s1, stage1)), "paths": stage1},
            "final": None if f is None else {
                "policy_id": f.candidate.policy.policy_id,
                "score": float(f.score), "paths": len(f.path_objectives)},
        })

    result.update({
        "monte_carlo_runs": runs,
        "joint_winner": _candidate_dict(winner, runs),
        "search": {
            "mode": "joint",
            "controls": {
                "self": dataclasses.asdict(controls.self_age),
                "spouse": dataclasses.asdict(controls.spouse_age),
            },
            "exclusions": exclusion_dicts,
            "scenarios": scenario_rows,
            "stages": {
                "stage1_runs": stage1,
                # What matrix cells are compared against: the winner's own
                # score on the same first stage1_runs paths.
                "winner_stage1_score": float(_stage1_score(winner, stage1)),
                "final_runs": runs,
                "candidates": len(candidates),
                "finalists": [_candidate_dict(by_cand[k], runs) for k in finalist_keys],
                "per_scenario_breadth": params.per_scenario_breadth,
            },
            "baselines": {
                **({} if entered is None else {
                    "entered_no_conversion": _candidate_dict(none_entered, runs),
                    "entered_best_conversion": _candidate_dict(best_at_entered, runs),
                }),
                "winner_ages_no_conversion": _candidate_dict(none_winner, runs),
            },
            "comparisons": comparisons,
            "materiality": float(mat),
            "sensitivity": sensitivity,
            "assumptions": {
                "ss_cola": None if settings.ss_cola is None else float(settings.ss_cola),
                "seed": params.seed,
                "magi_proxy_note": (
                    "The two-year MAGI look-back is the same in every scenario: it was "
                    f"built from the {'entered' if entered else 'stored'} claim ages, and "
                    "a future claim cannot change income already earned."
                ),
            },
            "schedules": {
                k: [float(x) for x in by_cand[k].candidate.policy.conversions]
                for k in {winner.candidate.key, *finalist_keys, *compared}
            },
            "timings_seconds": {k: round(v, 2) for k, v in timings.items()},
            "peak_rss_mb": {k: round(v, 1) for k, v in rss.items()},
            "memo_entries": memo_entries,
        },
    })
    return result


def _assemble(winner: ScoredPolicy, runners_up: list[ScoredPolicy], none_policy,
              engines: Engines, mat: Decimal, *, paths_evaluated: int, runs: int,
              t0: float) -> dict:
    """The fixed-age result contract, filled from candidates already scored."""
    sc = winner.candidate.scenario
    yearly_plan, winning_policy, alternatives, warnings = build_report(
        winner, runners_up, none_policy, sc.state, engines, sc.settings, mat,
    )
    for card, sp in zip([winning_policy, *alternatives], [winner, *runners_up], strict=True):
        c = sp.candidate
        card.update({"key": c.key, "claim_age_self": c.scenario.claim_age_self,
                     "claim_age_spouse": c.scenario.claim_age_spouse,
                     "score": float(sp.score)})
        if runs > 0:
            # The card's score is a Monte Carlo mean, so its breakdown must be
            # too; the expected-return path's breakdown is kept, labeled.
            card["deterministic_score_components"] = card["score_components"]
            card["score_components"] = mc_score_components(sp, c.scenario.settings)
    return {
        "status": "success",
        "objective": OBJECTIVE_ID,
        "tax_tables": _tax_tables(engines, sc.settings),
        "computation_time_seconds": time.monotonic() - t0,
        "paths_evaluated": paths_evaluated,
        "monte_carlo_runs": runs,
        "market_model": market_model(sc.settings, runs),
        "starting_traditional_balance": float(sc.state.balance_traditional),
        "winning_policy": winning_policy,
        "yearly_plan": yearly_plan,
        "alternative_policies": alternatives,
        "warnings": warnings,
        "claim_ages": {"self": sc.settings.ss_claim_age_self,
                       "spouse": sc.settings.ss_claim_age_spouse},
    }


def _sensitivity(top, engines, constraints, runs, seed, progress) -> list[dict]:
    """Each top candidate rebuilt and scored under each variant."""
    if not top:
        return []
    variants = _sensitivity_variants(top[0].candidate.scenario.state,
                                     top[0].candidate.scenario.settings)
    rows: list[dict] = []
    for i, (name, _) in enumerate(variants):
        cands = []
        for sp in top:
            sc = sp.candidate.scenario
            v_settings = dict(_sensitivity_variants(sc.state, sc.settings))[name]
            v_sc = dataclasses.replace(sc, settings=v_settings)
            pol = rebuild_policy(sp.candidate.policy.policy_id, sc.state, engines,
                                 v_settings, constraints)
            cands.append(Candidate(v_sc, pol))
        scored = score_candidates_staged(cands, engines, constraints, runs=runs,
                                         stage1_runs=runs, finalists=len(cands), seed=seed)
        base = scored[0].score
        rows.append({
            "variant": name,
            "results": [{
                "key": sp.candidate.key,
                "score": float(sp.score),
                "success_probability": float(sp.success_probability),
                "vs_winner": float(sp.score - base),
                "rebuilt": "fixed rule, re-walked under the variant",
            } for sp in scored],
        })
        progress("sensitivity", i + 1, len(variants))
    return rows


def _deterministic_only(state, engines, settings, constraints, scenarios, per_scenario,
                        deterministic, exclusions, timings, rss, memo_entries, t_all) -> dict:
    """``monte_carlo_runs == 0``: a matrix of deterministic objective values per
    scenario, no stages and no finalists."""
    best = max((sc for sc in scenarios if sc.eligible),
               key=lambda sc: deterministic[sc.key]["value"])
    scored = [dataclasses.replace(sp, candidate=Candidate(best, sp.policy))
              for sp in score_policies(per_scenario[best.key], best.state, engines,
                                       best.settings, constraints, runs=0)]
    none_pol = next((p for p in per_scenario[best.key] if p.policy_id == "none"), None)
    pick = next(sp for sp in scored
                if sp.policy.policy_id == deterministic[best.key]["policy_id"])
    result = _assemble(
        pick, [sp for sp in scored if sp is not pick][:3], none_pol, engines, materiality(state),
        paths_evaluated=sum(d["policies"] for d in deterministic.values()),
        runs=0, t0=t_all,
    )
    timings["total"] = time.monotonic() - t_all
    result.update({
        "monte_carlo_runs": 0,
        "joint_winner": {
            "key": f"{deterministic[best.key]['policy_id']}@{best.key}",
            "policy_id": deterministic[best.key]["policy_id"],
            "claim_age_self": best.claim_age_self,
            "claim_age_spouse": best.claim_age_spouse,
            "deterministic": {"value": deterministic[best.key]["value"]},
        },
        "search": {
            "mode": "joint_deterministic",
            "exclusions": exclusions,
            "deterministic_matrix": [{
                "key": sc.key, "claim_age_self": sc.claim_age_self,
                "claim_age_spouse": sc.claim_age_spouse, "eligible": sc.eligible,
                "entered": sc.entered, **deterministic[sc.key],
            } for sc in scenarios],
            "timings_seconds": {k: round(v, 2) for k, v in timings.items()},
            "peak_rss_mb": {k: round(v, 1) for k, v in rss.items()},
            "memo_entries": memo_entries,
        },
    })
    return result
