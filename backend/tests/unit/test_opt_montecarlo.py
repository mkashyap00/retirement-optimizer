"""Tests for seeded Monte Carlo with risk-adjusted scoring.

TDD RED phase: tests written BEFORE implementation.

Test (a): same seed → identical scores across two calls (determinism).
Test (b): runs=0 passthrough — score = path_value, std = 0, success = 1 if feasible.
Test (c): success_probability ∈ [0, 1]; huge-portfolio / small-spend case ≥ 0.95.
Test (d): scoring-dimension regression — score == mean_value - risk_aversion * std_value exactly.
"""

from decimal import Decimal as D

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.montecarlo import score_policies
from src.optimization.search import search
from src.optimization.state import Constraints, Engines, Settings, State

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _engines():
    rules = TaxRules()
    return Engines(
        federal=FederalTaxEngine(rules),
        state=StateTaxEngine(rules),
        irmaa=IRMAACalculator(rules),
        rmd=RMDCalculator(rules),
        ss=SocialSecurityCalculator(),
        rules=rules,
    )


def _base_state():
    """Retired single, 65, TX — all-Roth, no taxes."""
    return State(
        year=2025,
        age_self=65,
        age_spouse=None,
        balance_taxable=D("0"),
        balance_traditional=D("0"),
        balance_roth=D("2000000"),
        basis_taxable=D("0"),
        filing_status="single",
        state_code="TX",
        medicare_self=True,
    )


def _base_settings(sim_years: int = 10):
    return Settings(
        start_year=2025,
        required_spending=D("30000"),
        simulation_years=sim_years,
       
    )


def _base_constraints():
    return Constraints()


def _multi_policy_fixture():
    """A household with real conversion room, so the search returns SEVERAL
    policies. `_base_state` is all-Roth with nothing to convert, which yields
    only "none" — useless for anything about ranking or elimination."""
    state = State(
        year=2025, age_self=62, age_spouse=60,
        balance_taxable=D("400000"), basis_taxable=D("200000"),
        balance_traditional=D("1200000"), balance_roth=D("100000"),
        filing_status="joint", state_code="CA",
    )
    settings = Settings(
        start_year=2025, required_spending=D("70000"),
        simulation_years=12,
    )
    engines, constraints = _engines(), _base_constraints()
    pols = search(state, engines, settings, constraints)
    return pols, engines, settings, constraints, state


def _get_policies(state=None, settings=None, constraints=None):
    """Return a small list of policies from the greedy search."""
    s = state or _base_state()
    cfg = settings or _base_settings()
    c = constraints or _base_constraints()
    eng = _engines()
    return search(s, eng, cfg, c), eng, cfg, c, s


# ---------------------------------------------------------------------------
# Test (a): Determinism — same seed → identical results across two calls
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_scores():
    """Calling score_policies twice with the same seed must return identical scores."""
    policies, engines, settings, constraints, state = _get_policies()
    assert policies, "Need at least one policy from search"

    result_1 = score_policies(
        policies, state, engines, settings, constraints,
        runs=5, seed=42,
    )
    result_2 = score_policies(
        policies, state, engines, settings, constraints,
        runs=5, seed=42,
    )

    assert len(result_1) == len(result_2)
    for sp1, sp2 in zip(result_1, result_2, strict=True):
        assert sp1.policy.policy_id == sp2.policy.policy_id
        assert sp1.mean_value == sp2.mean_value
        assert sp1.std_value == sp2.std_value
        assert sp1.score == sp2.score
        assert sp1.success_probability == sp2.success_probability


# ---------------------------------------------------------------------------
# Test (b): runs=0 passthrough
# ---------------------------------------------------------------------------


