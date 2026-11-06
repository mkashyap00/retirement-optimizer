"""A saved household, assembled into optimizer inputs, simulated.

Engine tests build State/Settings by hand, so they never notice when assembly
drops a field on the way from the database. These go the whole way:
payload -> DuckDB -> build_optimizer_inputs -> simulate_year.
"""
import dataclasses
from datetime import date
from decimal import Decimal as D

import pytest
from src.api.assemble import build_optimizer_inputs
from src.api.endpoints.households import create_household
from src.api.endpoints.optimization import _ENGINES
from src.api.models import CapitalGainsIn, HouseholdPayload, IncomeIn
from src.data.database import Database
from src.optimization.transition import simulate_year

_TODAY = date(2026, 10, 15)


def _payload():
    return HouseholdPayload(**{
        "household": {
            "filing_status": "joint",
            "self_birth_date": "1956-03-01",
            "spouse_birth_date": "1956-05-01",
            "state": "TX",
        },
        "accounts": [
            {"account_type": "taxable", "owner": "self",
             "balance": "800000", "basis": "800000"},
        ],
        "income": [
            {"category": "pension", "owner": "spouse", "amount": "30000"},
            {"category": "pension", "owner": "self", "amount": "20000"},
            {"category": "rental", "owner": "joint", "amount": "12000"},
        ],
        "settings": {"required_spending": "60000", "ss_pia_self": "0"},
    })


@pytest.fixture
def saved():
    db = Database(":memory:")
    db.connect()
    hid = create_household(_payload(), db)["household_id"]
    yield db, hid
    db.close()


def test_income_owner_survives_assembly(saved):
    db, hid = saved
    _, settings, _ = build_optimizer_inputs(db, hid, _TODAY)
    got = {(e.category, e.owner, e.amount) for e in settings.income_schedule}
    assert got == {
        ("pension", "spouse", D("30000")),
        ("pension", "self", D("20000")),
        ("rental", "joint", D("12000")),
    }


@pytest.mark.parametrize("spouse_dies, surviving_pension", [(True, D("20000")),
                                                            (False, D("30000"))])
def test_the_deceased_pension_stops_and_the_others_continue(
    saved, spouse_dies, surviving_pension
):
    db, hid = saved
    state, settings, constraints = build_optimizer_inputs(db, hid, _TODAY)
    settings = dataclasses.replace(
        settings, first_death_year=2026, first_death_is_spouse=spouse_dies
    )
    assert state.pension == D("50000")  # 2026: both alive
    nxt, _ = simulate_year(state, D("0"), _ENGINES, settings, constraints)
    assert nxt.pension == surviving_pension
    assert nxt.rental == D("12000")  # joint income outlives either spouse


def test_a_legacy_row_without_an_owner_is_treated_as_joint(saved):
    """Rows saved before owners existed keep paying after a death — the
    behaviour they always had — rather than vanishing."""
    db, hid = saved
    db.execute(
        "INSERT INTO income_sources (id, household_id, category, owner, amount) "
        "VALUES (gen_random_uuid(), ?, 'pension', NULL, 5000)",
        [hid],
    )
    _, settings, _ = build_optimizer_inputs(db, hid, _TODAY)
    assert ("pension", "joint", D("5000")) in {
        (e.category, e.owner, e.amount) for e in settings.income_schedule
    }


def _ira_payload(self_birth, spouse_birth, accounts):
    return HouseholdPayload(**{
        "household": {
            "filing_status": "joint",
            "self_birth_date": self_birth,
            "spouse_birth_date": spouse_birth,
            "state": "TX",
        },
        "accounts": accounts,
        "income": [],
        "settings": {"required_spending": "60000", "ss_pia_self": "0"},
    })


def _assemble(payload):
    db = Database(":memory:")
    db.connect()
    try:
        hid = create_household(payload, db)["household_id"]
        return build_optimizer_inputs(db, hid, _TODAY)
    finally:
        db.close()


def test_traditional_balances_keep_their_owner():
    state, _, _ = _assemble(_ira_payload("1956-03-01", "1956-05-01", [
        {"account_type": "traditional", "owner": "self", "balance": "600000"},
        {"account_type": "traditional", "owner": "spouse", "balance": "400000"},
        # An IRA cannot be joint; a legacy row saying so stays self's.
        {"account_type": "traditional", "owner": "joint", "balance": "50000"},
    ]))
    assert state.balance_traditional == D("1050000")
    assert state.balance_traditional_spouse == D("400000")


def test_ages_are_those_attained_in_the_tax_year():
    # Birthdays in December: on 15 October 2026 both are still 69 and 72, but
    # the tax year is the one they turn 70 and 73 — the age RMDs, Medicare and
    # the age-65 deduction are all keyed to.
    state, _, _ = _assemble(_ira_payload("1956-12-01", "1953-12-20", [
        {"account_type": "taxable", "owner": "self", "balance": "100000",
         "basis": "100000"},
    ]))
    assert (state.age_self, state.age_spouse) == (70, 73)


