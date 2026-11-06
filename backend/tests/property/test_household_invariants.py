"""Invariants that must hold for ANY household, checked on random ones.

Every bracket-fill bug fixed so far (2026-09-21, 2026-10-03) slipped through
because the tests asserted a formula on a few hand-built households, and the
broken case -- a combination of income sources nobody had written a fixture
for -- was simply never generated. These tests state what the tool promises
and let Hypothesis search the space of households for a counterexample:

  * a "fill NN%" conversion lands taxable ordinary income at or below that
    bracket's top, on the year as actually simulated;
  * no conversion the bracket cap lets through puts the year's last dollar of
    ordinary income above the cap;
  * every year funds its spending unless the accounts are exhausted;
  * RMDs start exactly at the SECURE 2.0 age for the owner's birth year;
  * the "Before RMDs" window closes at that same age;
  * a conversion never exceeds the traditional balance.

Examples are derandomized so a failure reproduces on every run and in CI.
"""
from __future__ import annotations

from decimal import Decimal as D

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from src.data.tax_rules.rmd import applicable_rmd_age
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.actions import _last_dollar_rate, generate_conversions
from src.optimization.search import rule_of, search
from src.optimization.state import Constraints, Engines, Settings, State
from src.optimization.transition import simulate_year

YEAR = 2026
_RULES = TaxRules()
_ENGINES = Engines(
    federal=FederalTaxEngine(_RULES),
    state=StateTaxEngine(_RULES),
    irmaa=IRMAACalculator(_RULES),
    rmd=RMDCalculator(_RULES),
    ss=SocialSecurityCalculator(),
    rules=_RULES,
)
_FILL_RATE = {
    "fill_10": D("0.10"),
    "fill_12": D("0.12"),
    "fill_22": D("0.22"),
    "fill_24": D("0.24"),
    "fill_32": D("0.32"),
}
_ONE_DOLLAR = D("1")