def test_runs_zero_passthrough():
    """runs=0 returns deterministic results: score=path_value, std=0."""
    policies, engines, settings, constraints, state = _get_policies()
    assert policies

    results = score_policies(
        policies, state, engines, settings, constraints,
        runs=0,
    )

    assert len(results) == len(policies)
    for sp in results:
        assert sp.std_value == D("0"), f"std should be 0 for runs=0, got {sp.std_value}"
        assert sp.mean_value == sp.score, (
            f"score should equal mean_value for runs=0 (std=0), "
            f"got mean={sp.mean_value} score={sp.score}"
        )
        # score == path_value (the original deterministic value, quantised to cents)
        assert sp.score == sp.policy.result.path_value.quantize(D("0.01")), (
            "score should equal original path_value (quantised) for runs=0"
        )
        # success: 1 if feasible, else 0
        expected_success = D("1.0000") if sp.policy.result.feasible else D("0.0000")
        assert sp.success_probability == expected_success, (
            f"success_probability should be 1 if feasible, 0 otherwise; "
            f"got {sp.success_probability}, feasible={sp.policy.result.feasible}"
        )


# ---------------------------------------------------------------------------
# Test (c): success_probability bounds and large-portfolio sanity
# ---------------------------------------------------------------------------


def test_success_probability_in_bounds_and_high_for_rich_portfolio():
    """
    1) All success_probability values must be in [0, 1].
    2) A $2M Roth portfolio spending $30k/yr over 10 years should achieve
       success_probability >= 0.95 under typical Monte Carlo returns.
    """
    policies, engines, settings, constraints, state = _get_policies()
    assert policies

    results = score_policies(
        policies, state, engines, settings, constraints,
        runs=10, seed=99,
    )

    for sp in results:
        assert D("0") <= sp.success_probability <= D("1"), (
            f"success_probability={sp.success_probability} out of [0,1]"
        )

    # The best policy for our flush portfolio should be highly likely to succeed
    best = results[0]
    assert best.success_probability >= D("0.95"), (
        f"Expected success_probability >= 0.95 for $2M Roth / $30k spend, "
        f"got {best.success_probability}"
    )


def test_success_realistic_with_per_year_returns():
    """A comfortably-funded plan over a long horizon must read as highly likely.

    Regression for the sequence-of-returns bug: the MC used to draw ONE return
    per run and apply it to EVERY year, so ~1/3 of runs assumed a persistently
    negative return for the whole 27-year horizon and the plan "failed" ~a
    third of the time — this $3M / $75k (2.5%) plan wrongly read ~0.66. With
    independent per-year draws the horizon average clusters near the mean, so
    a comfortably-funded plan reads ~1.0.
    """
    state = State(
        year=2025,
        age_self=65,
        age_spouse=None,
        balance_taxable=D("0"),
        balance_traditional=D("0"),
        balance_roth=D("3000000"),
        basis_taxable=D("0"),
        filing_status="single",
        state_code="TX",
        medicare_self=True,
    )
    settings = Settings(
        start_year=2025,
        required_spending=D("75000"),  # 2.5% of $3M
        simulation_years=27,
       
    )
    constraints = Constraints()
    engines = _engines()
    policies = search(state, engines, settings, constraints)

    results = score_policies(
        policies, state, engines, settings, constraints, runs=100, seed=7
    )
    best = results[0]
    assert best.success_probability >= D("0.95"), (
        "A comfortably-funded plan over 27 years should read as highly likely "
        f"once returns vary year to year; got {best.success_probability}"
    )


# ---------------------------------------------------------------------------
# Test (d): Scoring-dimension regression — score formula with tolerance
# ---------------------------------------------------------------------------


def test_score_formula_with_tolerance():
    """
    Regression guard: the score is the mean per-path objective, and ranking is
    by (score, success_probability) descending.

    Was: score == mean - risk_aversion * std. The variance term is gone --
    see the objective note above -- so the guard is now that score reproduces
    E[economic] - lambda * E[unfunded proxy] from the raw path components.
    """
    policies, engines, settings, constraints, state = _get_policies()
    assert policies

    results = score_policies(
        policies, state, engines, settings, constraints, runs=7, seed=7,
    )

    for sp in results:
        # No spread penalty: score IS the mean objective.
        assert sp.score == sp.mean_value, (
            f"score={sp.score} != mean_value={sp.mean_value}; "
            f"a variance term has crept back in"
        )
        # Dimension guard: the objective must stay in dollars, never mixing a
        # probability into a dollar quantity.
        assert sp.success_probability <= D("1")
        assert sp.std_value >= D("0")

    # Verify descending sort by (score, success_probability)
    for i in range(len(results) - 1):
        a, b = results[i], results[i + 1]
        sort_key_a = (a.score, a.success_probability)
        sort_key_b = (b.score, b.success_probability)
        assert sort_key_a >= sort_key_b, (
            f"Results not sorted descending by (score, success): "
            f"position {i} has {sort_key_a} < position {i+1} has {sort_key_b}"
        )


