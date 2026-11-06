"""Capital gains already realized this year, and capital loss carryovers.

Netting follows Schedule D and its Capital Loss Carryover Worksheet. The
simulated year must tax the entered figures without treating them as cash,
and conversion sizing must see them.
"""

from decimal import Decimal as D

import pytest
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.capital_gains import loss_carryover, net_capital_gains
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.actions import generate_conversions
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State
from src.optimization.transition import simulate_year

_ENGINES = Engines(
    FederalTaxEngine(TaxRules()),
    StateTaxEngine(TaxRules()),
    IRMAACalculator(TaxRules()),
    RMDCalculator(TaxRules()),
    SocialSecurityCalculator(),
    TaxRules(),
)


# ── Netting ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "st, lt, taxed_st, taxed_lt, deduction",
    [
        (D("5000"), D("8000"), D("5000"), D("8000"), D("0")),  # both gains keep character
        (D("-3000"), D("8000"), D("0"), D("5000"), D("0")),  # ST loss offsets LT gain
        (D("5000"), D("-8000"), D("0"), D("0"), D("3000")),  # net loss, capped at $3,000
        (D("9000"), D("-2000"), D("7000"), D("0"), D("0")),  # LT loss offsets ST gain
        (D("-1000"), D("-500"), D("0"), D("0"), D("1500")),  # loss under the cap
    ],
)
def test_netting(st, lt, taxed_st, taxed_lt, deduction):
    net = net_capital_gains(st, lt)
    assert (net.short_term, net.long_term, net.loss_deduction) == (taxed_st, taxed_lt, deduction)


@pytest.mark.parametrize(
    "st, lt, carry_st, carry_lt",
    [
        (D("-10000"), D("4000"), D("3000"), D("0")),  # ST loss left after LT gain and $3,000
        (D("2000"), D("-10000"), D("0"), D("5000")),  # LT loss left after ST gain and $3,000
        (D("-2000"), D("-5000"), D("0"), D("4000")),  # the deduction uses ST loss first
        (D("5000"), D("1000"), D("0"), D("0")),  # a net gain carries nothing
    ],
)
def test_carryover_keeps_its_character(st, lt, carry_st, carry_lt):
    # Plenty of taxable income: the whole deduction is used.
    net = net_capital_gains(st, lt)
    assert loss_carryover(net, agi=D("200000"), total_deduction=D("30000")) == (carry_st, carry_lt)


def test_a_deduction_with_no_income_to_offset_is_carried_forward_whole():
    """Worksheet lines 1-4: the deduction counts as used only up to the
    taxable income it offset. With none, the whole loss carries forward."""
    net = net_capital_gains(D("-10000"), D("0"))
    agi = D("-3000")  # nothing but the $3,000 deduction
    assert loss_carryover(net, agi=agi, total_deduction=D("30000")) == (D("10000"), D("0"))


# ── The simulated year ───────────────────────────────────────────────────────


def _state(**kw):
    """MFJ 60/58 in TX, salary $100k, spending from a taxable account at full
    basis (its sales realize nothing), so only the entered gains are gains."""
    base = dict(
        year=2026, age_self=60, age_spouse=58,
        balance_taxable=D("400000"), basis_taxable=D("400000"),
        balance_traditional=D("500000"), balance_roth=D("0"),
        filing_status="joint", state_code="TX", salary=D("100000"),
    )
    base.update(kw)
    return State(**base)


_SETTINGS = Settings(start_year=2026, required_spending=D("90000"))


def _year(**kw):
    return simulate_year(_state(**kw), D("0"), _ENGINES, _SETTINGS, Constraints())


def test_short_term_gain_is_ordinary_income():
    _, base = _year()
    _, with_st = _year(realized_st_gain=D("20000"))
    assert with_st.audit["short_term_gain"] == D("20000")
    assert (
        with_st.audit["taxable_ordinary_income"] - base.audit["taxable_ordinary_income"]
        == D("20000")
    )
    assert with_st.federal_tax > base.federal_tax


def test_long_term_gain_stacks_above_ordinary_income():
    _, base = _year()
    _, with_lt = _year(realized_lt_gain=D("20000"))
    assert with_lt.audit["realized_ltcg"] == D("20000")
    assert with_lt.audit["taxable_ordinary_income"] == base.audit["taxable_ordinary_income"]
    assert with_lt.agi - base.agi == D("20000")


def test_entered_gains_are_not_cash():
    """The proceeds are already in the balances: the year withdraws more only
    by the extra tax, and spending is funded exactly as before."""
    # No salary: spending comes from the account, so extra tax is extra sales.
    _, base = _year(salary=D("0"))
    _, with_gain = _year(salary=D("0"), realized_st_gain=D("60000"), realized_lt_gain=D("80000"))
    extra_tax = with_gain.total_tax - base.total_tax
    extra_withdrawn = with_gain.withdrawal_taxable - base.withdrawal_taxable
    assert extra_tax > 0
    assert abs(extra_withdrawn - extra_tax) <= D("0.02")
    assert with_gain.net_spendable == base.net_spendable


def test_entered_gains_apply_to_one_year_only():
    nxt, _ = _year(realized_st_gain=D("20000"), realized_lt_gain=D("5000"))
    assert (nxt.realized_st_gain, nxt.realized_lt_gain) == (D("0"), D("0"))


