"""Tests for IRMAA calculator engine."""
from decimal import Decimal

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator


def test_below_first_threshold_no_surcharge():
    """Joint MAGI 150k is below first tier (212k), so no surcharge."""
    calc = IRMAACalculator(TaxRules())
    assert calc.annual_surcharge(Decimal("150000"), "joint", 2025, 2) == Decimal("0")


def test_tier1_joint_2025():
    """Joint MAGI 220k → tier 1: PartB 259.00 vs standard 185.00 = 74.00 + PartD 13.70
    = 87.70/mo/person -> * 12 * 2 = 2,104.80
    """
    calc = IRMAACalculator(TaxRules())
    assert calc.annual_surcharge(Decimal("220000"), "joint", 2025, 2) == Decimal("2104.80")


def test_threshold_is_a_cliff():
    """At exactly 212,000 (the threshold), stays in tier 0 (<=).
    At 212,001, moves to tier 1, resulting in surcharge > 2000.
    """
    calc = IRMAACalculator(TaxRules())
    below = calc.annual_surcharge(Decimal("212000"), "joint", 2025, 2)
    above = calc.annual_surcharge(Decimal("212001"), "joint", 2025, 2)
    assert below == Decimal("0") and above > Decimal("2000")
