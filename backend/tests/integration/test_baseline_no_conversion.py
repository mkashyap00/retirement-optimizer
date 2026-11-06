"""A fixed-age run reports `none` at the same ages, fully sampled, as the
baseline its improvement is measured against."""
from __future__ import annotations

import pytest
from src.optimization.optimizer import materiality, run_optimization
from tests.integration.test_joint import ENGINES, _couple


@pytest.fixture(scope="module")
def run():
    state, settings, constraints = _couple()
    return state, run_optimization(state, ENGINES, settings, constraints, monte_carlo_runs=9)


def test_none_is_scored_on_the_full_sample_against_the_plan(run):
    state, result = run
    base, wp = result["baseline_no_conversion"], result["winning_policy"]
    assert base["policy_id"] == "none" and base["monte_carlo_paths"] == 9
    assert base["score_difference"] == pytest.approx(wp["score"] - base["score"], abs=0.01)
    assert result["materiality"] == float(materiality(state))
    if base["is_recommendation"]:
        assert wp["policy_id"] == "none" and base["paired"] is None
    else:
        assert base["paired"]["verdict"] in {"winner", "alternative", "unresolved", "equivalent"}


def test_both_sides_of_the_baseline_carry_their_breakdown(run):
    """The page splits the score difference into estate and unfunded
    spending; each side's components reconstruct its own score."""
    _, result = run
    base = result["baseline_no_conversion"]
    for comps, score in ((base["score_components"], base["score"]),
                         (base["recommendation_score_components"],
                          result["winning_policy"]["score"])):
        assert comps["basis"] == "monte_carlo"
        rebuilt = (comps["estate_pv"] - comps["shortfall_weight"] * comps["shortfall_pv"]
                   - comps["discretionary_shortfall_weight"] * comps["discretionary_shortfall_pv"])
        assert rebuilt == pytest.approx(score, abs=0.05)


def test_alternatives_carry_their_own_score(run):
    """The alternatives table ranks on each strategy's own score; the
    paired difference agrees with it when both used every scenario."""
    _, result = run
    wp = result["winning_policy"]
    for alt in result["alternative_policies"]:
        assert isinstance(alt["score"], float)
        if alt["monte_carlo_paths"] == wp["monte_carlo_paths"]:
            assert wp["score"] - alt["score"] == pytest.approx(
                alt["paired"]["mean_difference"], abs=0.05)


def test_a_forced_none_run_is_its_own_baseline():
    state, settings, constraints = _couple()
    result = run_optimization(state, ENGINES, settings, constraints, monte_carlo_runs=9,
                              forced_policy="none")
    base = result["baseline_no_conversion"]
    assert base["is_recommendation"] and base["score_difference"] == 0


def test_none_wins_a_normal_run_when_it_scores_highest_on_the_full_sample(monkeypatch):
    """`none` eliminated at stage 1 but best over every path is the
    recommendation; a forced run keeps it as the optimizer's own pick."""
    from src.optimization import montecarlo
    state, settings, constraints = _couple()
    calls: dict[str, int] = {}
    real = montecarlo._run_paths

    def fake(pol, *a):
        objectives, feasible, succ, reduced, comps = real(pol, *a)
        first = calls.get(pol.policy_id, 0) == 0
        calls[pol.policy_id] = calls.get(pol.policy_id, 0) + 1
        if pol.policy_id == "none":
            bump = -10**7 if first else 10**8
            objectives = [o + bump for o in objectives]
        return objectives, feasible, succ, reduced, comps

    monkeypatch.setattr(montecarlo, "_run_paths", fake)
    result = run_optimization(state, ENGINES, settings, constraints, monte_carlo_runs=30)
    assert result["winning_policy"]["policy_id"] == "none"
    assert result["baseline_no_conversion"]["is_recommendation"]

    calls.clear()
    forced_id = next(a["policy_id"] for a in result["alternative_policies"])
    forced = run_optimization(state, ENGINES, settings, constraints, monte_carlo_runs=30,
                              forced_policy=forced_id)
    assert forced["optimizer_pick"] == "none"
    assert forced["winning_policy"]["policy_id"] == forced_id
