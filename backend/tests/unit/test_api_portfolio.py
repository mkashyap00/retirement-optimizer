"""Integration tests for portfolio upload and sale-plan API endpoints.

Uses FastAPI TestClient with an in-memory DuckDB. The portfolio is keyed to
the app-level default profile (not a household); reconciliation against a
plan is opt-in via the ``household_id`` query param on upload.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_HH_PAYLOAD = {
    "household": {
        "filing_status": "single",
        "self_birth_date": "1965-03-15",
        "state": "CA",
    },
    "accounts": [
        {"account_type": "taxable", "owner": "self", "balance": 100000.0, "basis": 80000.0},
    ],
    "income": [],
    "settings": {
        "required_spending": 60000.0,
        "ss_pia_self": 2000.0,
    },
    "constraints": {
        "irmaa_policy": "ignore",
        "conversion_window": "anytime",
    },
}

_CSV_MODE_A = """\
ticker,lot_date,shares,cost_basis_per_share,current_price,account_type
AAPL,2022-01-10,100,120.00,150.00,taxable
MSFT,2021-06-15,50,200.00,250.00,taxable
"""

_BAD_CSV = "foo,bar,baz\n1,2,3\n"

_UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def client():
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def household_id(client):
    """Create a household and return its id (used as reconciliation context)."""
    resp = client.post("/households", json=_HH_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["household_id"]


# ---------------------------------------------------------------------------
# POST /portfolio
# ---------------------------------------------------------------------------


class TestUploadPortfolio:
    def test_upload_returns_200_with_count(self, client):
        resp = client.post("/portfolio", json={"csv": _CSV_MODE_A})
        assert resp.status_code == 200
        data = resp.json()
        assert data["lots"] == 2
        assert isinstance(data["warnings"], list)

    def test_upload_unknown_reconciliation_household_returns_404(self, client):
        resp = client.post(
            f"/portfolio?household_id={_UNKNOWN_ID}",
            json={"csv": _CSV_MODE_A},
        )
        assert resp.status_code == 404

    def test_upload_bad_csv_returns_400(self, client):
        resp = client.post("/portfolio", json={"csv": _BAD_CSV})
        assert resp.status_code == 400
        assert len(resp.json()["detail"]) > 0

    def test_upload_mode_c_includes_warning(self, client):
        mode_c = (
            "ticker,shares,avg_cost_basis,market_value,account_type\n"
            "VTI,200,80.00,18000.00,taxable\n"
        )
        resp = client.post("/portfolio", json={"csv": mode_c})
        assert resp.status_code == 200
        assert any("Lot-level detail" in w for w in resp.json()["warnings"])

    def test_second_upload_overwrites_first(self, client):
        """Uploading a second time replaces the stored portfolio."""
        resp1 = client.post("/portfolio", json={"csv": _CSV_MODE_A})
        assert resp1.json()["lots"] == 2

        single_lot = (
            "ticker,lot_date,shares,cost_basis_per_share,current_price,account_type\n"
            "VTI,2022-01-01,100,80.00,100.00,taxable\n"
        )
        resp2 = client.post("/portfolio", json={"csv": single_lot})
        assert resp2.json()["lots"] == 1

    def test_get_portfolio_empty_before_upload(self, client):
        resp = client.get("/portfolio")
        assert resp.status_code == 200
        body = resp.json()
        assert body["positions"] == []
        assert body["uploaded_at"] is None

    def test_get_portfolio_returns_stored_holdings(self, client):
        client.post("/portfolio", json={"csv": _CSV_MODE_A})
        resp = client.get("/portfolio")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["positions"]) == 2
        tickers = {p["ticker"] for p in body["positions"]}
        assert tickers == {"AAPL", "MSFT"}
        assert body["uploaded_at"] is not None
        p = next(p for p in body["positions"] if p["ticker"] == "AAPL")
        for key in ("shares", "price", "market_value", "cost_basis", "holding_period"):
            assert key in p

    def test_upload_shared_across_plans(self, client):
        """One upload serves any plan — a second household sees the same
        portfolio without re-uploading (the whole point of profile keying)."""
        client.post("/portfolio", json={"csv": _CSV_MODE_A})
        # A brand-new household created afterwards still gets a sale plan.
        client.post("/households", json=_HH_PAYLOAD)
        resp = client.get("/portfolio/sale-plan", params={"target_cash": 5000})
        assert resp.status_code == 200
        assert len(resp.json()["sold"]) >= 1


# ---------------------------------------------------------------------------
# GET /portfolio/sale-plan
# ---------------------------------------------------------------------------


class TestSalePlan:
    def test_sale_plan_without_upload_returns_404(self, client):
        resp = client.get("/portfolio/sale-plan", params={"target_cash": 10000})
        assert resp.status_code == 404

    def test_sale_plan_roundtrip(self, client):
        client.post("/portfolio", json={"csv": _CSV_MODE_A})
        resp = client.get("/portfolio/sale-plan", params={"target_cash": 5000})
        assert resp.status_code == 200
        data = resp.json()
        assert "sold" in data
        assert "cash_raised" in data
        assert "realized_lt_gain" in data
        assert "realized_st_gain" in data
        assert "warnings" in data

    def test_sale_plan_sold_list_has_rows(self, client):
        client.post("/portfolio", json={"csv": _CSV_MODE_A})
        resp = client.get("/portfolio/sale-plan", params={"target_cash": 5000})
        assert resp.status_code == 200
        entry = resp.json()["sold"][0]
        for key in ("ticker", "shares_sold", "proceeds", "realized_gain", "holding_period"):
            assert key in entry, f"Missing key {key!r} in sold entry"

    def test_sale_plan_cash_raised_near_target(self, client):
        """Cash raised should be within a few cents of target (partial lots)."""
        client.post("/portfolio", json={"csv": _CSV_MODE_A})
        target = 5000.0
        resp = client.get("/portfolio/sale-plan", params={"target_cash": target})
        assert abs(resp.json()["cash_raised"] - target) < 0.01


# ---------------------------------------------------------------------------
# GET /portfolio/sale-plan.csv and .pdf — dated exports
# ---------------------------------------------------------------------------


class TestSalePlanExports:
    def test_csv_export_without_upload_returns_404(self, client):
        resp = client.get("/portfolio/sale-plan.csv", params={"target_cash": 5000})
        assert resp.status_code == 404

    def test_csv_export_is_dated_and_attachment(self, client):
        client.post("/portfolio", json={"csv": _CSV_MODE_A})
        resp = client.get(
            "/portfolio/sale-plan.csv",
            params={"target_cash": 5000, "spend": 3000, "convtax": 2000, "year": 2029},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert "sale-plan-" in resp.headers["content-disposition"]
        body = resp.text
        assert "Sale Plan" in body
        assert "Prices as of" in body
        assert "Funding spending" in body
        assert "Funding Roth conversion tax" in body
        assert "2029" in body
        assert "Profile ID" in body

    def test_pdf_export_returns_pdf_bytes(self, client):
        client.post("/portfolio", json={"csv": _CSV_MODE_A})
        resp = client.get("/portfolio/sale-plan.pdf", params={"target_cash": 5000})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"
        assert "attachment" in resp.headers["content-disposition"]

    def test_pdf_export_without_upload_returns_404(self, client):
        resp = client.get("/portfolio/sale-plan.pdf", params={"target_cash": 5000})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reconciliation: uploaded totals vs the plan's account figures (opt-in)
# ---------------------------------------------------------------------------

_TEMPLATE_MATCHING = """\
symbol,shares,price,cost_basis,account_type
VTI,500,200.00,80000,taxable
"""
# 500 × 200 = 100,000 market value — matches the plan's taxable balance;
# 80,000 cost basis — matches the plan's taxable basis exactly

_TEMPLATE_STALE = """\
symbol,shares,price,cost_basis,account_type
VTI,500,140.00,80000,taxable
"""
# 500 × 140 = 70,000 — 30% below the plan's 100,000 taxable balance;
# basis still matches so only the price/balance warning fires

_TEMPLATE_BASIS_MISMATCH = """\
symbol,shares,price,cost_basis,account_type
VTI,500,200.00,50000,taxable
"""
# market value matches (100,000) but cost basis 50,000 vs the plan's 80,000


class TestReconciliation:
    def test_matching_totals_no_warning(self, client, household_id):
        resp = client.post(
            f"/portfolio?household_id={household_id}",
            json={"csv": _TEMPLATE_MATCHING},
        )
        assert resp.status_code == 200
        assert not any(
            "differ" in w or "balance" in w or "cost basis" in w
            for w in resp.json()["warnings"]
        ), resp.json()["warnings"]

    def test_stale_totals_warn_with_both_numbers(self, client, household_id):
        resp = client.post(
            f"/portfolio?household_id={household_id}",
            json={"csv": _TEMPLATE_STALE},
        )
        assert resp.status_code == 200
        warnings = resp.json()["warnings"]
        recon = [w for w in warnings if "taxable" in w and "$70,000" in w and "$100,000" in w]
        assert recon, f"expected reconciliation warning naming both totals: {warnings}"
        assert any("price" in w.lower() for w in recon), recon

    def test_cost_basis_mismatch_warns(self, client, household_id):
        resp = client.post(
            f"/portfolio?household_id={household_id}",
            json={"csv": _TEMPLATE_BASIS_MISMATCH},
        )
        assert resp.status_code == 200
        warnings = resp.json()["warnings"]
        recon = [
            w
            for w in warnings
            if "cost basis" in w and "$50,000" in w and "$80,000" in w
        ]
        assert recon, f"expected cost-basis reconciliation warning: {warnings}"
        assert not any("balance is" in w for w in warnings), warnings

    def test_no_reconciliation_without_household_context(self, client):
        """Uploading from the top-nav (no plan context) skips reconciliation."""
        resp = client.post("/portfolio", json={"csv": _TEMPLATE_STALE})
        assert resp.status_code == 200
        assert not any("balance is" in w for w in resp.json()["warnings"])
