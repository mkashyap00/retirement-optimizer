from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest
from src.data.tax_rules.types import (
    Bracket,
    FederalTaxYear,
    NiitRule,
    SaltRule,
    SeniorBonus,
)


def test_bracket_is_frozen():
    b = Bracket(upper=Decimal("11925"), rate=Decimal("0.10"))
    with pytest.raises(FrozenInstanceError):
        b.rate = Decimal("0.99")


def test_federal_tax_year_holds_all_domains():
    senior_bonus = SeniorBonus(
        amount_per_person=Decimal("6000"),
        phaseout_start={"single": Decimal("75000"), "joint": Decimal("150000")},
        phaseout_rate=Decimal("0.06"),
        first_year=2025,
        last_year=2028,
    )
    salt_rule = SaltRule(
        cap={"single": Decimal("40000"), "joint": Decimal("40000")},
        phase_down_start=Decimal("500000"),
        phase_down_rate=Decimal("0.30"),
        floor=Decimal("10000"),
    )
    niit_rule = NiitRule(
        rate=Decimal("0.038"),
        threshold={"single": Decimal("200000"), "joint": Decimal("250000")},
    )
    fy = FederalTaxYear(
        year=2099,
        source="test",
        brackets={"single": [Bracket(None, Decimal("0.10"))]},
        ltcg_brackets={"single": [Bracket(None, Decimal("0"))]},
        standard_deduction={"single": Decimal("10000")},
        aged_addition={"single": Decimal("2000")},
        senior_bonus=senior_bonus,
        salt=salt_rule,
        niit=niit_rule,
    )
    assert fy.brackets["single"][0].rate == Decimal("0.10")
