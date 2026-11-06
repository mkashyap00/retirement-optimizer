"""The joint claim-age + conversion search (optimization/joint.py)."""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import pytest
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.claiming import AgeControl, ClaimControls, ClaimInputError
from src.optimization.joint import JointSearchParams, run_joint_optimization
from src.optimization.search import search, thru_year_of
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State

_RULES = TaxRules()
ENGINES = Engines(
    federal=FederalTaxEngine(_RULES), state=StateTaxEngine(_RULES),
    irmaa=IRMAACalculator(_RULES), rmd=RMDCalculator(_RULES),
    ss=SocialSecurityCalculator(), rules=_RULES,
)
SEARCH_BOTH = ClaimControls(AgeControl("search"), AgeControl("search"))
SMALL = JointSearchParams(monte_carlo_runs=6, stage1_runs=2, finalists=2,
                          sensitivity_finalists=2)


def _couple(age_self=69, age_spouse=69, years=12, **kw):
    """Both 69 and not yet claiming: a 2×2 grid (69 or 70 each)."""
    state = State(
        year=2026, age_self=age_self, age_spouse=age_spouse,
        balance_taxable=D("300000"), basis_taxable=D("200000"),
        balance_traditional=D("1200000"), balance_roth=D("50000"),
        filing_status="joint", state_code="TX",
    )
    settings = Settings(
        start_year=2026, required_spending=D("70000"), simulation_years=years,
        ss_pia_self=D("3000"), ss_claim_age_self=70, ss_receiving_self=False,
        ss_pia_spouse=D("1800"), ss_claim_age_spouse=70, ss_receiving_spouse=False,
        birth_year_self=2026 - age_self, birth_year_spouse=2026 - age_spouse, **kw,
    )
    return state, settings, Constraints()


@pytest.fixture(scope="module")
def small_run():
    state, settings, constraints = _couple()
    events: list[tuple[str, int, int]] = []
    result = run_joint_optimization(
        state, ENGINES, settings, constraints, SEARCH_BOTH, SMALL,
        on_progress=lambda *e: events.append(e),
    )
    return result, events, (state, settings, constraints)


def test_a_two_by_two_grid_runs_every_scenario(small_run):
    result, _, _ = small_run
    keys = [s["key"] for s in result["search"]["scenarios"]]
    assert sorted(keys) == ["69-69", "69-70", "70-69", "70-70"]
    assert [s["key"] for s in result["search"]["scenarios"] if s["entered"]] == ["70-70"]


def test_baselines_and_finalists_are_fully_sampled_at_equal_counts(small_run):
    result, _, _ = small_run
    s = result["search"]
    assert s["stages"]["stage1_runs"] == 2 and s["stages"]["final_runs"] == 6
    for b in s["baselines"].values():
        assert b["monte_carlo_paths"] == 6
    for f in s["stages"]["finalists"]:
        assert f["monte_carlo_paths"] == 6 and f["eligible"]
    assert result["joint_winner"]["monte_carlo_paths"] == 6
    w = result["joint_winner"]
    assert s["baselines"]["winner_ages_no_conversion"]["key"] == (
        f"none@{w['claim_age_self']}-{w['claim_age_spouse']}"
    )
    for c in s["comparisons"].values():
        assert c["verdict"] in {"winner", "alternative", "unresolved", "equivalent"}


def test_the_winner_is_the_best_fully_sampled_eligible_candidate(small_run):
    """A baseline outside the finalists still wins if it scores best on the
    full sample; a finalist cannot win on a stage-1 lead alone."""
    result, _, _ = small_run
    s = result["search"]
    pool = s["stages"]["finalists"] + list(s["baselines"].values())
    best = max((c for c in pool if c["eligible"] and c["fully_sampled"]),
               key=lambda c: (c["score"], c["success_probability"]))
    assert result["joint_winner"]["key"] == best["key"]


def test_the_entered_scenario_carries_every_policy(small_run):
    result, _, (state, settings, constraints) = small_run
    entered = next(r for r in result["search"]["scenarios"] if r["entered"])
    n_policies = len(search(state, ENGINES, settings, constraints))
    assert entered["deterministic"]["policies"] == n_policies
    # 3 non-entered scenarios × (≤ breadth 3 + none) plus every entered policy.
    assert result["search"]["stages"]["candidates"] <= n_policies + 3 * 4


def test_sensitivity_rebuilds_finalists_and_keeps_stop_years(small_run):
    result, _, _ = small_run
    sens = {row["variant"]: row["results"] for row in result["search"]["sensitivity"]}
    assert set(sens) == {"horizon_minus_5", "horizon_plus_5", "spouse_dies_78", "self_dies_78"}
    top_keys = [r["key"] for r in sens["horizon_minus_5"]]
    assert top_keys[0] == result["joint_winner"]["key"]
    for rows in sens.values():
        # The same candidates in every variant, the winner first: rebuilt, not re-chosen.
        assert [r["key"] for r in rows] == top_keys and rows[0]["vs_winner"] == 0
    stop = thru_year_of(result["joint_winner"]["policy_id"])
    if stop is not None:
        assert result["joint_winner"]["conversion_stop_year"] <= stop


