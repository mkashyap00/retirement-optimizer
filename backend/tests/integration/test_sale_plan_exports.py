"""The sale plan in the CSV/Excel/PDF exports says when its prices are from
and everything the selector found wrong.

A portfolio uploaded long ago, holding one short-term share worth $100, asked
to fund a $1,000 withdrawal: the exports said "prices as of" the download
date, listed $100 of proceeds, and gave no hint that the holdings fell $900
short or that the sale was short-term.
"""
import csv
import io
import json
from datetime import date

import pytest
from src.api.sale_plans import run_sale_plans
from src.data.database import DEFAULT_PROFILE_ID, Database
from src.reports.csv_export import yearly_plan_csv

_TODAY = date(2026, 10, 15)


@pytest.fixture
def db():
    d = Database(":memory:")
    d.connect()
    d.execute(
        "INSERT INTO profile_portfolios (profile_id, uploaded_at, lots_json, warnings_json) "
        "VALUES (?, TIMESTAMP '2020-01-01 09:00:00', ?, '[]')",
        [DEFAULT_PROFILE_ID, json.dumps([{
            "ticker": "SNOW", "lot_date": None, "shares": "1",
            "cost_basis_per_share": "40", "current_price": "100",
            "account_type": "taxable", "long_term": False,
        }])],
    )
    yield d
    d.close()


_RESULT = {"yearly_plan": [{"year": 2026, "withdrawal_taxable": 1000.0}]}


def test_prices_are_dated_by_the_upload_not_the_download(db):
    plans = run_sale_plans(db, _RESULT, _TODAY)
    assert plans["as_of"] == "2020-01-01"
    assert plans["generated_on"] == "2026-10-15"


def test_the_shortfall_and_the_selectors_warnings_are_kept(db):
    year = run_sale_plans(db, _RESULT, _TODAY)["years"][0]
    assert year["cash_raised"] == 100.0
    assert year["cash_short"] == 900.0
    text = " ".join(year["warnings"]).lower()
    assert "insufficient" in text
    assert "short-term" in text


def test_the_csv_carries_them(db):
    out = yearly_plan_csv({"yearly_plan": []}, sale_plans=run_sale_plans(db, _RESULT, _TODAY))
    assert "prices as of 2020-01-01" in out
    assert "Insufficient taxable holdings" in out
    rows = list(csv.reader(io.StringIO(out[out.index("year,target_cash"):])))
    header, first = rows[0], rows[1]
    assert dict(zip(header, first, strict=False))["cash_short"] == "900.00"


def test_the_excel_sheet_carries_them(db):
    from openpyxl import load_workbook
    from src.reports.xlsx_export import build_xlsx

    result = {"yearly_plan": [], "winning_policy": {}, "alternative_policies": []}
    wb = load_workbook(io.BytesIO(build_xlsx(
        result, None, sale_plans=run_sale_plans(db, _RESULT, _TODAY))))
    values = " ".join(str(c.value) for row in wb["Sale Plan"].iter_rows()
                      for c in row if c.value is not None)
    assert "prices as of 2020-01-01" in values
    assert "Insufficient taxable holdings" in values
    assert "900" in values


def test_auto_saved_reports_of_two_runs_in_one_second_do_not_collide(tmp_path, monkeypatch):
    from src.reports.storage import save_run_reports

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = {"yearly_plan": [], "winning_policy": {}, "alternative_policies": [],
              "warnings": []}
    a = save_run_reports("2026-10-15 09:00:00.1", result, None, run_id="aaaa1111-x")
    b = save_run_reports("2026-10-15 09:00:00.9", result, None, run_id="bbbb2222-y")
    assert a["csv"] != b["csv"]
    assert a["csv"].exists() and b["csv"].exists()