# ---------------------------------------------------------------------------
# Test (e): target_estate branch — feasible but terminal < target → success = 0
# ---------------------------------------------------------------------------


def test_target_estate_branch_failure():
    """
    Coverage: when target_estate is set high enough that runs are feasible
    but terminal_estate < target_estate, success_probability should be 0.
    Uses small runs=3 and simulation_years=5 for speed.
    """
    state = _base_state()
    settings = _base_settings(sim_years=5)
    # Set target_estate very high (higher than starting balance of $2M)
    constraints = Constraints(target_estate=D("5000000"))

    policies, engines, _, _, _ = _get_policies(state, settings, constraints)
    assert policies, "Need at least one policy from search"

    results = score_policies(
        policies, state, engines, settings, constraints,
        runs=3, seed=123,
    )

    # With target_estate=$5M and starting Roth=$2M, success_probability should be 0
    # (no run can achieve terminal ≥ $5M given limited time and starting capital)
    for sp in results:
        assert sp.success_probability == D("0.0000"), (
            f"Expected success_probability=0 when target_estate > starting balance, "
            f"got {sp.success_probability}"
        )


# ---------------------------------------------------------------------------
# Objective: E[economic] − λ·E[unfunded proxy], with no variance penalty
# ---------------------------------------------------------------------------
#
# The old score was mean − 0.5·std of a quantity that already contained the
# infeasibility penalty, so the risk term partly measured the penalty
# function's shape rather than economic risk. Worse, standard deviation is
# symmetric: it punished strategies for occasionally producing a LARGER
# estate, which is not a risk any retiree holds.
#
# λ is a shortfall COST WEIGHT — "a PV dollar of unfunded retirement costs this
# many dollars of economic value" — NOT risk aversion. It prices the loss of
# funded consumption, not aversion to uncertainty.


def test_score_is_the_mean_objective_with_no_variance_penalty():
    policies, engines, settings, constraints, state = _get_policies()
    scored = score_policies(policies, state, engines, settings, constraints, runs=10)
    for sp in scored:
        assert sp.score == sp.mean_value, (
            f"{sp.policy.policy_id}: score {sp.score} != mean {sp.mean_value} "
            "— a variance term has crept back in"
        )
        assert sp.std_value >= D("0"), "std is still reported as a diagnostic"


def test_shortfall_weight_scales_the_penalty():
    """λ=0 ignores shortfall; raising λ can only lower a score, never raise it."""
    import dataclasses

    policies, engines, settings, constraints, state = _get_policies()

    def scores(lam: str) -> dict[str, D]:
        cfg = dataclasses.replace(settings, shortfall_weight=D(lam))
        out = score_policies(policies, state, engines, cfg, constraints, runs=10)
        return {sp.policy.policy_id: sp.score for sp in out}

    lo, mid, hi = scores("0"), scores("1"), scores("5")
    for pid in lo:
        assert lo[pid] >= mid[pid] >= hi[pid], (
            f"{pid}: score not monotonically non-increasing in shortfall_weight"
        )


def test_shortfall_weight_zero_scores_pure_economics():
    """With λ=0 an infeasible path is judged on its economics alone — the
    guard that proves the penalty is genuinely detached from economic_value."""
    import dataclasses

    from src.optimization.evaluate import simulate_path

    # Tiny portfolio, large spending → guaranteed depletion.
    state = State(
        year=2025, age_self=65, age_spouse=None,
        balance_taxable=D("0"), balance_traditional=D("0"),
        balance_roth=D("1000"), basis_taxable=D("0"),
        filing_status="single", state_code="TX",
    )
    settings = dataclasses.replace(
        _base_settings(sim_years=5), required_spending=D("50000"),
        shortfall_weight=D("0"),
    )
    engines, constraints = _engines(), _base_constraints()
    pols = search(state, engines, settings, constraints)
    scored = score_policies(pols, state, engines, settings, constraints, runs=5)

    det = simulate_path(state, [], engines, settings, constraints)
    assert det.feasible is False and det.shortfall_pv > D("0")
    # λ=0 → the shortfall contributes nothing, so the score is the economics only.
    assert scored[0].score == det.economic_value.quantize(D("0.01"))


