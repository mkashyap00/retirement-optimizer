"""Unit tests for sale_plans.run_sale_plans.

The sale plan embedded in run exports is an *annual-cadence* artifact: every
year is priced against today's holdings, so future years would show a nearly
identical sell list. The user re-runs the plan each year with a fresh
portfolio, so only the FIRST taxable-withdrawal year is actionable — the
export must carry that one year and no more.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from src.api.sale_plans import run_sale_plans


class _FakeDB:
    """Minimal stand-in exposing the single fetch_one run_sale_plans uses."""

    def __init__(self, lots: list[dict] | None):
        self._lots = lots

    def fetch_one(self, _sql: str, _params: list):
        if self._lots is None:
            return None
        # lots_json, warnings_json, uploaded_at
        return (json.dumps(self._lots), "[]", datetime(2026, 7, 5, 9, 0))


def _lot(ticker: str, shares: str) -> dict:
    return {
        "ticker": ticker,
        "lot_date": None,
        "shares": shares,
        "cost_basis_per_share": "10",
        "current_price": "100",
        "account_type": "taxable",
        "long_term": True,
    }


_LOTS = [_lot("AAA", "1000"), _lot("BBB", "1000")]


def test_only_first_withdrawal_year_is_included():
    """Two withdrawal years in the plan → sale plan carries only the first."""
    db = _FakeDB(_LOTS)
    result = {
        "yearly_plan": [
            {"year": 2026, "withdrawal_taxable": 100_000},
            {"year": 2027, "withdrawal_taxable": 50_000},
            {"year": 2028, "withdrawal_taxable": 0},
        ]
    }

    out = run_sale_plans(db, result, as_of=date(2026, 7, 23))

    assert out is not None
    assert len(out["years"]) == 1
    assert out["years"][0]["year"] == 2026


def test_first_withdrawal_year_need_not_be_year_zero():
    """The 'year 0' is the first year that actually draws on taxable — later
    if the opening years have no taxable withdrawal."""
    db = _FakeDB(_LOTS)
    result = {
        "yearly_plan": [
            {"year": 2026, "withdrawal_taxable": 0},
            {"year": 2027, "withdrawal_taxable": 0},
            {"year": 2028, "withdrawal_taxable": 80_000},
            {"year": 2029, "withdrawal_taxable": 40_000},
        ]
    }

    out = run_sale_plans(db, result, as_of=date(2026, 7, 23))

    assert out is not None
    assert len(out["years"]) == 1
    assert out["years"][0]["year"] == 2028


def test_no_taxable_withdrawal_returns_none():
    db = _FakeDB(_LOTS)
    result = {"yearly_plan": [{"year": 2026, "withdrawal_taxable": 0}]}
    assert run_sale_plans(db, result, as_of=date(2026, 7, 23)) is None


def test_no_portfolio_returns_none():
    db = _FakeDB(None)
    result = {"yearly_plan": [{"year": 2026, "withdrawal_taxable": 100_000}]}
    assert run_sale_plans(db, result, as_of=date(2026, 7, 23)) is None
