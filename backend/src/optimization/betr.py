"""BETR (break-even tax rate) metric for Roth conversion analysis.

Derived from Vanguard's July 2025 research paper:
  "A 'BETR' approach to Roth conversions"

The BETR is the future marginal tax rate at which the after-tax withdrawal
value is the same in both the no-conversion and conversion scenarios.
"""
from __future__ import annotations

from decimal import Decimal

_ONE = Decimal("1")
_QUANTIZE = Decimal("0.0001")


def compute_betr(
    conversion_tax_rate: Decimal,  # (tax_with - tax_without) / conversion; basis-adjusted
    years_to_drawdown: int,        # max(1, 73 - age_self); 1 if already at RMD age
    pretax_return: Decimal,        # settings.nominal_return
    taxable_drag: Decimal,         # settings.dividend_yield * 0.15 (same as transition.py)
    paid_from_taxable: bool,       # True when taxable account covers the conversion tax
) -> Decimal:
    """BETR = future marginal tax rate at which convert vs. no-convert are equal.

    Derivation (paper Fig. 2): per pre-tax dollar converted with tax t paid from a
    taxable side fund over n years:
      no-convert:  G*(1-t_future) + t*G_tx     (trad grows to G, side fund keeps t)
      convert:     G                            (Roth grows to G, side fund spent)
      indifference: BETR = t * G_tx / G
    where G = (1+pretax_return)^n and G_tx = (1+pretax_return-taxable_drag)^n.
    If the tax cannot be paid from taxable (paid_from_taxable=False), BETR = t
    (paper Scenario 1: conversion taxes paid from the IRA itself).
    """
    if not paid_from_taxable:
        return conversion_tax_rate.quantize(_QUANTIZE)

    n = years_to_drawdown
    g = (_ONE + pretax_return) ** n
    g_tx = (_ONE + pretax_return - taxable_drag) ** n

    betr = conversion_tax_rate * g_tx / g
    return betr.quantize(_QUANTIZE)