# ---------------------------------------------------------------------------
# Paired comparison: an honest verdict instead of a manufactured winner
# ---------------------------------------------------------------------------
#
# Every policy is already simulated against the SAME return sequences (common
# random numbers), so differences between them can be compared path-by-path.
# Pairing measured 3.8x tighter than treating the two means as independent
# (SE $165,293 -> $43,633), because most market noise cancels.
#
# The verdict must be three-state. Statistical non-significance is NOT
# equivalence: a paired mean of +$59,879 with SE $43,633 gives roughly
# [-$27k, +$146k], which says "we cannot tell which is better", not "they are
# the same". Only a CI contained inside an explicit materiality threshold
# earns "equivalent".


def _paired_fixture():
    policies, engines, settings, constraints, state = _multi_policy_fixture()
    scored = score_policies(policies, state, engines, settings, constraints, runs=20)
    return scored


def test_scored_policy_retains_per_path_values_for_pairing():
    for sp in _paired_fixture():
        assert len(sp.path_objectives) == 20
        assert len(sp.path_feasible) == 20


def test_paired_comparison_reports_the_four_feasibility_groups():
    from src.optimization.montecarlo import compare_paired

    scored = _paired_fixture()
    if len(scored) < 2:
        import pytest
        pytest.skip("fixture produced a single policy")
    cmp = compare_paired(scored[0], scored[1])

    assert cmp.policy_id == scored[1].policy.policy_id
    total = (
        cmp.both_feasible
        + cmp.winner_only_feasible
        + cmp.alternative_only_feasible
        + cmp.both_infeasible
    )
    assert total == 20, "every path must land in exactly one group"
    assert D("0") <= cmp.winner_win_fraction <= D("1")
    assert cmp.ci_low <= cmp.mean_difference <= cmp.ci_high


def test_identical_policies_compare_as_exactly_zero():
    """A policy paired with itself has zero difference on every path — the
    tightest possible check that the pairing is truly path-by-path."""
    from src.optimization.montecarlo import compare_paired

    scored = _paired_fixture()
    cmp = compare_paired(scored[0], scored[0])
    assert cmp.mean_difference == D("0")
    assert cmp.median_difference == D("0")
    assert cmp.std_error == D("0")
    assert cmp.both_infeasible + cmp.both_feasible == 20
    assert cmp.winner_only_feasible == 0
    assert cmp.alternative_only_feasible == 0


def test_verdict_is_unresolved_when_the_interval_spans_zero():
    from src.optimization.montecarlo import _verdict

    # Mean clearly positive but the interval includes zero → cannot call it.
    assert _verdict(D("59879"), D("59879"), D("-27000"), D("146000"), D("0")) == "unresolved"
    # Interval strictly above zero, median agrees → the winner really wins.
    assert _verdict(D("50000"), D("40000"), D("10000"), D("90000"), D("0")) == "winner"
    # Interval strictly below zero, median agrees → the alternative wins.
    assert _verdict(D("-50000"), D("-40000"), D("-90000"), D("-10000"), D("0")) == "alternative"


def test_mean_and_median_disagreeing_in_sign_forces_unresolved():
    """Guard against a skewed distribution: the paired differences here are 73
    modest wins and 2 catastrophic losses, so the mean can point one way while
    the typical path points the other. A t-based interval alone would call
    that decisive; it is not."""
    from src.optimization.montecarlo import _verdict

    # Interval excludes zero, but the median has the opposite sign.
    assert _verdict(D("50000"), D("-1000"), D("10000"), D("90000"), D("0")) == "unresolved"


