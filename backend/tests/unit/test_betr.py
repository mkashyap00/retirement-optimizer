"""Unit tests for the BETR (break-even tax rate) metric.

TDD RED phase: tests written per p04-task-8-brief.md before implementation.
"""
from decimal import Decimal as D

from src.optimization.betr import compute_betr


def test_betr_equals_current_rate_when_paid_from_ira():
    assert compute_betr(D("0.22"), 15, D("0.06"), D("0.003"), paid_from_taxable=False) == D("0.22")


def test_betr_below_current_rate_when_paid_from_taxable():
    # Paper's core claim: taxable-funded conversion taxes lower the BETR,
    # and the effect grows with horizon.
    b10 = compute_betr(D("0.22"), 10, D("0.06"), D("0.003"), paid_from_taxable=True)
    b20 = compute_betr(D("0.22"), 20, D("0.06"), D("0.003"), paid_from_taxable=True)
    assert b20 < b10 < D("0.22")


def test_betr_scales_with_drag():
    # More tax-inefficient side fund (higher drag) -> lower BETR (paper Scenario 3 vs 2).
    efficient = compute_betr(D("0.35"), 20, D("0.06"), D("0.003"), True)
    inefficient = compute_betr(D("0.35"), 20, D("0.06"), D("0.02"), True)
    assert inefficient < efficient < D("0.35")


def test_betr_zero_when_no_tax_cost():
    # 100% IRA basis -> conversion is free -> BETR 0: always convert.
    assert compute_betr(D("0"), 20, D("0.06"), D("0.003"), True) == D("0")