def test_a_net_loss_is_deducted_and_the_rest_carried_forward():
    # No growth, so the account stays at full basis and later sales realize
    # nothing that would absorb the carryover.
    flat = Settings(start_year=2026, required_spending=D("90000"),
                    nominal_return=D("0"), dividend_yield=D("0"),
                    income_schedule=[IncomeEntry("salary", D("100000"), None, None)])
    nxt, first = simulate_year(
        _state(realized_st_gain=D("-10000")), D("0"), _ENGINES, flat, Constraints()
    )
    assert first.audit["capital_loss_deduction"] == D("-3000")
    assert (nxt.loss_carryover_st, nxt.loss_carryover_lt) == (D("7000"), D("0"))

    later, second = simulate_year(nxt, D("0"), _ENGINES, flat, Constraints())
    assert second.audit["capital_loss_deduction"] == D("-3000")
    assert later.loss_carryover_st == D("4000")


def test_a_carried_loss_absorbs_the_plans_own_gains():
    """A carryover offsets the gains the plan's sales realize."""
    kw = dict(basis_taxable=D("100000"), salary=D("0"))  # sales are 75% gain
    _, base = _year(**kw)
    nxt, offset = _year(loss_carryover_lt=D("10000"), **kw)
    assert base.audit["realized_ltcg"] > D("10000")
    assert offset.audit["realized_ltcg"] == base.audit["realized_ltcg"] - D("10000")
    assert offset.audit["lt_gain_from_planned_sales"] == base.audit["lt_gain_from_planned_sales"]
    assert nxt.loss_carryover_lt == D("0")


# ── Conversion sizing ────────────────────────────────────────────────────────


def _fill_12(**kw):
    return dict(generate_conversions(_state(**kw), _ENGINES, _SETTINGS, Constraints()))["fill_12"]


def test_short_term_gain_uses_up_bracket_room():
    assert _fill_12() - _fill_12(realized_st_gain=D("20000")) == D("20000")


def test_long_term_gain_leaves_bracket_room_alone():
    assert _fill_12(realized_lt_gain=D("20000")) == _fill_12()


def test_a_capital_loss_deduction_adds_bracket_room():
    assert _fill_12(realized_st_gain=D("-10000")) - _fill_12() == D("3000")


# ── State loss treatment ─────────────────────────────────────────────────────


def _flat(state_code, salary="20000"):
    """No growth and full basis: no later sale realizes a gain, so only the
    entered loss is in play. Salary in the schedule so every year has it."""
    settings = Settings(
        start_year=2026, required_spending=D("15000"), nominal_return=D("0"),
        dividend_yield=D("0"),
        income_schedule=[IncomeEntry("salary", D(salary), None, None)],
    )
    return settings, dict(state_code=state_code, salary=D(salary))


def test_california_figures_its_own_carryover():
    """$20,000 of salary: below the federal standard deduction, so the federal
    deduction offsets nothing and the federal carryover stays $10,000. On
    California income it is used, so California deducts the $10,000 once over
    four years, never $3,000 a year forever."""
    settings, kw = _flat("CA")
    state = _state(realized_st_gain=D("-10000"), state_loss_carryover_st=D("0"), **kw)
    state_deducted = D("0")
    for _ in range(6):
        state, ledger = simulate_year(state, D("0"), _ENGINES, settings, Constraints())
        state_deducted -= ledger.audit["state_capital_loss_deduction"]
    assert state.loss_carryover_st == D("10000")  # federal: never used
    assert state.state_loss_carryover_st == D("0")
    assert state_deducted == D("10000")


@pytest.mark.parametrize("code", ["PA", "NJ"])
def test_pennsylvania_and_new_jersey_allow_no_loss_against_salary(code):
    settings, kw = _flat(code, salary="100000")
    _, base = simulate_year(_state(**kw), D("0"), _ENGINES, settings, Constraints())
    nxt, loss = simulate_year(
        _state(realized_st_gain=D("-10000"), **kw), D("0"), _ENGINES, settings, Constraints())
    assert loss.audit["state_capital_loss_deduction"] == D("0")
    assert loss.state_tax == base.state_tax
    assert nxt.state_loss_carryover_st == D("0")
    assert loss.federal_tax < base.federal_tax  # the federal deduction still applies


def test_pennsylvania_nets_a_loss_against_same_year_gains():
    settings, kw = _flat("PA", salary="100000")
    _, netted = simulate_year(
        _state(realized_st_gain=D("-10000"), realized_lt_gain=D("25000"), **kw),
        D("0"), _ENGINES, settings, Constraints())
    _, plain = simulate_year(
        _state(realized_lt_gain=D("15000"), **kw), D("0"), _ENGINES, settings, Constraints())
    assert netted.state_tax == plain.state_tax


def test_new_york_keeps_the_federal_result():
    """New York starts from the federal return, so it deducts what the federal
    return deducts: with the same $20,000 salary as the California case, $3,000
    every year while the federal carryover lasts, never exhausting a balance of
    its own."""
    settings, kw = _flat("NY")
    state = _state(realized_st_gain=D("-10000"), state_loss_carryover_st=D("0"), **kw)
    for _ in range(6):
        state, ledger = simulate_year(state, D("0"), _ENGINES, settings, Constraints())
        assert ledger.audit["state_capital_loss_deduction"] == D("-3000")
        assert ledger.audit["capital_loss_deduction"] == D("-3000")
    assert state.loss_carryover_st == D("10000")
    assert state.state_loss_carryover_st == state.loss_carryover_st


def test_wisconsin_allows_3000_with_its_own_carryover():
    """$3,000 from tax year 2023 (it was $500), with Wisconsin's own carryover."""
    settings, kw = _flat("WI", salary="100000")
    nxt, ledger = simulate_year(
        _state(realized_st_gain=D("-10000"), **kw), D("0"), _ENGINES, settings, Constraints())
    assert ledger.audit["state_capital_loss_deduction"] == D("-3000")
    assert nxt.state_loss_carryover_st == D("7000")
    assert ledger.audit["capital_loss_deduction"] == D("-3000")
