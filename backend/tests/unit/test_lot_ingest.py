"""Unit tests for portfolio CSV ingest (src/portfolio/ingest.py)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from src.portfolio.ingest import _MODE_C_WARNING, ingest_csv

# ---------------------------------------------------------------------------
# Mode A fixture — per-share basis
# ---------------------------------------------------------------------------

MODE_A_CSV = """\
ticker,lot_date,shares,cost_basis_per_share,current_price,account_type
AAPL,2022-01-10,100,120.00,150.00,taxable
MSFT,2021-06-15,50,200.00,250.00,taxable
VTI,,200,80.00,90.00,roth
"""

# ---------------------------------------------------------------------------
# Mode B fixture — total basis + market value
# ---------------------------------------------------------------------------

MODE_B_CSV = """\
ticker,lot_date,shares,cost_basis_total,market_value,account_type
AAPL,2022-01-10,100,"$12,000.00","$15,000.00",taxable
MSFT,2021-06-15,50,"$10,000.00","$12,500.00",taxable
"""

# ---------------------------------------------------------------------------
# Mode C fixture — no lot dates, average cost
# ---------------------------------------------------------------------------

MODE_C_CSV = """\
ticker,shares,avg_cost_basis,market_value,account_type
VTI,200,80.00,18000.00,taxable
BND,100,50.00,5500.00,taxable
"""

# ---------------------------------------------------------------------------
# BOM + dollar/comma stripped numbers
# ---------------------------------------------------------------------------

BOM_CSV = "﻿" + MODE_A_CSV


class TestModeA:
    def test_lot_count(self):
        lots, warnings = ingest_csv(MODE_A_CSV)
        assert len(lots) == 3

    def test_no_warnings(self):
        _, warnings = ingest_csv(MODE_A_CSV)
        assert warnings == []

    def test_cost_basis_per_share_preserved(self):
        lots, _ = ingest_csv(MODE_A_CSV)
        aapl = next(lot for lot in lots if lot.ticker == "AAPL")
        assert aapl.cost_basis_per_share == Decimal("120.00")
        assert aapl.current_price == Decimal("150.00")

    def test_lot_date_parsed(self):
        lots, _ = ingest_csv(MODE_A_CSV)
        aapl = next(lot for lot in lots if lot.ticker == "AAPL")
        assert aapl.lot_date == date(2022, 1, 10)

    def test_none_lot_date_when_blank(self):
        lots, _ = ingest_csv(MODE_A_CSV)
        vti = next(lot for lot in lots if lot.ticker == "VTI")
        assert vti.lot_date is None

    def test_account_type_normalised(self):
        lots, _ = ingest_csv(MODE_A_CSV)
        vti = next(lot for lot in lots if lot.ticker == "VTI")
        assert vti.account_type == "roth"

    def test_ticker_uppercased(self):
        csv = (
            "ticker,lot_date,shares,cost_basis_per_share,current_price,account_type\n"
            "aapl,2022-01-10,10,100.00,110.00,taxable\n"
        )
        lots, _ = ingest_csv(csv)
        assert lots[0].ticker == "AAPL"


class TestModeB:
    def test_lot_count(self):
        lots, _ = ingest_csv(MODE_B_CSV)
        assert len(lots) == 2

    def test_derives_per_share_cost_basis(self):
        lots, _ = ingest_csv(MODE_B_CSV)
        aapl = next(lot for lot in lots if lot.ticker == "AAPL")
        # cost_basis_total=$12000 / shares=100 → 120
        assert aapl.cost_basis_per_share == Decimal("120.00")

    def test_derives_current_price(self):
        lots, _ = ingest_csv(MODE_B_CSV)
        aapl = next(lot for lot in lots if lot.ticker == "AAPL")
        # market_value=$15000 / shares=100 → 150
        assert aapl.current_price == Decimal("150.00")

    def test_dollar_comma_stripped(self):
        # $12,000.00 should parse without error; covered by deriving basis above
        lots, _ = ingest_csv(MODE_B_CSV)
        assert len(lots) == 2


class TestModeC:
    def test_lot_count(self):
        lots, _ = ingest_csv(MODE_C_CSV)
        assert len(lots) == 2

    def test_lot_dates_are_none(self):
        lots, _ = ingest_csv(MODE_C_CSV)
        for lot in lots:
            assert lot.lot_date is None

    def test_mode_c_warning_present(self):
        _, warnings = ingest_csv(MODE_C_CSV)
        assert any(_MODE_C_WARNING in w for w in warnings), warnings

    def test_avg_cost_basis_used_as_per_share(self):
        lots, _ = ingest_csv(MODE_C_CSV)
        vti = next(lot for lot in lots if lot.ticker == "VTI")
        # avg_cost_basis=80, market_value=18000/200=90
        assert vti.cost_basis_per_share == Decimal("80.00")
        assert vti.current_price == Decimal("90.00")


class TestBOM:
    def test_bom_stripped(self):
        lots, _ = ingest_csv(BOM_CSV)
        assert len(lots) == 3


class TestDollarCommaNumbers:
    def test_dollar_comma_mode_a(self):
        # Dollar amounts with commas must be quoted in the CSV cell
        csv = (
            "ticker,lot_date,shares,cost_basis_per_share,current_price,account_type\n"
            'AAPL,2022-01-10,100,"$1,234.56","$1,500.00",taxable\n'
        )
        lots, _ = ingest_csv(csv)
        assert lots[0].cost_basis_per_share == Decimal("1234.56")
        assert lots[0].current_price == Decimal("1500.00")


class TestMalformedHeader:
    def test_unknown_header_raises_value_error(self):
        csv = "foo,bar,baz\n1,2,3\n"
        with pytest.raises(ValueError) as exc_info:
            ingest_csv(csv)
        msg = str(exc_info.value)
        # Message should name the expected sets
        assert "Mode A" in msg or "mode" in msg.lower()

    def test_error_message_names_expected_columns(self):
        csv = "ticker,mystery_col,shares\n1,2,3\n"
        with pytest.raises(ValueError) as exc_info:
            ingest_csv(csv)
        msg = str(exc_info.value)
        # Should at least mention what was expected
        assert "ticker" in msg.lower() or "cost_basis" in msg.lower()


class TestBlankLines:
    def test_blank_lines_skipped(self):
        csv = (
            "ticker,lot_date,shares,cost_basis_per_share,current_price,account_type\n"
            "AAPL,2022-01-10,100,120.00,150.00,taxable\n"
            "\n"
            "MSFT,2021-06-15,50,200.00,250.00,taxable\n"
        )
        lots, _ = ingest_csv(csv)
        assert len(lots) == 2


# ---------------------------------------------------------------------------
# Template format — the documented v1 aggregate-position layout
# ---------------------------------------------------------------------------

TEMPLATE_CSV = """\
symbol,shares,price,cost_basis,account_type,long_term
VTI,500,"$285.10","$95,225",taxable,
SNOW,100,180.00,21000,taxable,no
VTSAX,1000,132.50,,traditional,
"""


class TestTemplateFormat:
    """The predefined aggregate template: symbol/shares/price/total cost basis."""

    def test_parses_positions(self):
        lots, warnings = ingest_csv(TEMPLATE_CSV)
        assert len(lots) == 3
        assert warnings == []

    def test_maps_columns(self):
        lots, _ = ingest_csv(TEMPLATE_CSV)
        vti = lots[0]
        assert vti.ticker == "VTI"
        assert vti.shares == Decimal("500")
        assert vti.current_price == Decimal("285.10")
        # total cost basis $95,225 / 500 shares → 190.45 per share
        assert vti.cost_basis_per_share == Decimal("190.45")
        assert vti.total_cost_basis == Decimal("95225")
        assert vti.account_type == "taxable"
        assert vti.lot_date is None

    def test_long_term_flag_parsed(self):
        lots, _ = ingest_csv(TEMPLATE_CSV)
        today = date(2026, 7, 18)
        # blank → assumed long-term; explicit "no" → short-term
        assert lots[0].holding_period(today) == "long_term"
        assert lots[1].holding_period(today) == "short_term"

    def test_basis_optional_outside_taxable(self):
        lots, _ = ingest_csv(TEMPLATE_CSV)
        assert lots[2].account_type == "traditional"
        assert lots[2].cost_basis_per_share == Decimal("0")

    def test_missing_basis_on_taxable_row_rejected(self):
        bad = (
            "symbol,shares,price,cost_basis,account_type\n"
            "VTI,500,285.10,,taxable\n"
        )
        with pytest.raises(ValueError, match="cost_basis"):
            ingest_csv(bad)

    def test_total_cost_basis_divided_by_shares(self):
        csv = (
            "symbol,shares,price,cost_basis,account_type\n"
            "VTI,400,285.10,76000,taxable\n"
        )
        lots, _ = ingest_csv(csv)
        # $76,000 / 400 shares → 190.00 per share
        assert lots[0].cost_basis_per_share == Decimal("190")
        assert lots[0].total_cost_basis == Decimal("76000")

    def test_long_term_column_optional(self):
        csv_no_flag = (
            "symbol,shares,price,cost_basis,account_type\n"
            "VTI,500,285.10,95225,taxable\n"
        )
        lots, warnings = ingest_csv(csv_no_flag)
        assert lots[0].holding_period(date(2026, 7, 18)) == "long_term"
        assert warnings == []

    def test_tab_separated_paste_accepted(self):
        """A range pasted from Excel/Sheets is tab-separated — sniff it."""
        tsv = (
            "symbol\tshares\tprice\tcost_basis\taccount_type\tlong_term\n"
            "VTI\t500\t285.10\t95225\ttaxable\t\n"
        )
        lots, warnings = ingest_csv(tsv)
        assert len(lots) == 1
        assert lots[0].ticker == "VTI"
        assert lots[0].cost_basis_per_share == Decimal("190.45")
        assert warnings == []

    def test_header_spaces_normalised_to_underscores(self):
        """`cost basis` (a space) must match the `cost_basis` column."""
        csv = (
            "symbol,shares,price,cost basis,account_type\n"
            "VTI,500,285.10,95225,taxable\n"
        )
        lots, _ = ingest_csv(csv)
        assert lots[0].cost_basis_per_share == Decimal("190.45")

    def test_tab_paste_with_spaced_header(self):
        """The exact shape from the user's failed upload: tabs + `cost basis`."""
        pasted = (
            "symbol\tshares\tprice\tcost basis\taccount_type\tlong_term\n"
            "VTI\t500\t285.10\t95225\ttaxable\t\n"
        )
        lots, warnings = ingest_csv(pasted)
        assert len(lots) == 1
        assert lots[0].total_cost_basis == Decimal("95225")
        assert warnings == []
