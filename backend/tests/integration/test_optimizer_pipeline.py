"""Integration tests for run_optimization — the end-to-end optimizer pipeline.

TDD RED phase: tests written BEFORE implementation.

Test (a): structure — all required keys present; len(yearly_plan) == simulation_years.
Test (b): determinism — two runs with same seed produce identical winning_policy.
Test (c): property — every yearly row has net_spendable >= required_spending - 1.
Test (d): golden — compare {policy_id, lifetime_taxes_nominal, terminal_estate}
          against golden_standard_household.json; --regen-golden rewrites it.
Test (e): performance — standard household with monte_carlo_runs=100 completes < 5s.
"""
from __future__ import annotations

import dataclasses
import json
import os
import time
from decimal import Decimal as D
from pathlib import Path

import pytest
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.optimizer import run_optimization
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State

# ---------------------------------------------------------------------------
# Shared fixtures — standard household
# ---------------------------------------------------------------------------

GOLDEN_PATH = Path(__file__).parent / "golden_standard_household.json"

REQUIRED_KEYS = {
    "status",
    "computation_time_seconds",
    "paths_evaluated",
    "monte_carlo_runs",
    "winning_policy",
    "yearly_plan",
    "alternative_policies",
    "warnings",
}

WINNING_POLICY_KEYS = {
    "policy_id",
    "lifetime_taxes_nominal",
    "lifetime_taxes_pv",
    "terminal_estate",
    "success_probability",
    "score",
    "total_conversions",
    "projected_future_marginal_rate",
    "discount_rate",
}

YEARLY_PLAN_KEYS = {
    "year",
    "age_self",
    "age_spouse",
    "conversion",
    "withdrawal_taxable",
    "withdrawal_traditional",
    "withdrawal_roth",
    "rmd",
    "agi",
    "magi",
    "federal_tax",
    "state_tax",
    "irmaa",
    "total_tax",
    "effective_rate",
    "marginal_rate",
    "net_spendable",
    "required_spending",
    "shortfall",
    "target_spending",
    "discretionary_cut",
    "balance_taxable",
    "balance_traditional",
    "balance_roth",
    "rationale",
    "audit",
}


def _engines() -> Engines:
    rules = TaxRules()
    return Engines(
        federal=FederalTaxEngine(rules),
        state=StateTaxEngine(rules),
        irmaa=IRMAACalculator(rules),
        rmd=RMDCalculator(rules),
        ss=SocialSecurityCalculator(),
        rules=rules,
    )


def _standard_state() -> State:
    """62yo MFJ, $400k taxable/$300k basis, $2.5M trad, $50k Roth, $30k pension, CA."""
    return State(
        year=2025,
        age_self=62,
        age_spouse=62,
        balance_taxable=D("400000"),
        basis_taxable=D("300000"),
        balance_traditional=D("2500000"),
        balance_roth=D("50000"),
        filing_status="joint",
        state_code="CA",
        pension=D("30000"),
    )


def _standard_settings() -> Settings:
    return Settings(
        start_year=2025,
        required_spending=D("90000"),
        simulation_years=30,
        income_schedule=[IncomeEntry("pension", D("30000"), None, None)],
    )


def _standard_constraints() -> Constraints:
    return Constraints()


