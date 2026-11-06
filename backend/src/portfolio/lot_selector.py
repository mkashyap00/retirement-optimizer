"""Tax-lot selection algorithm: losses first, then the cheapest gains.

Priority order for selling:

1. Long-term **losses** (most negative unrealized gain per dollar of
   market value first — maximises loss harvesting value).
2. Short-term **losses**, the same way.
3. Long-term **gains**, smallest gain per dollar of proceeds first. For a
   fixed cash target that is what minimises the gain realized. Within one
   security it is HIFO (same price, so highest basis = smallest gain); across
   securities, basis per share means nothing — a $500 basis on a $1,000 share
   is a bigger gain per dollar than a $90 basis on a $100 share — and it
   would change with a stock split.
4. Short-term **gains**, the same way.

Lots with ``holding_period == "unknown"`` (no acquisition date) are treated
as long-term with a one-time advisory warning appended to the plan.

Only lots whose ``account_type == "taxable"`` are eligible for sale.

Partial-lot sales are allowed — the last lot consumed may be sold in part
to hit *target_cash* exactly.

If total eligible market value < *target_cash*, every eligible lot is sold
and a warning is appended.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from src.portfolio.models import SalePlan, SoldLot, TaxLot

logger = logging.getLogger(__name__)

_INSUFFICIENT_WARNING = (
    "Insufficient taxable holdings to raise the requested cash. "
    "Sold all eligible lots."
)
_UNKNOWN_HP_WARNING = (
    "One or more lots have no acquisition date. "
    "Treating as long-term for ordering purposes."
)
_SHORT_TERM_WARNING = (
    "This plan sells short-term holdings: their gains are taxed at ordinary "
    "income rates, not the long-term capital-gains rate."
)

# A quantized partial sale (6-dp shares) leaves the running remainder a hair
# off zero. Below this threshold the target is "raised" — chasing the residual
# only mints partial sales that round to 0 shares for every remaining lot.
_CASH_EPSILON = Decimal("0.01")


def _gain_per_dollar(lot: TaxLot) -> Decimal:
    """Unrealized gain divided by market value (negative = loss)."""
    mv = lot.market_value
    if mv == 0:
        return Decimal("0")
    return lot.unrealized_gain / mv


def _sort_key(lot: TaxLot, as_of: date) -> tuple:
    """Return a sort key that produces the priority ordering.

    Bucket integers:
      0 → long-term loss
      1 → short-term loss
      2 → long-term gain / break-even
      3 → short-term gain / break-even

    Within each bucket lots are sorted by gain per dollar of market value,
    lowest first: the deepest loss, then the smallest gain per dollar raised.
    """
    long_term = lot.holding_period(as_of) in ("long_term", "unknown")
    if lot.unrealized_gain < 0:
        bucket = 0 if long_term else 1
    else:
        bucket = 2 if long_term else 3
    return (bucket, _gain_per_dollar(lot))


def select_lots(
    lots: list[TaxLot],
    target_cash: Decimal,
    as_of: date,
) -> SalePlan:
    """Choose which lots to sell to raise *target_cash* with minimum tax.

    Args:
        lots: Full universe of held lots (all account types allowed; only
            ``"taxable"`` ones are eligible).
        target_cash: Cash proceeds required.
        as_of: Reference date for holding-period calculations (normally today).

    Returns:
        A :class:`~models.SalePlan` with the ordered sale actions and
        aggregate gain / warning metadata.
    """
    plan = SalePlan()

    eligible = [lot for lot in lots if lot.account_type == "taxable"]

    # Check for unknown-HP lots and emit warning once
    has_unknown = any(lot.holding_period(as_of) == "unknown" for lot in eligible)
    if has_unknown:
        plan.warnings.append(_UNKNOWN_HP_WARNING)

    # Sort eligible lots by priority
    eligible.sort(key=lambda lot: _sort_key(lot, as_of))

    cash_remaining = target_cash
    total_eligible_mv = sum(lot.market_value for lot in eligible)

    if total_eligible_mv < target_cash:
        plan.warnings.append(_INSUFFICIENT_WARNING)
        # Sell everything
        cash_remaining = total_eligible_mv + Decimal("1")  # ensure loop sells all

    for lot in eligible:
        if cash_remaining <= _CASH_EPSILON:
            break

        mv = lot.market_value
        if mv <= 0:
            continue

        if mv <= cash_remaining:
            # Sell full lot
            shares_sold = lot.shares
            proceeds = mv
        else:
            # Partial sale — pro-rata shares
            fraction = cash_remaining / mv
            shares_sold = (lot.shares * fraction).quantize(Decimal("0.000001"))
            proceeds = shares_sold * lot.current_price

        # Defensive: a partial that rounds to 0 shares raises nothing and would
        # only add a spurious $0 row. Skip it (also avoids a no-progress loop).
        if shares_sold <= 0:
            continue

        gain_per_share = lot.current_price - lot.cost_basis_per_share
        realized_gain = shares_sold * gain_per_share

        sold_lot = SoldLot(
            lot=lot,
            shares_sold=shares_sold,
            proceeds=proceeds,
            realized_gain=realized_gain,
        )
        plan.sold.append(sold_lot)
        plan.cash_raised += proceeds
        cash_remaining -= proceeds

        hp = lot.holding_period(as_of)
        if hp == "short_term":
            plan.realized_st_gain += realized_gain
        else:  # long_term or unknown → lt bucket
            plan.realized_lt_gain += realized_gain

    if any(s.lot.holding_period(as_of) == "short_term" for s in plan.sold):
        plan.warnings.append(_SHORT_TERM_WARNING)

    return plan