# Per-year checks are cheap (a handful of single-year simulations each), so
# they get a wide search. Whole-plan checks run the full policy search.
_YEAR_SETTINGS = settings(
    max_examples=300,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
_PLAN_SETTINGS = settings(
    max_examples=40,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)


def _money(lo: int, hi: int):
    return st.integers(lo, hi).map(lambda v: D(v))


@st.composite
def households(draw):
    """(state, settings, constraints) for one plausible household."""
    joint = draw(st.booleans())
    age_self = draw(st.integers(55, 80))
    age_spouse = draw(st.integers(max(50, age_self - 6), age_self + 6)) if joint else None
    retired = age_self >= 67 or draw(st.booleans())
    taxable = draw(_money(0, 1_500_000))
    basis_frac = D(draw(st.integers(0, 100))) / 100
    claimed_ss = age_self >= 62 and draw(st.booleans())

    state = State(
        year=YEAR,
        age_self=age_self,
        age_spouse=age_spouse,
        balance_taxable=taxable,
        basis_taxable=(taxable * basis_frac).quantize(D("1")),
        balance_traditional=draw(_money(50_000, 4_000_000)),
        balance_roth=draw(_money(0, 500_000)),
        filing_status="joint" if joint else "single",
        state_code=draw(st.sampled_from(["CA", "TX", "NY", "CO", "FL"])),
        salary=D(0) if retired else draw(_money(20_000, 220_000)),
        pension=draw(st.one_of(st.just(D(0)), _money(5_000, 60_000))),
        social_security=draw(_money(12_000, 95_000)) if claimed_ss else D(0),
        interest=draw(_money(0, 10_000)),
        dividends_qualified=draw(_money(0, 30_000)),
        dividends_ordinary=draw(_money(0, 15_000)),
        medicare_self=age_self >= 65,
        medicare_spouse=age_spouse is not None and age_spouse >= 65,
    )
    plan = Settings(
        start_year=YEAR,
        required_spending=draw(_money(30_000, 250_000)),
        birth_year_self=YEAR - age_self,
        birth_year_spouse=None if age_spouse is None else YEAR - age_spouse,
        simulation_years=draw(st.integers(10, 30)),
    )
    constraints = Constraints(
        marginal_rate_limit=draw(
            st.one_of(st.none(), st.sampled_from([D("0.10"), D("0.12"), D("0.22"), D("0.24")]))
        ),
        preserve_taxable=draw(st.booleans()),
    )
    return state, plan, constraints


def _brackets(year: int, filing: str, inflation: D):
    """The table the simulator taxes *year* with — projected past the last
    published year at the plan's inflation, exactly as the engine does."""
    return _RULES.federal(year, inflation).brackets[filing]


def _top(year: int, filing: str, rate: D, inflation: D) -> D:
    return next(b.upper for b in _brackets(year, filing, inflation) if b.rate == rate)


def _landed(ledger) -> D:
    return ledger.audit["taxable_ordinary_income"]


def _describe(state, plan, constraints) -> str:
    return (
        f"{state.filing_status} age {state.age_self}/{state.age_spouse}, "
        f"taxable {state.balance_taxable} (basis {state.basis_taxable}), "
        f"IRA {state.balance_traditional}, salary {state.salary}, pension {state.pension}, "
        f"SS {state.social_security}, spend {plan.required_spending}, "
        f"{state.state_code}, cap {constraints.marginal_rate_limit}, "
        f"preserve_taxable {constraints.preserve_taxable}"
    )


# ── One year ──────────────────────────────────────────────────────────────────


@_YEAR_SETTINGS
@given(households())
def test_a_bracket_fill_never_lands_above_its_bracket(household):
    state, plan, constraints = household
    for action_id, amount in generate_conversions(state, _ENGINES, plan, constraints):
        rate = _FILL_RATE.get(action_id)
        if rate is None:
            continue
        _, ledger = simulate_year(state, amount, _ENGINES, plan, constraints)
        top = _top(state.year, state.filing_status, rate, plan.inflation)
        assert _landed(ledger) <= top, (
            f"{action_id} of {amount} landed taxable ordinary income at "
            f"{_landed(ledger)}, above the {rate:.0%} top of {top}. "
            + _describe(state, plan, constraints)
        )


@_YEAR_SETTINGS
@given(households())
def test_no_conversion_the_cap_allows_lands_above_the_cap(household):
    state, plan, constraints = household
    if constraints.marginal_rate_limit is None:
        return
    for action_id, amount in generate_conversions(state, _ENGINES, plan, constraints)[1:]:
        _, ledger = simulate_year(state, amount, _ENGINES, plan, constraints)
        rate = _last_dollar_rate(
            _brackets(state.year, state.filing_status, plan.inflation), _landed(ledger)
        )
        assert rate <= constraints.marginal_rate_limit, (
            f"{action_id} of {amount} passed a {constraints.marginal_rate_limit:.0%} cap "
            f"but its last dollar is taxed at {rate:.0%}. " + _describe(state, plan, constraints)
        )


@_YEAR_SETTINGS
@given(households())
def test_every_candidate_year_funds_its_spending_or_runs_dry(household):
    state, plan, constraints = household
    for action_id, amount in generate_conversions(state, _ENGINES, plan, constraints):
        _, ledger = simulate_year(state, amount, _ENGINES, plan, constraints)
        if ledger.shortfall == 0:
            assert ledger.net_spendable >= ledger.required_spending - _ONE_DOLLAR, (
                f"{action_id}: no shortfall reported, yet only {ledger.net_spendable} of "
                f"{ledger.required_spending} funded. " + _describe(state, plan, constraints)
            )
        else:
            drawable = ledger.end_taxable + ledger.end_traditional + ledger.end_roth
            assert drawable <= _ONE_DOLLAR, (
                f"{action_id}: {ledger.shortfall} shortfall reported with {drawable} "
                f"still in the accounts. " + _describe(state, plan, constraints)
            )


@_YEAR_SETTINGS
@given(households())
def test_conversions_never_exceed_the_traditional_balance(household):
    state, plan, constraints = household
    for action_id, amount in generate_conversions(state, _ENGINES, plan, constraints)[1:]:
        assert D(0) < amount <= state.balance_traditional, (
            f"{action_id} of {amount} against a traditional balance of "
            f"{state.balance_traditional}. " + _describe(state, plan, constraints)
        )


@_YEAR_SETTINGS
@given(households())
def test_rmds_start_at_the_secure_2_age_for_the_birth_year(household):
    state, plan, constraints = household
    _, ledger = simulate_year(state, D(0), _ENGINES, plan, constraints)
    due = state.age_self >= applicable_rmd_age(plan.birth_year_self)
    assert (ledger.rmd > 0) == due, (
        f"age {state.age_self}, born {plan.birth_year_self}: RMD {ledger.rmd}, "
        f"but RMDs {'are' if due else 'are not'} due."
    )


@_YEAR_SETTINGS
@given(households())
def test_the_before_rmds_window_closes_at_the_secure_2_age(household):
    state, plan, constraints = household
    window = Constraints(
        conversion_window="pre_rmd",
        marginal_rate_limit=constraints.marginal_rate_limit,
        preserve_taxable=constraints.preserve_taxable,
    )
    offered = generate_conversions(state, _ENGINES, plan, window)[1:]
    if state.age_self >= applicable_rmd_age(plan.birth_year_self):
        assert offered == [], (
            f"age {state.age_self}, born {plan.birth_year_self}: the Before RMDs window "
            f"still offered {offered}."
        )


# ── Whole plans ───────────────────────────────────────────────────────────────


@_PLAN_SETTINGS
@given(households())
def test_every_policy_keeps_its_promises_in_every_year(household):
    """The per-year promises, checked on every year of every policy the
    search actually builds -- where rule schedules walk into situations
    (taxable account exhausted, RMDs starting) no year-0 fixture reaches."""
    state, plan, constraints = household
    cap = constraints.marginal_rate_limit
    for policy in search(state, _ENGINES, plan, constraints):
        rule = rule_of(policy.policy_id)
        rule_rate = _FILL_RATE.get(rule)  # bracket rules only, not level_*pct
        for ledger in policy.result.ledgers:
            where = f"{policy.policy_id} {ledger.year}: " + _describe(state, plan, constraints)
            if ledger.shortfall == 0:
                assert ledger.net_spendable >= ledger.required_spending - _ONE_DOLLAR, where
            if ledger.conversion <= 0:
                continue
            landed = _landed(ledger)
            brackets = _brackets(ledger.year, state.filing_status, plan.inflation)
            if rule_rate is not None:
                top = _top(ledger.year, state.filing_status, rule_rate, plan.inflation)
                assert landed <= top, (
                    f"converted {ledger.conversion}, landed {landed} above the "
                    f"{rule_rate:.0%} top of {top}. " + where
                )
            if cap is not None:
                rate = _last_dollar_rate(brackets, landed)
                assert rate <= cap, (
                    f"converted {ledger.conversion}; last dollar taxed at {rate:.0%}, "
                    f"above the {cap:.0%} cap. " + where
                )
