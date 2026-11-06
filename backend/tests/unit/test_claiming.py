"""Claim-age scenarios: eligible ages, exclusions, and per-scenario inputs."""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import pytest
from benchmarks.greedy_vs_rules import build_case
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.claiming import (
    AgeControl,
    ClaimControls,
    ClaimInputError,
    assumed_filing_people,
    check_pinned_ages,
    claim_age_options,
    enumerate_scenarios,
    legacy_inference_people,
    receiving_error,
    require_claim_ages,
    with_claim_ages,
)
from src.optimization.state import IncomeEntry, Settings, State

_RULES = TaxRules()


def _engines():
    from src.optimization.state import Engines

    return Engines(
        federal=FederalTaxEngine(_RULES), state=StateTaxEngine(_RULES),
        irmaa=IRMAACalculator(_RULES), rmd=RMDCalculator(_RULES),
        ss=SocialSecurityCalculator(), rules=_RULES,
    )


ENGINES = _engines()
SEARCH_BOTH = ClaimControls(AgeControl("search"), AgeControl("search"))


def _couple(age_self=60, age_spouse=58, **settings_kw):
    state = State(
        year=2026, age_self=age_self, age_spouse=age_spouse,
        balance_taxable=D("200000"), balance_traditional=D("900000"),
        balance_roth=D("0"), basis_taxable=D("150000"),
        filing_status="joint", state_code="TX",
        magi_two_years_ago=D("80000"), magi_last_year=D("81000"),
    )
    kw = dict(
        start_year=2026, required_spending=D("80000"), simulation_years=30,
        ss_pia_self=D("3000"), ss_claim_age_self=67,
        ss_pia_spouse=D("1500"), ss_claim_age_spouse=67,
        birth_year_self=2026 - age_self, birth_year_spouse=2026 - age_spouse,
    )
    kw.update(settings_kw)
    return state, Settings(**kw)


# ---------------------------------------------------------------------------
# Grid bounds and exclusions
# ---------------------------------------------------------------------------


def test_a_person_under_62_with_no_salary_can_claim_at_62_through_70():
    state, settings = _couple()
    ages, excl = claim_age_options("self", state, settings)
    assert ages == list(range(62, 71)) and excl == []


def test_the_grid_starts_at_todays_age():
    state, settings = _couple(age_self=65)
    assert claim_age_options("self", state, settings)[0] == list(range(65, 71))


def test_a_salaried_couple_searches_six_by_seven_with_salary_exclusions():
    """Self (63) earns to 2027, spouse (60) to 2029; claiming while a salary
    is still paid before FRA would trip the earnings test."""
    state, settings, _ = build_case("salaried_couple")
    self_ages, self_excl = claim_age_options("self", state, settings)
    spouse_ages, spouse_excl = claim_age_options("spouse", state, settings)
    assert self_ages == list(range(65, 71))
    assert spouse_ages == list(range(64, 71))
    assert [(e.age, e.reason) for e in self_excl] == [
        (63, "salary paid 2026–2027, before full retirement age"),
        (64, "salary paid 2027, before full retirement age"),
    ]
    assert [e.age for e in spouse_excl] == [62, 63]

    scenarios, _ = enumerate_scenarios(state, settings, ENGINES, SEARCH_BOTH)
    assert sum(s.eligible for s in scenarios) == 42
    assert len(scenarios) == 42  # the entered ages (68, 66) are in the grid


def test_a_joint_salary_excludes_both_people():
    state, settings = _couple(
        income_schedule=[IncomeEntry("salary", D("60000"), 2026, 2029, "joint")]
    )
    # self 60 -> claiming at 62 (2028) or 63 (2029) overlaps; spouse 58 -> 62 is 2030.
    assert claim_age_options("self", state, settings)[0][0] == 64
    assert claim_age_options("spouse", state, settings)[0][0] == 62