def test_equivalent_requires_an_explicit_materiality_threshold():
    from src.optimization.montecarlo import _verdict

    # Whole interval inside +/- $10k and a threshold was supplied.
    assert _verdict(D("500"), D("400"), D("-3000"), D("4000"), D("10000")) == "equivalent"
    # Same numbers, no threshold declared → we may not claim equivalence.
    assert _verdict(D("500"), D("400"), D("-3000"), D("4000"), D("0")) == "unresolved"


# ---------------------------------------------------------------------------
# Adaptive staging: spend the simulation budget on the policies still in contention
# ---------------------------------------------------------------------------
#
# Scoring every candidate at the full budget wastes most of it on policies that
# are eliminated after the first few dozen paths. Staging scores everything
# cheaply, drops the dominated ones, then spends the remainder on the finalists
# — which buys a tighter interval where it actually decides something.
#
# The paths MUST be appended to the same common set, never regenerated. Path r
# is drawn from Random(seed + r), so it is identical regardless of how many
# paths are requested; that is what lets stage 2 extend stage 1 rather than
# replace it, preserving the pairing that makes comparisons 3.8x tighter.


def test_adaptive_appends_to_the_same_common_paths():
    """A finalist's first N per-path values must equal a plain N-run scoring.

    If staging regenerated paths instead of appending, these would differ and
    the pairing benefit would silently be lost.
    """
    policies, engines, settings, constraints, state = _multi_policy_fixture()
    from src.optimization.montecarlo import score_policies_adaptive

    staged = score_policies_adaptive(
        policies, state, engines, settings, constraints, runs=30, seed=42,
    )
    plain = score_policies(
        policies, state, engines, settings, constraints, runs=10, seed=42,
    )
    plain_by_id = {sp.policy.policy_id: sp for sp in plain}

    winner = staged[0]
    ref = plain_by_id[winner.policy.policy_id]
    assert winner.path_objectives[:10] == ref.path_objectives, (
        "stage 1 paths were regenerated instead of extended — CRN broken"
    )
    assert winner.path_feasible[:10] == ref.path_feasible


def test_adaptive_gives_finalists_the_full_budget():
    policies, engines, settings, constraints, state = _multi_policy_fixture()
    from src.optimization.montecarlo import score_policies_adaptive

    staged = score_policies_adaptive(
        policies, state, engines, settings, constraints, runs=30, seed=42, survivors=2,
    )
    assert len(staged[0].path_objectives) == 30, "the winner must reach the full budget"
    # Eliminated policies are still reported, on the evidence gathered for them.
    assert all(len(sp.path_objectives) > 0 for sp in staged)
    assert len(staged) == len(policies), "no candidate should vanish from the report"


def test_adaptive_is_cheaper_than_scoring_everything_at_full_budget():
    """The whole point: fewer simulated paths for the same finalist precision."""
    import src.optimization.montecarlo as mc
    from src.optimization.montecarlo import score_policies_adaptive

    policies, engines, settings, constraints, state = _multi_policy_fixture()
    if len(policies) < 3:
        import pytest
        pytest.skip("need several policies to eliminate any")

    calls = {"n": 0}
    real = mc.simulate_path

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    mc.simulate_path = counting
    try:
        calls["n"] = 0
        score_policies_adaptive(
            policies, state, engines, settings, constraints, runs=30, seed=42, survivors=2,
        )
        staged_calls = calls["n"]
        calls["n"] = 0
        score_policies(policies, state, engines, settings, constraints, runs=30, seed=42)
        flat_calls = calls["n"]
    finally:
        mc.simulate_path = real

    assert staged_calls < flat_calls, (
        f"staging simulated {staged_calls} paths vs {flat_calls} flat — no saving"
    )


def test_adaptive_passthrough_when_runs_is_zero():
    policies, engines, settings, constraints, state = _get_policies()
    from src.optimization.montecarlo import score_policies_adaptive

    staged = score_policies_adaptive(
        policies, state, engines, settings, constraints, runs=0, seed=42,
    )
    assert len(staged) == len(policies)
    assert all(sp.std_value == D("0") for sp in staged)


