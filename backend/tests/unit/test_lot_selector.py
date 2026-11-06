"""Unit tests for the lot-selection algorithm (src/portfolio/lot_selector.py)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.portfolio.lot_selector import (
    _INSUFFICIENT_WARNING,
    _UNKNOWN_HP_WARNING,
    select_lots,
)
from src.portfolio.models import TaxLot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AS_OF = date(2026, 7, 5)  # reference date for all tests


def make_lot(
    ticker: str,
    *,
    shares: float,
    cost_per_share: float,
    price: float,
    account_type: str = "taxable",
    lot_date: date | None = None,
) -> TaxLot:
    return TaxLot(
        ticker=ticker,
        lot_date=lot_date,
        shares=Decimal(str(shares)),
        cost_basis_per_share=Decimal(str(cost_per_share)),
        current_price=Decimal(str(price)),
        account_type=account_type,
    )


# Long-term dates (held > 365 days before AS_OF)
LT_DATE = date(2024, 1, 1)   # ~18 months before AS_OF
ST_DATE = date(2026, 5, 1)   # ~65 days before AS_OF (short-term)


# ---------------------------------------------------------------------------
# Core HIFO / loss-first fixture
#
# Lot A: 100 shares @ $60 cost,  $100 price → +$4000 gain, $10000 MV  (lt gain, low basis)
# Lot B: 100 shares @ $90 cost,  $100 price → +$1000 gain, $10000 MV  (lt gain, high basis)
# Lot C: 100 shares @ $110 cost, $100 price → -$1000 loss, $10000 MV  (lt loss)
#
# Expected sell order for target $15000:
#   1. All of C (loss-first)                     → $10000 raised, -$1000 gain
#   2. Partial B (HIFO: $90 basis > $60 basis)   → $5000 raised,  +$500 gain (50 shares)
#   Total realized_lt_gain = -$1000 + $500 = -$500
# ---------------------------------------------------------------------------

LOT_A = make_lot("A", shares=100, cost_per_share=60,  price=100, lot_date=LT_DATE)
LOT_B = make_lot("B", shares=100, cost_per_share=90,  price=100, lot_date=LT_DATE)
LOT_C = make_lot("C", shares=100, cost_per_share=110, price=100, lot_date=LT_DATE)


class TestNoZeroShareDust:
    """A quantized partial sale leaves sub-cent rounding dust in
    cash_remaining. If the loop keeps going, every remaining lot gets a
    partial that rounds to 0 shares — spurious $0 rows the user must ignore.
    """

    def test_no_zero_share_rows_after_target_met(self):
        # Both gains → HIFO order P (cost 20) then Q (cost 10). Target $100 is
        # a partial of P: 100/3000 → 3.333333 sh @ $30 = $99.99999, leaving
        # $0.00001 of dust. Q must NOT appear as a 0-share row.
        p = make_lot("P", shares=100, cost_per_share=20, price=30)
        q = make_lot("Q", shares=100, cost_per_share=10, price=50)

        plan = select_lots([p, q], Decimal("100"), AS_OF)

        assert all(s.shares_sold > 0 for s in plan.sold), (
            f"zero-share rows leaked: "
            f"{[(s.lot.ticker, s.shares_sold) for s in plan.sold]}"
        )
        assert {s.lot.ticker for s in plan.sold} == {"P"}
        assert abs(plan.cash_raised - Decimal("100")) < Decimal("0.01")


class TestLossFirstHIFO:
    def test_sells_loss_lot_first(self):
        plan = select_lots([LOT_A, LOT_B, LOT_C], Decimal("15000"), AS_OF)
        tickers = [s.lot.ticker for s in plan.sold]
        assert tickers[0] == "C", f"Expected C first (loss lot), got {tickers}"

    def test_then_partial_hifo_lot(self):
        plan = select_lots([LOT_A, LOT_B, LOT_C], Decimal("15000"), AS_OF)
        tickers = [s.lot.ticker for s in plan.sold]
        assert tickers[1] == "B", f"Expected B second (HIFO of remaining gains), got {tickers}"
        assert len(plan.sold) == 2, "Should not have sold lot A"

    def test_correct_cash_raised(self):
        plan = select_lots([LOT_A, LOT_B, LOT_C], Decimal("15000"), AS_OF)
        assert abs(plan.cash_raised - Decimal("15000")) < Decimal("0.01")

    def test_partial_lot_shares(self):
        plan = select_lots([LOT_A, LOT_B, LOT_C], Decimal("15000"), AS_OF)
        b_sale = next(s for s in plan.sold if s.lot.ticker == "B")
        # $5000 / $100 per share = 50 shares
        assert abs(b_sale.shares_sold - Decimal("50")) < Decimal("0.001")

    def test_realized_lt_gain_sign(self):
        """Net lt gain = C's loss (−$1000) + B's partial gain (+$500) = −$500.

        C: 100 shares × ($100 − $110) = −$1000
        B: 50 shares  × ($100 − $90)  = +$500
        Net = −$500
        """
        plan = select_lots([LOT_A, LOT_B, LOT_C], Decimal("15000"), AS_OF)
        assert abs(plan.realized_lt_gain - Decimal("-500")) < Decimal("0.01")

    def test_no_st_gains(self):
        plan = select_lots([LOT_A, LOT_B, LOT_C], Decimal("15000"), AS_OF)
        assert plan.realized_st_gain == Decimal("0")


class TestShortTermLastOrdering:
    def test_lt_sold_before_st(self):
        """Short-term gain lot should be sold after long-term gain lot."""
        lt_lot = make_lot("LT", shares=100, cost_per_share=80, price=100, lot_date=LT_DATE)
        st_lot = make_lot("ST", shares=100, cost_per_share=80, price=100, lot_date=ST_DATE)
        plan = select_lots([st_lot, lt_lot], Decimal("5000"), AS_OF)
        tickers = [s.lot.ticker for s in plan.sold]
        assert tickers[0] == "LT", f"Expected LT first, got {tickers}"

    def test_st_gain_in_st_bucket(self):
        """Gains from short-term lot must appear in realized_st_gain, not lt."""
        st_lot = make_lot("ST", shares=100, cost_per_share=80, price=100, lot_date=ST_DATE)
        plan = select_lots([st_lot], Decimal("10000"), AS_OF)
        assert plan.realized_st_gain > Decimal("0")
        assert plan.realized_lt_gain == Decimal("0")


class TestInsufficientHoldings:
    def test_warning_present(self):
        lot = make_lot("X", shares=10, cost_per_share=50, price=100, lot_date=LT_DATE)
        plan = select_lots([lot], Decimal("9999999"), AS_OF)
        assert any(_INSUFFICIENT_WARNING in w for w in plan.warnings)

    def test_sells_all(self):
        lot = make_lot("X", shares=10, cost_per_share=50, price=100, lot_date=LT_DATE)
        plan = select_lots([lot], Decimal("9999999"), AS_OF)
        sold = plan.sold[0]
        assert sold.shares_sold == lot.shares


class TestNonTaxableIgnored:
    def test_traditional_not_eligible(self):
        trad = make_lot("IRA", shares=100, cost_per_share=50, price=100,
                        lot_date=LT_DATE, account_type="traditional")
        taxable = make_lot("TAX", shares=100, cost_per_share=50, price=100,
                           lot_date=LT_DATE, account_type="taxable")
        plan = select_lots([trad, taxable], Decimal("5000"), AS_OF)
        tickers_sold = {s.lot.ticker for s in plan.sold}
        assert "IRA" not in tickers_sold
        assert "TAX" in tickers_sold

    def test_roth_not_eligible(self):
        roth = make_lot("ROTH", shares=100, cost_per_share=50, price=100,
                        lot_date=LT_DATE, account_type="roth")
        plan = select_lots([roth], Decimal("5000"), AS_OF)
        # Should sell nothing (no taxable lots)
        assert len(plan.sold) == 0 or plan.cash_raised == Decimal("0")


class TestUnknownHoldingPeriod:
    def test_unknown_treated_as_lt_with_warning(self):
        unknown_lot = make_lot("UNK", shares=100, cost_per_share=50, price=100, lot_date=None)
        plan = select_lots([unknown_lot], Decimal("5000"), AS_OF)
        assert any(_UNKNOWN_HP_WARNING in w for w in plan.warnings)

    def test_unknown_gain_goes_to_lt_bucket(self):
        unknown_lot = make_lot("UNK", shares=100, cost_per_share=50, price=100, lot_date=None)
        plan = select_lots([unknown_lot], Decimal("5000"), AS_OF)
        assert plan.realized_lt_gain > Decimal("0")
        assert plan.realized_st_gain == Decimal("0")

    def test_unknown_warning_emitted_only_once(self):
        lot1 = make_lot("A", shares=10, cost_per_share=50, price=100, lot_date=None)
        lot2 = make_lot("B", shares=10, cost_per_share=50, price=100, lot_date=None)
        plan = select_lots([lot1, lot2], Decimal("1000"), AS_OF)
        count = sum(1 for w in plan.warnings if _UNKNOWN_HP_WARNING in w)
        assert count == 1


class TestFullLotSale:
    def test_full_lot_sold_when_mv_equals_target(self):
        lot = make_lot("X", shares=100, cost_per_share=90, price=100, lot_date=LT_DATE)
        plan = select_lots([lot], Decimal("10000"), AS_OF)
        assert plan.sold[0].shares_sold == Decimal("100")
        assert abs(plan.cash_raised - Decimal("10000")) < Decimal("0.01")


class TestMultipleLossLots:
    def test_loss_lot_ordering_by_magnitude(self):
        """When selecting from two long-term loss lots, prefer the greater loss (higher basis).

        Lot A: −15% loss (−150 per $1000 raised, cost basis $100)
        Lot B: −5% loss (−50 per $1000 raised, cost basis $100)

        Should sell Lot A first (worse loss → more tax benefit per share).
        """
        # 100 shares @ $100 cost, $85 price → −$1500 loss, MV = $8500
        loss_lot_a = make_lot("A", shares=100, cost_per_share=100, price=85, lot_date=LT_DATE)
        # 100 shares @ $100 cost, $95 price → −$500 loss, MV = $9500
        loss_lot_b = make_lot("B", shares=100, cost_per_share=100, price=95, lot_date=LT_DATE)

        # Request $18000 to require selling both lots
        plan = select_lots([loss_lot_b, loss_lot_a], Decimal("18000"), AS_OF)
        tickers = [s.lot.ticker for s in plan.sold]
        assert tickers[0] == "A", f"Expected A first (−15% loss), got {tickers}"
        assert tickers[1] == "B", f"Expected B second (−5% loss), got {tickers}"


class TestEmptyLots:
    def test_empty_list(self):
        plan = select_lots([], Decimal("10000"), AS_OF)
        assert plan.sold == []
        assert plan.cash_raised == Decimal("0")


D = Decimal


class TestLongTermFlag:
    """Explicit long_term flag (aggregate template) drives holding period."""

    def test_flag_overrides_missing_date(self):
        lt = TaxLot("VTI", None, D("100"), D("50"), D("60"), "taxable", long_term=True)
        st = TaxLot("SNOW", None, D("100"), D("50"), D("60"), "taxable", long_term=False)
        assert lt.holding_period(date(2026, 7, 18)) == "long_term"
        assert st.holding_period(date(2026, 7, 18)) == "short_term"

    def test_short_term_flagged_position_sold_last(self):
        # Both at a gain; the ST-flagged one must be demoted below the LT one
        lt_gain = TaxLot("VTI", None, D("100"), D("50"), D("60"), "taxable", long_term=True)
        st_gain = TaxLot("SNOW", None, D("100"), D("10"), D("60"), "taxable", long_term=False)
        plan = select_lots([st_gain, lt_gain], D("6000"), as_of=date(2026, 7, 18))
        assert plan.sold[0].lot.ticker == "VTI"

    def test_selling_short_term_position_warns(self):
        st_gain = TaxLot("SNOW", None, D("100"), D("10"), D("60"), "taxable", long_term=False)
        plan = select_lots([st_gain], D("3000"), as_of=date(2026, 7, 18))
        assert any("short-term" in w.lower() for w in plan.warnings), plan.warnings

    def test_no_short_term_warning_when_only_lt_sold(self):
        lt = TaxLot("VTI", None, D("100"), D("50"), D("60"), "taxable", long_term=True)
        plan = select_lots([lt], D("3000"), as_of=date(2026, 7, 18))
        assert not any("short-term" in w.lower() for w in plan.warnings)


class TestGainRankedPerDollarRaised:
    """For a fixed cash target the tax is set by the gain realized per dollar
    of proceeds. Basis per share only ranks lots of the SAME security; across
    securities with different prices it is meaningless."""

    def test_the_cheaper_gain_is_sold_across_securities(self):
        # A: $1,000 price, $500 basis/share -> 50 cents of gain per dollar.
        # B: $100 price, $90 basis/share    -> 10 cents of gain per dollar.
        # Ranking by basis per share sold A ($500 > $90) and realized $500;
        # ten shares of B raise the same $1,000 with $100 of gain.
        a = make_lot("A", shares=10, cost_per_share=500, price=1000, lot_date=LT_DATE)
        b = make_lot("B", shares=100, cost_per_share=90, price=100, lot_date=LT_DATE)
        plan = select_lots([a, b], Decimal("1000"), AS_OF)
        assert [s.lot.ticker for s in plan.sold] == ["B"]
        assert plan.realized_lt_gain == Decimal("100")

    def test_a_stock_split_does_not_change_the_order(self):
        a = make_lot("A", shares=10, cost_per_share=500, price=1000, lot_date=LT_DATE)
        b = make_lot("B", shares=100, cost_per_share=90, price=100, lot_date=LT_DATE)
        a_split = make_lot("A", shares=200, cost_per_share=25, price=50, lot_date=LT_DATE)
        before = select_lots([a, b], Decimal("1000"), AS_OF)
        after = select_lots([a_split, b], Decimal("1000"), AS_OF)
        assert [s.lot.ticker for s in before.sold] == [s.lot.ticker for s in after.sold]
        assert before.realized_lt_gain == after.realized_lt_gain


class TestLossesFirst:
    def test_a_short_term_loss_is_sold_before_a_long_term_gain(self):
        # Selling the loss raises the cash and lowers the year's gains; the
        # long-term gain would add to them.
        st_loss = make_lot("STL", shares=100, cost_per_share=110, price=100, lot_date=ST_DATE)
        lt_gain = make_lot("LTG", shares=100, cost_per_share=80, price=100, lot_date=LT_DATE)
        plan = select_lots([lt_gain, st_loss], Decimal("5000"), AS_OF)
        assert [s.lot.ticker for s in plan.sold] == ["STL"]
        assert plan.realized_st_gain == Decimal("-500")