def test_progress_runs_in_phase_order(small_run):
    _, events, _ = small_run
    phases = [e[0] for e in events]
    order = ["deterministic", "monte_carlo", "sensitivity"]
    assert [p for p in order if p in phases] == order
    assert phases == sorted(phases, key=order.index)
    assert events[3] == ("deterministic", 4, 4)


def test_the_result_is_deterministic(small_run):
    result, _, (state, settings, constraints) = small_run
    again = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH, SMALL)
    assert again["joint_winner"] == result["joint_winner"]
    assert again["search"]["scenarios"] == result["search"]["scenarios"]


def test_breadth_limits_each_scenarios_candidates():
    state, settings, constraints = _couple()
    one = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH,
                                 dataclasses.replace(SMALL, per_scenario_breadth=1,
                                                     sensitivity_finalists=0))
    three = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH,
                                   dataclasses.replace(SMALL, sensitivity_finalists=0))
    assert one["search"]["stages"]["candidates"] < three["search"]["stages"]["candidates"]


def test_stage1_above_the_budget_is_normalised():
    p = JointSearchParams(monte_carlo_runs=20, stage1_runs=50).normalised()
    assert p.stage1_runs == 20
    assert JointSearchParams(monte_carlo_runs=0).normalised().stage1_runs == 0


def test_zero_runs_is_a_deterministic_matrix_without_stages():
    state, settings, constraints = _couple()
    result = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH,
                                    JointSearchParams(monte_carlo_runs=0))
    s = result["search"]
    assert s["mode"] == "joint_deterministic"
    assert "stages" not in s and len(s["deterministic_matrix"]) == 4
    best = max(s["deterministic_matrix"], key=lambda r: r["value"])
    assert result["joint_winner"]["key"] == f"{best['policy_id']}@{best['key']}"


def test_a_diagnostic_entered_scenario_never_wins_or_takes_a_finalist_slot():
    """Self entered claim 64 overlaps a salary: that scenario is scored as a
    labeled baseline but cannot be chosen."""
    state, settings, constraints = _couple(
        age_self=64, age_spouse=70, years=10,
        income_schedule=[IncomeEntry("salary", D("40000"), 2026, 2027, "self")],
    )
    settings = dataclasses.replace(settings, ss_claim_age_self=64)
    controls = ClaimControls(AgeControl("search"), AgeControl("fixed"))
    result = run_joint_optimization(state, ENGINES, settings, constraints, controls,
                                    dataclasses.replace(SMALL, sensitivity_finalists=0))
    s = result["search"]
    diag = [r for r in s["scenarios"] if not r["eligible"]]
    assert [r["key"] for r in diag] == ["64-70"] and diag[0]["entered"]
    assert all(f["eligible"] for f in s["stages"]["finalists"])
    assert result["joint_winner"]["eligible"]
    assert s["baselines"]["entered_no_conversion"]["eligible"] is False
    assert {e["age"] for e in s["exclusions"]} == {64, 65}


def test_no_eligible_scenario_is_a_validation_result():
    state, settings, constraints = _couple(
        age_self=64, age_spouse=70, years=10,
        income_schedule=[IncomeEntry("salary", D("40000"), 2026, 2027, "self")],
    )
    settings = dataclasses.replace(settings, ss_claim_age_self=64)
    result = run_joint_optimization(state, ENGINES, settings, constraints,
                                    ClaimControls(), SMALL)
    assert result["status"] == "error" and result["error"] == "no_eligible_scenario"


def test_unstated_receiving_past_the_claim_age_refuses_the_search():
    state, settings, constraints = _couple()
    settings = dataclasses.replace(settings, ss_claim_age_self=67, ss_receiving_self=None)
    with pytest.raises(ClaimInputError):
        run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH, SMALL)


def test_the_public_winner_card_carries_the_joint_monte_carlo_statistics(small_run):
    """winning_policy / alternative_policies are the joint search's own scored
    candidates, not a deterministic re-run's (which would report success 0/1
    from one path beside a 300-path joint_winner)."""
    result, _, _ = small_run
    jw, wp = result["joint_winner"], result["winning_policy"]
    assert wp["key"] == jw["key"] and wp["policy_id"] == jw["policy_id"]
    assert (wp["claim_age_self"], wp["claim_age_spouse"]) == (
        jw["claim_age_self"], jw["claim_age_spouse"])
    assert wp["score"] == jw["score"]
    assert wp["success_probability"] == jw["success_probability"]
    assert wp["monte_carlo_paths"] == result["monte_carlo_runs"] == 6
    assert result["claim_ages"] == {"self": jw["claim_age_self"],
                                    "spouse": jw["claim_age_spouse"]}
    assert "forced_policy" not in result and "optimizer_pick" not in result
    assert not any(w.startswith("Forced-policy run") for w in result["warnings"])

    assert result["alternative_policies"]
    for alt in result["alternative_policies"]:
        assert alt["key"] != wp["key"] and alt["monte_carlo_paths"] == 6
        # The same paired comparison, at the same materiality, as the search record.
        assert alt["paired"] == {k: v for k, v in result["search"]["comparisons"][alt["key"]]
                                 .items() if k != "key"}