def test_a_salary_after_fra_excludes_nothing():
    state, settings = _couple(
        age_self=66,
        income_schedule=[IncomeEntry("salary", D("60000"), 2027, None, "self")],
    )
    # FRA for 1960 is 67 -> 2027; claiming at 66 (2026) leaves 2026 before FRA
    # with no salary yet, so 66 survives too.
    assert claim_age_options("self", state, settings)[0] == list(range(66, 71))


def test_an_open_ended_salary_excludes_every_age_before_fra():
    state, settings = _couple(
        income_schedule=[IncomeEntry("salary", D("60000"), None, None, "self")]
    )
    assert claim_age_options("self", state, settings)[0] == [67, 68, 69, 70]


# ---------------------------------------------------------------------------
# PIA, receiving, over 70
# ---------------------------------------------------------------------------


def test_no_pia_is_no_dimension_when_fixed_and_an_error_when_searched():
    state, settings = _couple(ss_pia_spouse=None, ss_claim_age_spouse=None)
    assert claim_age_options("spouse", state, settings, "fixed") == ([], [])
    with pytest.raises(ClaimInputError, match="0 if none"):
        claim_age_options("spouse", state, settings, "search")


def test_a_zero_pia_is_a_real_dimension():
    state, settings = _couple(ss_pia_spouse=D("0"))
    assert claim_age_options("spouse", state, settings)[0] == list(range(62, 71))


def test_someone_already_receiving_is_locked_to_their_claim():
    state, settings = _couple(age_self=66, ss_claim_age_self=63, ss_receiving_self=True)
    assert claim_age_options("self", state, settings) == ([63], [])


def test_over_70_and_not_receiving_files_now_at_70():
    state, settings = _couple(age_self=73, ss_claim_age_self=70, ss_receiving_self=False)
    assert claim_age_options("self", state, settings) == ([70], [])
    assert assumed_filing_people(state, settings) == ["self"]


def test_receiving_flag_contradictions():
    assert receiving_error("self", 66, 68, True) is not None     # cannot have claimed at 68
    assert receiving_error("self", 66, 64, False) is not None    # 64 is in the past
    assert receiving_error("self", 66, 66, False) is None        # files this year
    assert receiving_error("self", 73, 70, False) is None        # over 70: file now
    assert receiving_error("self", 73, 69, False) is not None
    assert receiving_error("self", 66, 64, None) is None         # unknown: legacy reading


def test_unknown_receiving_past_the_claim_age_is_legacy_inference_and_blocks_search():
    state, settings = _couple(age_self=68, ss_claim_age_self=67)
    assert legacy_inference_people(state, settings) == ["self"]
    with pytest.raises(ClaimInputError, match="confirm whether self"):
        enumerate_scenarios(state, settings, ENGINES, SEARCH_BOTH)
    confirmed = dataclasses.replace(settings, ss_receiving_self=True)
    assert legacy_inference_people(state, confirmed) == []
    enumerate_scenarios(state, confirmed, ENGINES, SEARCH_BOTH)


# ---------------------------------------------------------------------------
# Scenario inputs
# ---------------------------------------------------------------------------


def test_with_claim_ages_changes_only_year0_social_security():
    """Self is 66; claiming at 66 pays this year, at 70 it does not. Nothing
    else may move — MAGI history in particular was earned under the stored
    ages and a future claim cannot change it."""
    state, settings = _couple(age_self=66, ss_claim_age_self=70)
    now, s_now = with_claim_ages(state, settings, ENGINES, 66, None)
    later, _ = with_claim_ages(state, settings, ENGINES, 70, None)
    assert now.social_security > 0 and later.social_security == 0
    assert s_now.ss_claim_age_self == 66 and s_now.ss_claim_age_spouse == 67
    for field in dataclasses.fields(State):
        if field.name != "social_security":
            assert getattr(now, field.name) == getattr(state, field.name), field.name