def test_adaptive_never_lets_an_eliminated_policy_win():
    """REGRESSION: the first implementation sorted every policy together, so a
    candidate dropped after stage 1 — measured on a third of the paths — could
    outrank a finalist measured on all of them and be reported as the winner.
    Estimates over different sample sizes are not comparable; the eliminated
    policy lost on the evidence available and a noisier mean cannot reinstate it.
    """
    from src.optimization.montecarlo import score_policies_adaptive

    policies, engines, settings, constraints, state = _multi_policy_fixture()
    runs = 30
    staged = score_policies_adaptive(
        policies, state, engines, settings, constraints,
        runs=runs, seed=42, survivors=3,
    )
    assert len(staged[0].path_objectives) == runs, (
        "the reported winner was scored on a partial sample"
    )
    # Finalists come first, and every one of them has the full budget.
    full = [sp for sp in staged if len(sp.path_objectives) == runs]
    assert staged[: len(full)] == full, "finalists must be ranked above eliminated"


def test_a_pinned_policy_reaches_the_full_budget_even_if_eliminated():
    """A forced run reports the pinned policy whatever its rank, so it must be
    measured on the full budget. Eliminated at stage 1 it kept runs // 3
    paths while the run advertised the full count — an interval too narrow."""
    policies, engines, settings, constraints, state = _multi_policy_fixture()
    from src.optimization.montecarlo import score_policies_adaptive

    unpinned = score_policies_adaptive(
        policies, state, engines, settings, constraints, runs=30, seed=42, survivors=2,
    )
    loser = unpinned[-1].policy.policy_id
    assert len(unpinned[-1].path_objectives) == 10  # eliminated at stage 1

    pinned = score_policies_adaptive(
        policies, state, engines, settings, constraints, runs=30, seed=42, survivors=2,
        pinned=loser,
    )
    by_id = {sp.policy.policy_id: sp for sp in pinned}
    assert len(by_id[loser].path_objectives) == 30
    # Pinning measures it more; it does not promote it over the finalists.
    assert [sp.policy.policy_id for sp in pinned[:2]] == [
        sp.policy.policy_id for sp in unpinned[:2]
    ]


# ---------------------------------------------------------------------------
# Claim scenarios: score_candidates_staged
# ---------------------------------------------------------------------------


def _scenario_candidates(claim_ages=(62, 70)):
    """The multi-policy household with Social Security, under several claim
    ages for self: one candidate list spanning several scenarios."""
    import dataclasses

    from src.optimization.claiming import Candidate, ClaimScenario, scenario_key, with_claim_ages

    pols, engines, settings, constraints, state = _multi_policy_fixture()
    settings = dataclasses.replace(
        settings, ss_pia_self=D("2800"), ss_claim_age_self=67, birth_year_self=1963,
    )
    out = []
    for age in claim_ages:
        s_state, s_settings = with_claim_ages(state, settings, engines, age, None)
        sc = ClaimScenario(age, None, s_state, s_settings, scenario_key(age, None))
        for p in search(s_state, engines, s_settings, constraints)[:3]:
            out.append(Candidate(sc, p))
    return out, engines, constraints


def test_candidates_in_different_scenarios_share_the_same_paths():
    """Path r is one return sequence for every scenario, so scoring a
    candidate alone or among other scenarios' candidates gives the same
    per-path objectives — what makes cross-scenario pairing valid."""
    from src.optimization.montecarlo import score_candidates_staged

    cands, engines, constraints = _scenario_candidates()
    together = score_candidates_staged(
        cands, engines, constraints, runs=8, stage1_runs=8, finalists=2,
    )
    alone = score_candidates_staged(
        [cands[-1]], engines, constraints, runs=8, stage1_runs=8, finalists=2,
    )
    assert together[-1].path_objectives == alone[0].path_objectives
    assert [sp.candidate.key for sp in together] == [c.key for c in cands]


def test_components_reconcile_with_the_score_on_every_candidate():
    from src.optimization.montecarlo import score_candidates_staged

    cands, engines, constraints = _scenario_candidates()
    for sp in score_candidates_staged(
        cands, engines, constraints, runs=9, stage1_runs=3, finalists=2,
    ):
        s = sp.candidate.scenario.settings
        m = sp.mean_components
        rebuilt = (m.estate_pv - s.shortfall_weight * m.shortfall_pv
                   - s.discretionary_shortfall_weight * m.discretionary_shortfall_pv)
        assert abs(rebuilt - sp.score) <= D("0.02"), sp.candidate.key
        assert m.taxes_pv >= 0


