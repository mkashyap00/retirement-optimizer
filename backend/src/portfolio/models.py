"""Portfolio tax-lot data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class TaxLot:
    """A single tax lot position in a brokerage account.

    Args:
        ticker: Security symbol (e.g. "AAPL").
        lot_date: Date the lot was acquired, or ``None`` when unavailable
            (Mode C ingest). ``None`` → holding period is ``"unknown"``.
        shares: Number of shares held.
        cost_basis_per_share: Original cost per share.
        current_price: Current market price per share.
        account_type: One of ``"taxable"``, ``"traditional"``, ``"roth"``.
        long_term: Explicit holding-period flag from the aggregate template
            (positions carry no dates). ``True``/``False`` override the
            date-based classification; ``None`` falls back to ``lot_date``.
    """

    ticker: str
    lot_date: date | None
    shares: Decimal
    cost_basis_per_share: Decimal
    current_price: Decimal
    account_type: str
    long_term: bool | None = None

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def total_cost_basis(self) -> Decimal:
        """Total cost basis = shares × cost_basis_per_share."""
        return self.shares * self.cost_basis_per_share

    @property
    def market_value(self) -> Decimal:
        """Current market value = shares × current_price."""
        return self.shares * self.current_price

    @property
    def unrealized_gain(self) -> Decimal:
        """Unrealized gain/loss = market_value − total_cost_basis."""
        return self.market_value - self.total_cost_basis

    # ------------------------------------------------------------------
    # Holding-period classification
    # ------------------------------------------------------------------

    def holding_period(self, as_of: date) -> str:
        """Return holding-period bucket for this lot.

        Returns:
            ``"long_term"`` if flagged long-term or held > 365 days from
            *as_of*, ``"short_term"`` if flagged or held ≤ 365 days,
            ``"unknown"`` when neither a flag nor a ``lot_date`` is present.
        """
        if self.long_term is not None:
            return "long_term" if self.long_term else "short_term"
        if self.lot_date is None:
            return "unknown"
        held_days = (as_of - self.lot_date).days
        return "long_term" if held_days > 365 else "short_term"


@dataclass
class SoldLot:
    """Records how many shares of a particular lot were sold and the result.

    Args:
        lot: The originating :class:`TaxLot`.
        shares_sold: Number of shares actually sold (may be < lot.shares for
            partial sales).
        proceeds: Sale proceeds (shares_sold × current_price).
        realized_gain: Gain/loss realised on this sale.
    """

    lot: TaxLot
    shares_sold: Decimal
    proceeds: Decimal
    realized_gain: Decimal


@dataclass
class SalePlan:
    """The complete plan produced by :func:`~lot_selector.select_lots`.

    Args:
        sold: Ordered list of :class:`SoldLot` entries.
        cash_raised: Total proceeds across all sales.
        realized_lt_gain: Net long-term capital gain/loss realised.
        realized_st_gain: Net short-term capital gain/loss realised.
        warnings: Advisory messages (insufficient holdings, unknown holding
            period treated as long-term, etc.).
    """

    sold: list[SoldLot] = field(default_factory=list)
    cash_raised: Decimal = Decimal("0")
    realized_lt_gain: Decimal = Decimal("0")
    realized_st_gain: Decimal = Decimal("0")
    warnings: list[str] = field(default_factory=list)