_INCOME_FIELDS = ("salary", "pension", "rental", "interest",
                  "dividends_qualified", "dividends_ordinary")


def test_every_income_category_arrives_in_the_first_year():
    # Constant streams: the first year must carry exactly what the second
    # does. Interest used to be dropped from the first year only.
    payload = _ira_payload("1956-03-01", "1956-05-01", [
        {"account_type": "taxable", "owner": "self", "balance": "800000",
         "basis": "800000"},
    ])
    payload.income = [
        IncomeIn(category=cat, owner="joint", amount=D(amt))
        for cat, amt in (("salary", "1000"), ("pension", "2000"), ("rental", "3000"),
                         ("interest", "10000"), ("qualified_dividend", "5000"),
                         ("nonqualified_dividend", "6000"))
    ]
    state, settings, constraints = _assemble(payload)
    nxt, _ = simulate_year(state, D("0"), _ENGINES, settings, constraints)
    first = {f: getattr(state, f) for f in _INCOME_FIELDS}
    assert first == {f: getattr(nxt, f) for f in _INCOME_FIELDS}
    assert state.interest == D("10000")


def _ss_couple_payload(ss_cola=None):
    settings = {"required_spending": "60000", "ss_pia_self": "4000",
                "ss_claim_age_self": 67, "ss_pia_spouse": "1200",
                "ss_claim_age_spouse": 67}
    if ss_cola is not None:
        settings["ss_cola"] = ss_cola
    return HouseholdPayload(**{
        "household": {"filing_status": "joint", "self_birth_date": "1956-03-01",
                      "spouse_birth_date": "1956-05-01", "state": "TX"},
        "accounts": [{"account_type": "taxable", "owner": "self",
                      "balance": "800000", "basis": "800000"}],
        "income": [],
        "settings": settings,
    })


def test_year0_social_security_comes_from_the_shared_helper():
    """Assembly and the simulator compute this year's benefit with the same
    function, so the year-0 state includes the spousal top-up the simulator
    pays every later year (it used to be dropped in year 0 only)."""
    from src.optimization.transition import household_social_security
    db = Database(":memory:")
    db.connect()
    hid = create_household(_ss_couple_payload(), db)["household_id"]
    state, settings, _ = build_optimizer_inputs(db, hid, _TODAY)
    assert state.social_security == household_social_security(
        _ENGINES.ss, settings, state.age_self, state.age_spouse, _TODAY.year)
    assert state.social_security > (D("4000") + D("1200")) * 12, "top-up included"
    db.close()


@pytest.mark.parametrize("stored, expected", [(None, None), ("0", D("0")),
                                              ("0.025", D("0.025"))])
def test_ss_cola_survives_assembly(stored, expected):
    db = Database(":memory:")
    db.connect()
    hid = create_household(_ss_couple_payload(stored), db)["household_id"]
    _, settings, _ = build_optimizer_inputs(db, hid, _TODAY)
    assert settings.ss_cola == expected
    db.close()


def _with_gains(tax_year):
    return _payload().model_copy(update={"capital_gains": CapitalGainsIn(
        tax_year=tax_year, short_term="-4000", long_term="25000",
        carryover_short_term="1500", carryover_long_term="0",
    )})


def test_gains_already_realized_reach_the_first_year():
    db = Database(":memory:")
    db.connect()
    hid = create_household(_with_gains(2026), db)["household_id"]
    state, settings, constraints = build_optimizer_inputs(db, hid, _TODAY)
    assert (state.realized_st_gain, state.realized_lt_gain) == (D("-4000"), D("25000"))
    assert (state.loss_carryover_st, state.loss_carryover_lt) == (D("1500"), D("0"))
    assert settings.stale_capital_gains_year is None
    # Netted: ST -5,500 against LT +25,000 leaves 19,500 long-term.
    _, ledger = simulate_year(state, D("0"), _ENGINES, settings, constraints)
    assert ledger.audit["realized_ltcg"] == D("19500")
    db.close()


def test_gains_entered_for_an_earlier_year_are_not_applied():
    db = Database(":memory:")
    db.connect()
    hid = create_household(_with_gains(2025), db)["household_id"]
    state, settings, _ = build_optimizer_inputs(db, hid, _TODAY)
    assert (state.realized_st_gain, state.realized_lt_gain) == (D("0"), D("0"))
    assert state.loss_carryover_st == D("0")
    assert settings.stale_capital_gains_year == 2025
    db.close()


@pytest.mark.parametrize("rule, expected", [("fixed", None), ("guardrails", D("40000"))])
def test_a_stored_floor_applies_only_when_spending_can_be_cut(rule, expected):
    payload = _payload()
    payload = payload.model_copy(update={"settings": payload.settings.model_copy(
        update={"spending_rule": rule, "spending_floor": D("40000")})})
    _, settings, _ = _assemble(payload)
    assert settings.spending_floor == expected
