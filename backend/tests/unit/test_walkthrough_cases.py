"""The walkthrough households (benchmarks/walkthrough.py) keep showing what
docs/HOW_A_RECOMMENDATION_IS_CHOSEN.md says they show.

Deterministic only: each case runs `search` once (about a second) and checks
the property its example is built around. If one of these fails after an
engine change, re-run the walkthrough and refresh the document's tables.
"""
from __future__ import annotations

import pytest
from benchmarks.walkthrough import CASES, engines
from src.optimization.search import rule_of, search


@pytest.fixture(scope="module")
def eng():
    return engines()


@pytest.fixture(scope="module")
def policies(eng):
    out = {}
    for name, make in CASES.items():
        state, settings, constraints = make()
        out[name] = search(state, eng, settings, constraints)
    return out


def _ids(pols) -> set[str]:
    return {p.policy_id for p in pols}


@pytest.mark.parametrize("name", list(CASES))
def test_every_case_has_the_baseline_and_at_least_one_rule(policies, name):
    pols = policies[name]
    assert "none" in _ids(pols)
    assert any(rule_of(p.policy_id) is not None for p in pols)
    # `none` is genuinely all-zero.
    none = next(p for p in pols if p.policy_id == "none")
    assert all(c == 0 for c in none.conversions)


def test_happy_is_fully_funded_with_a_broad_menu(policies):
    pols = policies["happy"]
    assert len(pols) >= 50
    assert all(p.result.feasible for p in pols)


def test_tight_runs_short_under_every_strategy(policies):
    pols = policies["tight"]
    assert all(not p.result.feasible for p in pols)
    assert all(p.result.shortfall_pv > 0 for p in pols)


def test_large_builds_many_variants_and_none_trails(policies):
    pols = policies["large"]
    assert len(pols) >= 50
    # Sorted best-first by path_value; with $6M of RMDs coming, `none` is
    # near the bottom of the steady-return ranking.
    ids = [p.policy_id for p in pols]
    assert ids.index("none") > len(ids) * 0.8


def test_working_low_bracket_fills_wait_for_the_salaries_to_end(policies):
    pols = {p.policy_id: p for p in policies["working"]}
    # Both salaries are paid through 2029 (years 0-3): the 10% and 12%
    # brackets are full, so those fills convert nothing in those years.
    for rule in ("fill_10_annual", "fill_12_annual"):
        assert rule in pols, rule
        assert all(c == 0 for c in pols[rule].conversions[:4]), rule
        assert any(c > 0 for c in pols[rule].conversions[4:]), rule
    # The 22% bracket has room above the salaries from the first year.
    assert pols["fill_22_annual"].conversions[0] > 0


def test_tight_shortfall_years_come_from_the_evaluated_result(eng, policies):
    """The build table's shortfall year is the first year the full rule's
    steady-return path reports a shortfall -- not derived from the length of
    the schedule, which is one year late."""
    from benchmarks.walkthrough import CASES as cases
    from benchmarks.walkthrough import build_rows

    case = cases["tight"]()
    pols = {p.policy_id: p for p in policies["tight"]}
    for row in build_rows(case, eng, policies["tight"]):
        full = pols.get(f"{row['rule']}_annual")
        if full is None:
            assert row["shortfall_year"] is None
            continue
        assert row["shortfall_year"] == full.result.depletion_year
        # The walk stopped at that year: no conversion is scheduled in or after it.
        first_short = full.result.depletion_year - case[1].start_year
        assert all(c == 0 for c in full.conversions[first_short:]), row["rule"]
    # No conversions lasts longest on the steady path: every rule runs short earlier.
    none_year = pols["none"].result.depletion_year
    assert all(p.result.depletion_year <= none_year for p in pols.values())
