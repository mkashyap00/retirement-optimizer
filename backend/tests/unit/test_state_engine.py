# backend/tests/unit/test_state_engine.py
"""State tax engine tests — TDD suite for Task 5 (fixes B7, B8)."""
from decimal import Decimal as D

import pytest
from src.data.tax_rules.rules import TaxRules
from src.engines.tax.state import StateIncome, StateTaxEngine


@pytest.fixture
def engine():
    return StateTaxEngine(TaxRules())


def test_no_tax_state_returns_zero(engine):
    """TX has no state income tax — any income should yield Decimal('0')."""
    assert engine.calculate(StateIncome(ordinary=D("200000")), "TX", "joint") == D("0")


def test_most_states_exempt_ss(engine):
    """B7 regression: CA does not tax SS — adding SS should not change the tax."""
    with_ss = engine.calculate(
        StateIncome(ordinary=D("50000"), social_security=D("40000")), "CA", "joint"
    )
    without = engine.calculate(StateIncome(ordinary=D("50000")), "CA", "joint")
    assert with_ss == without


def test_ltcg_taxed_as_ordinary_at_state_level(engine):
    """LTCG is treated as ordinary income for state tax; $60k+$40k LTCG == $100k ordinary."""
    a = engine.calculate(
        StateIncome(ordinary=D("60000"), capital_gains_long=D("40000")), "CA", "joint"
    )
    b = engine.calculate(StateIncome(ordinary=D("100000")), "CA", "joint")
    assert a == b


def test_california_matches_ftb_worked_example(engine):
    """FTB 2025 schedule example: joint taxable income $125,000 -> $4,768.10.
    Taxable = gross - the $11,412 joint standard deduction."""
    tax = engine.calculate(StateIncome(ordinary=D("136412")), "CA", "joint")
    assert tax == D("4768.10")


def test_california_mental_health_tax_applies_over_one_million(engine):
    """1% on taxable income over $1,000,000 for every filing status, on top
    of the ordinary schedule (FTB single: 72,219.84 + 12.3% over 742,953)."""
    taxable = D("1100000")
    single = engine.calculate(StateIncome(ordinary=taxable + D("5706")), "CA", "single")
    ordinary = D("72219.84") + (taxable - D("742953")) * D("0.123")
    # FTB rounds each bracket's cumulative base to cents; allow that plus final rounding.
    assert abs(single - (ordinary + D("1000"))) <= D("0.02")
    below = engine.calculate(StateIncome(ordinary=D("900000") + D("11412")), "CA", "joint")
    assert abs(below - (D("77276.52") + (D("900000") - D("891542")) * D("0.113"))) <= D("0.02")