def test_every_finalist_is_in_the_one_alternatives_list(small_run):
    result, _, _ = small_run
    listed = {result["winning_policy"]["key"], *(a["key"] for a in result["alternative_policies"])}
    assert {f["key"] for f in result["search"]["stages"]["finalists"]} <= listed


def test_assembly_does_not_rerun_the_search(monkeypatch):
    import src.optimization.joint as joint_mod

    calls: list[str] = []
    real = joint_mod.search
    monkeypatch.setattr(joint_mod, "search",
                        lambda *a, **k: calls.append("x") or real(*a, **k))
    state, settings, constraints = _couple()
    run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH,
                           dataclasses.replace(SMALL, sensitivity_finalists=0))
    assert len(calls) == 4  # once per scenario, none to format the result
    calls.clear()
    det = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH,
                                 JointSearchParams(monte_carlo_runs=0))
    assert len(calls) == 4
    assert det["winning_policy"]["key"] == det["joint_winner"]["key"]


def _reconstruct(c: dict) -> float:
    return (c["estate_pv"] - c["shortfall_weight"] * c["shortfall_pv"]
            - c["discretionary_shortfall_weight"] * c["discretionary_shortfall_pv"])


def test_each_public_breakdown_reconstructs_its_reported_score(small_run):
    """winning_policy.score is a Monte Carlo mean, so score_components must be
    the Monte Carlo means; the expected-return breakdown is kept, labeled."""
    result, _, _ = small_run
    cards = [result["winning_policy"], *result["alternative_policies"]]
    for card in cards:
        mc = card["score_components"]
        assert mc["basis"] == "monte_carlo" and mc["monte_carlo_paths"] == 6
        assert mc["score"] == card["score"]
        # Three separately quantised means: at most a cent and a half apart.
        assert _reconstruct(mc) == pytest.approx(card["score"], abs=0.02)
        det = card["deterministic_score_components"]
        assert det["basis"] == "deterministic"
        det_value = (det["terminal_estate_pv"] - det["shortfall_weight"] * det["shortfall_pv"]
                     - det["discretionary_shortfall_weight"]
                     * det["discretionary_shortfall_pv"])
        assert det_value == pytest.approx(det["deterministic_value"], abs=0.02)
    jw = result["joint_winner"]
    assert jw["score_components"]["estate_pv"] == cards[0]["score_components"]["estate_pv"]


def test_a_deterministic_only_run_keeps_deterministic_breakdowns():
    state, settings, constraints = _couple()
    result = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH,
                                    JointSearchParams(monte_carlo_runs=0))
    for card in [result["winning_policy"], *result["alternative_policies"]]:
        assert card["score_components"]["basis"] == "deterministic"
        assert "deterministic_score_components" not in card
        assert card["score"] == pytest.approx(
            card["score_components"]["deterministic_value"], abs=0.01)


def test_results_record_the_market_model_they_were_drawn_from(small_run):
    """The page and exports state the run's own assumptions from this record."""
    from src.optimization.montecarlo import VOLATILITY
    from src.optimization.optimizer import run_optimization

    state, settings, constraints = _couple()
    fixed = run_optimization(state, ENGINES, settings, constraints, monte_carlo_runs=4)
    for r in (small_run[0], fixed):
        m = r["market_model"]
        assert m["scenarios"] == r["monte_carlo_runs"]
        assert m["mean_return"] == float(settings.nominal_return)
        assert m["volatility"] == float(VOLATILITY)
        assert m["distribution"] == "normal" and m["independent_years"] is True


def test_a_search_without_entered_ages_reports_no_entered_baselines():
    """Nobody chose an age: the result compares conversions at the recommended
    ages only, never against invented "your ages"."""
    state, settings, constraints = _couple()
    settings = dataclasses.replace(settings, ss_claim_age_self=None, ss_claim_age_spouse=None)
    result = run_joint_optimization(state, ENGINES, settings, constraints, SEARCH_BOTH,
                                    dataclasses.replace(SMALL, sensitivity_finalists=0))
    s = result["search"]
    assert not any(r["entered"] for r in s["scenarios"])
    assert set(s["baselines"]) == {"winner_ages_no_conversion"}
    assert result["status"] == "success" and result["joint_winner"]["eligible"]
    assert result["starting_traditional_balance"] == 1_200_000