def test_every_scenario_shares_balances_and_magi_history():
    state, settings = _couple(age_self=63, age_spouse=62)
    scenarios, _ = enumerate_scenarios(state, settings, ENGINES, SEARCH_BOTH)
    assert len(scenarios) == 8 * 9
    for sc in scenarios:
        assert sc.state.magi_two_years_ago == state.magi_two_years_ago
        assert sc.state.magi_last_year == state.magi_last_year
        assert sc.state.balance_traditional == state.balance_traditional
    keys = {sc.key for sc in scenarios}
    assert len(keys) == len(scenarios) and "67-67" in keys


def test_an_excluded_entered_age_is_a_diagnostic_scenario():
    state, settings = _couple(
        ss_claim_age_self=62,
        income_schedule=[IncomeEntry("salary", D("60000"), 2026, 2028, "self")],
    )
    scenarios, exclusions = enumerate_scenarios(state, settings, ENGINES, SEARCH_BOTH)
    entered = [s for s in scenarios if s.claim_age_self == 62 and s.claim_age_spouse == 67]
    assert len(entered) == 1 and not entered[0].eligible
    assert all(s.eligible for s in scenarios if s is not entered[0])
    assert any(e.person == "self" and e.age == 62 for e in exclusions)


def test_fixed_controls_give_one_scenario_and_a_single_filer_has_no_spouse_dimension():
    state, settings = _couple()
    scenarios, _ = enumerate_scenarios(state, settings, ENGINES, ClaimControls())
    assert [s.key for s in scenarios] == ["67-67"]

    single = dataclasses.replace(state, age_spouse=None, filing_status="single")
    solo = dataclasses.replace(settings, ss_pia_spouse=None, ss_claim_age_spouse=None)
    scenarios, _ = enumerate_scenarios(
        single, solo, ENGINES, ClaimControls(AgeControl("search"))
    )
    assert [s.key for s in scenarios] == [f"{a}--" for a in range(62, 71)]


def test_pinned_ages_must_be_eligible():
    state, settings = _couple(
        income_schedule=[IncomeEntry("salary", D("60000"), 2026, 2028, "self")]
    )
    check_pinned_ages(state, settings, 65, 62)
    with pytest.raises(ClaimInputError, match="salary paid 2028, before full retirement age"):
        check_pinned_ages(state, settings, 62, None)


# ---------------------------------------------------------------------------
# A searched age with no comparison age
# ---------------------------------------------------------------------------


def test_a_searched_age_without_an_entered_age_has_no_entered_scenario():
    state, settings = _couple(ss_claim_age_self=None, ss_claim_age_spouse=None)
    scenarios, _ = enumerate_scenarios(state, settings, ENGINES, SEARCH_BOTH)
    assert len(scenarios) == 9 * 9
    assert not any(s.entered for s in scenarios)
    # One person entered and the other not: still no "your ages" pair.
    state, settings = _couple(ss_claim_age_spouse=None)
    scenarios, _ = enumerate_scenarios(state, settings, ENGINES, SEARCH_BOTH)
    assert not any(s.entered for s in scenarios)


def test_a_fixed_age_must_exist():
    state, settings = _couple(ss_claim_age_spouse=None)
    with pytest.raises(ClaimInputError, match="choose a Social Security claim age for spouse"):
        enumerate_scenarios(state, settings, ENGINES,
                            ClaimControls(AgeControl("search"), AgeControl("fixed")))
    with pytest.raises(ClaimInputError, match="for your spouse, or let the optimizer"):
        require_claim_ages(state, settings)
    require_claim_ages(*_couple())
    # No benefit entered: no age is needed.
    require_claim_ages(*_couple(ss_pia_spouse=None, ss_claim_age_spouse=None))


def test_receiving_needs_the_age_benefits_started():
    assert "enter the age their benefits started" in receiving_error("self", 68, None, True)
    assert receiving_error("self", 60, None, False) is None