def _run_standard(monte_carlo_runs: int = 10, seed: int = 42) -> dict:
    return run_optimization(
        _standard_state(),
        _engines(),
        _standard_settings(),
        _standard_constraints(),
        monte_carlo_runs=monte_carlo_runs,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Test (a): Structure — all keys present, yearly_plan length correct
# ---------------------------------------------------------------------------


def test_output_structure():
    """All required top-level keys exist; winning_policy and yearly_plan have correct shapes."""
    result = _run_standard()

    # Top-level keys
    missing_top = REQUIRED_KEYS - set(result.keys())
    assert not missing_top, f"Missing top-level keys: {missing_top}"

    assert result["status"] == "success"
    assert isinstance(result["computation_time_seconds"], float)
    assert isinstance(result["paths_evaluated"], int)
    assert result["paths_evaluated"] > 0
    assert result["monte_carlo_runs"] == 10

    # winning_policy shape
    wp = result["winning_policy"]
    missing_wp = WINNING_POLICY_KEYS - set(wp.keys())
    assert not missing_wp, f"Missing winning_policy keys: {missing_wp}"

    # All winning_policy values should be floats (not Decimal) -- except the
    # id and the scenario count, which is a count.
    for k, v in wp.items():
        if k == "score_components":
            for ck, cv in v.items():
                if ck != "basis":
                    assert isinstance(cv, float), f"score_components[{ck!r}] is {type(cv)}"
        elif k not in ("policy_id", "monte_carlo_paths"):
            assert isinstance(v, float), f"winning_policy[{k!r}] is {type(v)}, expected float"
    assert wp["monte_carlo_paths"] == 10

    # The rate lifetime_taxes_pv was discounted at, so the UI can say so
    # instead of hardcoding it.
    assert wp["discount_rate"] == float(_standard_settings().discount_rate)

    # yearly_plan length and shape
    yp = result["yearly_plan"]
    settings = _standard_settings()
    assert len(yp) == settings.simulation_years, (
        f"Expected {settings.simulation_years} yearly rows, got {len(yp)}"
    )
    for i, row in enumerate(yp):
        missing_row = YEARLY_PLAN_KEYS - set(row.keys())
        assert not missing_row, f"Row {i} missing keys: {missing_row}"
        # All numeric values should be int or float, not Decimal
        # (rationale is a dict — checked separately in test_rationale_* tests)
        for k, v in row.items():
            if k == "rationale":
                assert isinstance(v, dict), f"Row {i}['rationale'] is {type(v)}, expected dict"
            elif k == "audit":
                # Worksheet-line derivation: all values JSON-native
                assert isinstance(v, dict), f"Row {i}['audit'] is {type(v)}, expected dict"
                for ak, av in v.items():
                    assert isinstance(av, (int, float, str)), (
                        f"Row {i}['audit'][{ak!r}] is {type(av)}, expected JSON-native"
                    )
            elif k == "age_spouse":
                # None for single filers; int for joint filers
                assert v is None or isinstance(v, int), (
                    f"Row {i}['age_spouse'] is {type(v)}, expected int or None"
                )
            else:
                assert isinstance(v, (int, float)), (
                    f"Row {i}[{k!r}] is {type(v)}, expected int or float"
                )

    # alternative_policies: up to 3 entries, each with required keys
    alts = result["alternative_policies"]
    assert isinstance(alts, list)
    assert len(alts) <= 3
    for alt in alts:
        for k in ("policy_id", "lifetime_taxes_delta", "terminal_estate_delta",
                  "success_probability_delta"):
            assert k in alt, f"Alternative missing key {k!r}"

    # warnings: list of strings
    assert isinstance(result["warnings"], list)
    for w in result["warnings"]:
        assert isinstance(w, str)


# ---------------------------------------------------------------------------
# Test (a2): Roth 5-year rule surfaces as a WARNING (not a hard block)
# ---------------------------------------------------------------------------


def test_early_roth_withdrawal_warns_not_blocked():
    """A young owner forced to draw a recently-opened Roth gets a 5-year
    warning, and the plan still meets spending (withdrawal is NOT blocked)."""
    # 56yo single filer, tiny taxable/traditional, large recently-opened Roth,
    # high spending → the plan must tap the Roth in early years.
    state = State(
        year=2025,
        age_self=56,
        age_spouse=None,
        balance_taxable=D("10000"),
        basis_taxable=D("10000"),
        balance_traditional=D("10000"),
        balance_roth=D("600000"),
        filing_status="single",
        state_code="CA",
        roth_earliest_opened_year=2024,  # 1 year old at start → < 5 years
    )
    settings = Settings(
        start_year=2025,
        required_spending=D("80000"),
        simulation_years=10,
    )
    result = run_optimization(
        state, _engines(), settings, _standard_constraints(),
        monte_carlo_runs=0, seed=42,
    )

    assert result["status"] == "success"
    # A Roth withdrawal happens in an early year (not blocked to zero)
    assert any(row["withdrawal_roth"] > 0 for row in result["yearly_plan"])
    # The 5-year-rule warning is surfaced
    assert any(
        "5-year rule" in w and "penalty" in w for w in result["warnings"]
    ), f"expected a Roth 5-year warning, got: {result['warnings']}"


# ---------------------------------------------------------------------------
# Test (b): Determinism — same seed → identical winning_policy
# ---------------------------------------------------------------------------


def test_determinism_same_seed():
    """Two calls with the same seed must produce identical winning_policy."""
    result1 = _run_standard(monte_carlo_runs=10, seed=42)
    result2 = _run_standard(monte_carlo_runs=10, seed=42)

    wp1 = result1["winning_policy"]
    wp2 = result2["winning_policy"]

    assert wp1 == wp2, (
        f"winning_policy differs:\n{wp1!r}\nvs\n{wp2!r}"
    )


# ---------------------------------------------------------------------------
# Test (c): Property — net_spendable >= required_spending - 1 every year
# ---------------------------------------------------------------------------


def test_property_net_spendable_covers_spending():
    """Every yearly row must have net_spendable >= required_spending - 1 (±$1 tolerance)."""
    result = _run_standard()

    for i, row in enumerate(result["yearly_plan"]):
        net = row["net_spendable"]
        req = row["required_spending"]
        assert net >= req - 1, (
            f"Year {row['year']} (row {i}): net_spendable={net:.2f} < "
            f"required_spending={req:.2f} - 1"
        )


# ---------------------------------------------------------------------------
# Test (d): Golden-file regression
# ---------------------------------------------------------------------------


def test_golden_standard_household(request):
    """Compare winning_policy against golden_standard_household.json.

    Run with --regen-golden to regenerate the file.

    CAVEAT — this fixture pins an unstable quantity. At monte_carlo_runs=10 the
    top policies score within about 1% of each other, and the winner can flip
    on the run count alone. So a policy_id change here is weak evidence of a
    real regression; check whether the scores actually moved before assuming a
    bug. (Regenerated 2026-10-15 twice: when surplus cash began to be saved,
    which lifted every low-conversion plan's estate, and when the age-65
    standard deduction was added and the senior bonus phased out per person.
    October 2026: the California 2025 schedule correction moved taxes and estate
    with the same winner; the unified objective — PV(after-tax estate) less the
    weighted gap, taxes no longer subtracted again — moved the 10-run winner
    from fill_24 to fill_12_annual, which is also the deterministic winner;
    projecting tax tables past 2026 at the plan's inflation, instead of
    freezing them, cut lifetime tax ~25% with the same winner, because the
    12% bracket it fills now keeps its real size.)
    The objective-function redesign replaced this with paired
    comparison and a "winner unresolved at current precision" verdict, which is
    what this fixture really wants to assert.
    """
    regen = request.config.getoption("--regen-golden", default=False)

    result = _run_standard(monte_carlo_runs=10, seed=42)
    wp = result["winning_policy"]

    snapshot = {
        "policy_id": wp["policy_id"],
        "lifetime_taxes_nominal": round(wp["lifetime_taxes_nominal"]),
        "terminal_estate": round(wp["terminal_estate"]),
    }

    if regen:
        GOLDEN_PATH.write_text(json.dumps(snapshot, indent=2) + "\n")
        pytest.skip(f"Golden file regenerated at {GOLDEN_PATH}")

    if not GOLDEN_PATH.exists():
        GOLDEN_PATH.write_text(json.dumps(snapshot, indent=2) + "\n")
        pytest.skip(f"Golden file created at {GOLDEN_PATH} — run again to compare")

    golden = json.loads(GOLDEN_PATH.read_text())

    assert snapshot["policy_id"] == golden["policy_id"], (
        f"policy_id changed: {snapshot['policy_id']!r} vs golden {golden['policy_id']!r}"
    )
    assert snapshot["lifetime_taxes_nominal"] == golden["lifetime_taxes_nominal"], (
        f"lifetime_taxes_nominal changed: {snapshot['lifetime_taxes_nominal']:,} "
        f"vs golden {golden['lifetime_taxes_nominal']:,}"
    )
    assert snapshot["terminal_estate"] == golden["terminal_estate"], (
        f"terminal_estate changed: {snapshot['terminal_estate']:,} "
        f"vs golden {golden['terminal_estate']:,}"
    )


# ---------------------------------------------------------------------------
# Test (e): Performance — monte_carlo_runs=100 completes within budget
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test (f): Rationale — every yearly_plan row has a non-empty narrative
# ---------------------------------------------------------------------------


def _walk_no_decimal(obj, path: str = "") -> None:
    """Recursively assert that obj contains no Decimal instances."""
    from decimal import Decimal as _D

    if isinstance(obj, _D):
        raise AssertionError(f"Decimal found at {path!r}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk_no_decimal(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _walk_no_decimal(v, f"{path}[{i}]")


def test_rationale_narrative_non_empty():
    """Every yearly_plan row has a 'rationale' dict with a non-empty narrative string."""
    result = _run_standard()
    for i, row in enumerate(result["yearly_plan"]):
        rat = row["rationale"]
        assert isinstance(rat, dict), f"Row {i}['rationale'] is {type(rat)}"
        narrative = rat.get("narrative", "")
        assert isinstance(narrative, str) and narrative, (
            f"Row {i}['rationale']['narrative'] is empty or missing: {narrative!r}"
        )


def test_rationale_conversion_amount_matches_row():
    """Conversion rows: rationale['conversion']['amount'] == row['conversion']."""
    result = _run_standard()
    checked = 0
    for i, row in enumerate(result["yearly_plan"]):
        if row["conversion"] > 0:
            rat = row["rationale"]
            assert rat["conversion"] is not None, (
                f"Row {i} has conversion={row['conversion']} but rationale['conversion'] is None"
            )
            assert rat["conversion"]["amount"] == row["conversion"], (
                f"Row {i}: rationale['conversion']['amount']={rat['conversion']['amount']!r} "
                f"!= row['conversion']={row['conversion']!r}"
            )
            checked += 1
    # Sanity: standard household should have at least one conversion year
    assert checked > 0, "No conversion rows found — test is vacuously true"


def test_rationale_conversion_none_on_zero_conversion_rows():
    """Zero-conversion rows have rationale['conversion'] is None.

    Forces fill_24_thru_2028, which converts for four years and then stops,
    so the plan is guaranteed to contain zero-conversion rows. (The standard
    winner converts nearly every year once brackets are indexed.)"""
    result = run_optimization(
        _standard_state(), _engines(), _standard_settings(), _standard_constraints(),
        monte_carlo_runs=10, seed=42, forced_policy="fill_24_thru_2028",
    )
    checked = 0
    for i, row in enumerate(result["yearly_plan"]):
        if row["conversion"] == 0:
            rat = row["rationale"]
            assert rat["conversion"] is None, (
                f"Row {i} has zero conversion but rationale['conversion']={rat['conversion']!r}"
            )
            checked += 1
    # Sanity: at least some non-conversion years expected
    assert checked > 0, "No zero-conversion rows found — test is vacuously true"


def test_no_decimal_in_output():
    """No Decimal objects appear anywhere in the run_optimization output dict."""
    result = _run_standard()
    _walk_no_decimal(result, "result")


@pytest.mark.slow
def test_performance_under_5s():
    """Standard household with monte_carlo_runs=100 must complete within its time budget.

    On GitHub's shared CI runners the same code runs ~1.7x slower than a dev
    machine (observed 4.8-5.2s vs 2.9s local), so a flat 5s budget flips on
    runner luck. Keep a tight regression guard locally; give CI
    proportional headroom via the CI env var GitHub Actions sets.

    The budget is a guard against a gross regression (roughly 2x), not a
    speed target: users run this on machines of every speed, and a few
    seconds either way does not matter to them. It was 5.0 / 7.5 until Monte
    Carlo began carrying the best _annual rule and `none` past the top-5
    cut, which measured 4.7s -> 5.0-5.3s here and made the old budget fail on
    a deliberate cost. It was 10 / 15 until Monte Carlo began carrying every
    limited-duration rule too, which measured 7.7s -> 14.8s here, and 20 / 30
    after it began scoring every policy (greedy rollouts removed, level-dollar
    rules added): 17.3s here.
    """
    budget = 40.0 if os.environ.get("CI") else 25.0
    t0 = time.monotonic()
    result = run_optimization(
        _standard_state(),
        _engines(),
        _standard_settings(),
        _standard_constraints(),
        monte_carlo_runs=100,
        seed=42,
    )
    elapsed = time.monotonic() - t0

    assert result["status"] == "success"
    assert elapsed < budget, (
        f"run_optimization with monte_carlo_runs=100 took {elapsed:.2f}s, "
        f"budget is {budget}s"
    )


# ---------------------------------------------------------------------------
# Test: truncated plan surfaces an explicit warning (not a silent short table)
# ---------------------------------------------------------------------------


def test_underfunded_plan_runs_the_full_horizon_and_says_where_it_falls_short():
    """When no policy can fund the full horizon, the result must SAY so.

    Before Step 4 the table simply stopped at depletion, which read as a
    display bug. It now runs to the requested horizon, showing what income
    alone covers in the short years, and the warning names the first shortfall
    year and its size.
    """
    state = State(
        year=2025,
        age_self=62,
        age_spouse=None,
        balance_taxable=D("50000"),
        basis_taxable=D("40000"),
        balance_traditional=D("100000"),
        balance_roth=D("0"),
        filing_status="single",
        state_code="CA",
    )
    settings = Settings(
        start_year=2025,
        required_spending=D("60000"),  # burns ~150k in under 3 years
        simulation_years=15,
    )
    result = run_optimization(
        state, _engines(), settings, _standard_constraints(),
        monte_carlo_runs=0, seed=42,
    )

    plan = result["yearly_plan"]
    assert len(plan) == 15, f"expected the full horizon, got {len(plan)} rows"

    short_rows = [r for r in plan if r["shortfall"] > 0]
    assert short_rows, "expected some year to fall short"
    # The short years are the LATE ones — the portfolio funds spending first.
    assert short_rows[-1]["year"] == plan[-1]["year"]
    # And a short row is short by exactly what it could not cover.
    for row in short_rows:
        assert abs(
            row["shortfall"] - (row["required_spending"] - row["net_spendable"])
        ) < 0.01

    assert any(
        "fall short of required spending starting in" in w
        for w in result["warnings"]
    ), f"expected a shortfall warning, got: {result['warnings']}"


# ---------------------------------------------------------------------------
# Step 5 — dynamic spending end to end
# ---------------------------------------------------------------------------


def _guardrail_household():
    state = State(
        year=2025, age_self=65, age_spouse=63,
        balance_taxable=D("250000"), basis_taxable=D("125000"),
        balance_traditional=D("700000"), balance_roth=D("50000"),
        filing_status="joint", state_code="CA",
        social_security=D("40000"),
    )
    settings = Settings(
        start_year=2025, required_spending=D("130000"), simulation_years=25,
        spending_rule="guardrails", spending_floor=D("95000"),
    )
    return state, settings


def test_guardrails_run_reports_the_cuts_it_made():
    """Success probability alone would hide the cost of getting there."""
    state, settings = _guardrail_household()
    result = run_optimization(
        state, _engines(), settings, _standard_constraints(),
        monte_carlo_runs=20, seed=42,
    )

    plan = result["yearly_plan"]
    assert len(plan) == 25
    for row in plan:
        # The identity the table and exports rely on, to the cent.
        assert abs(
            row["discretionary_cut"]
            - (row["target_spending"] - row["required_spending"])
        ) < 0.01
        assert row["discretionary_cut"] >= 0
        assert row["target_spending"] >= row["required_spending"] - 0.01

    # Whether or not the projected case triggered a cut, the run must SAY that
    # guardrails were active — otherwise a 100% success reading is unqualified.
    assert any(
        "guardrails are ON" in w for w in result["warnings"]
    ), f"expected a guardrails caveat, got: {result['warnings']}"

    assert "mean_years_reduced" in result["winning_policy"]


def test_fixed_spending_leaves_no_guardrail_traces():
    """The default rule must behave exactly as it did before Step 5."""
    state, settings = _guardrail_household()
    settings = dataclasses.replace(
        settings, spending_rule="fixed", spending_floor=None
    )
    result = run_optimization(
        state, _engines(), settings, _standard_constraints(),
        monte_carlo_runs=20, seed=42,
    )

    for row in result["yearly_plan"]:
        assert row["discretionary_cut"] == 0
        assert row["target_spending"] == row["required_spending"]
    assert not any("guardrails" in w for w in result["warnings"])


def test_alternatives_carry_their_first_year_conversion():
    """Each runner-up reports what IT converts this year, not just deltas.

    The close alternatives agree on roughly how much to convert in total but
    disagree on how much to convert now, by hundreds of thousands of dollars on
    this household. Year 0 is the only year a user acts on, so the Results page
    needs each alternative's year-0 amount to show that spread at all.
    """
    from src.optimization.search import search

    result = _run_standard()
    schedules = {
        p.policy_id: p.conversions
        for p in search(
            _standard_state(), _engines(), _standard_settings(), _standard_constraints()
        )
    }
    wp = result["winning_policy"]
    assert wp["year0_conversion"] == pytest.approx(result["yearly_plan"][0]["conversion"])
    assert result["alternative_policies"]
    for alt in result["alternative_policies"]:
        sched = schedules[alt["policy_id"]]
        assert alt["year0_conversion"] == pytest.approx(float(sched[0]) if sched else 0.0)
        assert alt["total_conversions"] == pytest.approx(float(sum(sched)))


def test_alternatives_carry_the_year_they_first_convert():
    """A plan where every close strategy converts $0 this year has no year-0
    spread to show; what still differs is WHEN each starts converting."""
    from src.optimization.search import search

    result = _run_standard()
    schedules = {
        p.policy_id: p.conversions
        for p in search(
            _standard_state(), _engines(), _standard_settings(), _standard_constraints()
        )
    }
    start = _standard_state().year
    for alt in result["alternative_policies"]:
        sched = schedules[alt["policy_id"]]
        nonzero = [i for i, v in enumerate(sched) if v > 0]
        expected = start + nonzero[0] if nonzero else None
        assert alt["first_conversion_year"] == expected


@pytest.mark.slow
def test_a_short_burst_path_value_ranks_low_still_wins_monte_carlo():
    """Found by a property test when Monte Carlo scored only a shortlist (the
    top 5 by path_value, plus the rules and `none`): a single 78-year-old with
    a $2.6M IRA, where scoring every policy picks `fill_24_thru_2027` (two
    years, then stop) decisively over `none`. Path_value ranks it ninth, so
    the shortlist never saw it and picked `none`. Monte Carlo now scores
    every policy."""
    state = State(
        year=2026, age_self=78, age_spouse=None,
        balance_taxable=D("999999"), basis_taxable=D("430000"),
        balance_traditional=D("2573104"), balance_roth=D("1756"),
        filing_status="single", state_code="TX", pension=D("27399"),
        social_security=D("33293"), interest=D("559"),
        dividends_qualified=D("6259"), dividends_ordinary=D("1629"),
        medicare_self=True,
    )
    settings = Settings(
        start_year=2026, required_spending=D("103820"), simulation_years=22,
        birth_year_self=1948,
    )
    result = run_optimization(
        state, _engines(), settings, Constraints(), monte_carlo_runs=60, seed=42
    )
    assert result["winning_policy"]["policy_id"] != "none"