def test_staged_extends_eligible_finalists_and_pinned_to_the_full_budget():
    """Finalist slots go to eligible candidates only; a pinned key reaches the
    full sample whatever its stage-1 rank; everyone else keeps stage 1."""
    import dataclasses

    from src.optimization.claiming import Candidate
    from src.optimization.montecarlo import score_candidates_staged

    cands, engines, constraints = _scenario_candidates()
    first = score_candidates_staged(
        cands, engines, constraints, runs=12, stage1_runs=4, finalists=2,
    )
    best = max(first, key=lambda sp: sum(sp.path_objectives[:4]))
    worst = min(first, key=lambda sp: sum(sp.path_objectives[:4]))

    # The stage-1 leader made ineligible (a diagnostic) loses its finalist slot.
    diag = dataclasses.replace(best.candidate.scenario, eligible=False)
    cands2 = [Candidate(diag, c.policy) if c.key == best.candidate.key else c for c in cands]
    scored = score_candidates_staged(
        cands2, engines, constraints, runs=12, stage1_runs=4, finalists=2,
        pinned={worst.candidate.key},
    )
    counts = {sp.candidate.key: len(sp.path_objectives) for sp in scored}
    assert counts[best.candidate.key] == 4
    assert counts[worst.candidate.key] == 12
    eligible_full = [k for k, n in counts.items() if n == 12 and k != worst.candidate.key]
    assert len(eligible_full) == 2
    assert sum(1 for n in counts.values() if n == 4) == len(cands) - 3


def test_scored_policies_and_comparisons_carry_the_claim_scenario():
    from src.optimization.montecarlo import compare_paired, score_candidates_staged

    cands, engines, constraints = _scenario_candidates()
    scored = score_candidates_staged(
        cands, engines, constraints, runs=6, stage1_runs=6, finalists=2,
    )
    early = next(sp for sp in scored if sp.candidate.scenario.claim_age_self == 62)
    late = next(sp for sp in scored if sp.candidate.scenario.claim_age_self == 70)
    cmp = compare_paired(early, late)
    assert cmp.candidate_key == late.candidate.key and "@70--" in cmp.candidate_key
    assert (cmp.claim_age_self, cmp.claim_age_spouse) == (70, None)


def test_a_contender_eliminated_at_stage_1_can_win_on_the_full_sample(monkeypatch):
    """REGRESSION: `none` was pinned -- measured on the full sample -- but
    ranked where stage 1 put it, so a baseline that scored higher than every
    finalist over all the paths was still reported below them. A contender
    is ranked with the finalists; a pinned (forced) policy still is not."""
    from src.optimization import montecarlo
    from src.optimization.montecarlo import score_policies_adaptive

    policies, engines, settings, constraints, state = _multi_policy_fixture()
    assert "none" in {p.policy_id for p in policies} and len(policies) > 3
    calls: dict[str, int] = {}

    def fake(pol, state, engines, settings, constraints, paths):
        first = calls.get(pol.policy_id, 0) == 0
        calls[pol.policy_id] = calls.get(pol.policy_id, 0) + 1
        if pol.policy_id == "none":
            v = D("0") if first else D("10000")    # last at stage 1, best overall
        else:
            v = D("100")
        n = len(paths)
        return [v] * n, [True] * n, n, [0] * n, [(v, D("0"), D("0"), D("0"))] * n

    monkeypatch.setattr(montecarlo, "_run_paths", fake)
    kw = dict(runs=30, seed=42, survivors=2)

    as_contender = score_policies_adaptive(
        policies, state, engines, settings, constraints, contenders="none", **kw)
    assert as_contender[0].policy.policy_id == "none"
    assert len(as_contender[0].path_objectives) == 30

    calls.clear()
    as_pinned = score_policies_adaptive(
        policies, state, engines, settings, constraints, pinned="none", **kw)
    by_id = {sp.policy.policy_id: sp for sp in as_pinned}
    assert len(by_id["none"].path_objectives) == 30
    assert as_pinned[0].policy.policy_id != "none", "a forced policy is not promoted"
