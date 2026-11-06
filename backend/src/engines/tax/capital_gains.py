"""Capital gain netting, the capital loss deduction and its carryover.

Schedule D nets short-term and long-term results separately (each including
any loss carried in from the prior year), then offsets one against the other
when their signs differ. A net gain keeps its character: short-term is taxed
as ordinary income, long-term on the capital-gains schedule. A net loss is
deducted against ordinary income up to $3,000 a year, and the rest carries
forward, short-term absorbed first (the Capital Loss Carryover Worksheet in
the Schedule D instructions).

A state either keeps the federal result, nets the same gains again with its
own carryover figured on state income, or allows no loss against other income
at all (``state_loss_rule``).

Not modelled: married filing separately ($1,500 limit; the app has no such
status), a deceased spouse's share of a carryover, which the survivor
cannot use after the final joint return (the carryover is treated as the
household's), and state income classes beyond the loss rule (e.g.
Massachusetts' separate short-term rate, Wisconsin's long-term exclusion).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.data.tax_rules.state import STATE_CAPITAL_LOSS_RULES

_ZERO = Decimal("0")
LOSS_DEDUCTION_LIMIT = Decimal("3000")


@dataclass(frozen=True)
class NetGains:
    """One year's capital results after netting."""

    short_term: Decimal  # net short-term gain taxed as ordinary income, >= 0
    long_term: Decimal  # net long-term gain taxed at capital-gains rates, >= 0
    loss_deduction: Decimal  # capital loss deducted from ordinary income, >= 0
    st_loss: Decimal  # net short-term loss before the deduction, >= 0
    lt_loss: Decimal  # net long-term loss before the deduction, >= 0
    st_gain: Decimal  # net short-term gain before cross-netting, >= 0
    lt_gain: Decimal  # net long-term gain before cross-netting, >= 0


def state_loss_rule(state_code: str) -> str:
    """"federal", "separate" or "none" for *state_code* (STATE_CAPITAL_LOSS_RULES)."""
    return STATE_CAPITAL_LOSS_RULES.get(state_code.upper(), "federal")


def net_capital_gains(
    short_term: Decimal, long_term: Decimal, limit: Decimal = LOSS_DEDUCTION_LIMIT
) -> NetGains:
    """Net one year's short-term and long-term results (Schedule D lines 7,
    15 and 16-21). Each argument already includes the loss carried in, as a
    negative amount. *limit* caps the loss deducted from other income."""
    st_gain, st_loss = max(_ZERO, short_term), max(_ZERO, -short_term)
    lt_gain, lt_loss = max(_ZERO, long_term), max(_ZERO, -long_term)
    total = short_term + long_term
    if total >= _ZERO:
        if short_term >= _ZERO and long_term >= _ZERO:
            taxed_st, taxed_lt = short_term, long_term
        elif short_term < _ZERO:
            taxed_st, taxed_lt = _ZERO, total
        else:
            taxed_st, taxed_lt = total, _ZERO
        return NetGains(taxed_st, taxed_lt, _ZERO, st_loss, lt_loss, st_gain, lt_gain)
    deduction = min(limit, -total)
    return NetGains(_ZERO, _ZERO, deduction, st_loss, lt_loss, st_gain, lt_gain)


def loss_carryover(
    net: NetGains, agi: Decimal, total_deduction: Decimal
) -> tuple[Decimal, Decimal]:
    """(short-term, long-term) loss carried into next year, both >= 0.

    The Capital Loss Carryover Worksheet counts only the part of the $3,000
    deduction that had taxable income to offset: with *agi* already reduced by
    the deduction, that is min(deduction, max(0, agi + deduction - the
    standard or itemized deduction))."""
    if net.st_loss + net.lt_loss <= net.st_gain + net.lt_gain:
        return _ZERO, _ZERO  # a net gain, or nothing: no carryover
    used = min(net.loss_deduction, max(_ZERO, agi + net.loss_deduction - total_deduction))
    st_carry = max(_ZERO, net.st_loss - (used + net.lt_gain))
    lt_carry = max(_ZERO, net.lt_loss - (net.st_gain + max(_ZERO, used - net.st_loss)))
    return st_carry, lt_carry
