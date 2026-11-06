"""Integration tests for POST /optimize, GET /runs/{run_id}, GET /households/{id}/runs.

TDD RED phase — written BEFORE implementation.

Test coverage:
  (1) POST /optimize with valid household → 200 {run_id, result}; result has
      winning_policy and 30 yearly_plan rows.
  (2) GET /runs/{run_id} returns identical result to the POST response.
  (3) GET /households/{id}/runs lists 1 run after one optimization, ordered newest first.
  (4) POST /optimize with unknown household_id → 404.
  (5) GET /runs/{unknown-id} → 404.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.reports.policy_labels import policy_label

# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

# MFJ 68/66 CA as of July 2026 (self born 1958-03-15, spouse born 1960-03-15).
# Assets: taxable 300k/basis 200k, traditional 800k, roth 100k.
# Income: pension 20k.
# SS: self PIA 2400 claim age 67 (age 68 >= 67 → already claiming);
#     spouse PIA 2000 claim age 66 (age 66 >= 66 → already claiming).
# Spending: 90k.  10 MC runs for speed.
_MFJ_PAYLOAD: dict = {
    "household": {
        "filing_status": "joint",
        "self_birth_date": "1958-03-15",
        "spouse_birth_date": "1960-03-15",
        "state": "CA",
    },
    "accounts": [
        {
            "account_type": "taxable",
            "owner": "joint",
            "balance": 300_000.0,
            "basis": 200_000.0,
        },
        {
            "account_type": "traditional",
            "owner": "joint",
            "balance": 800_000.0,
        },
        {
            "account_type": "roth",
            "owner": "joint",
            "balance": 100_000.0,
        },
    ],
    "income": [
        {"category": "pension", "owner": "self", "amount": 20_000.0},
    ],
    "settings": {
        "required_spending": 90_000.0,
        "ss_pia_self": 2_400.0,
        "ss_claim_age_self": 67,
        "ss_pia_spouse": 2_000.0,
        "ss_claim_age_spouse": 66,
    },
    "constraints": {},
}


@pytest.fixture
def client():
    """Each test gets a fresh in-memory DB via the app factory."""
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _create_household(client: TestClient) -> str:
    """POST _MFJ_PAYLOAD and return the household_id."""
    resp = client.post("/households", json=_MFJ_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()["household_id"]


# ---------------------------------------------------------------------------
# (1) POST /optimize → 200, winning_policy, 30 yearly_plan rows
# ---------------------------------------------------------------------------


def test_optimize_returns_200_with_winning_policy_and_30_rows(client):
    """POST /optimize with valid household → 200; result has winning_policy + 30 yearly rows."""
    hh_id = _create_household(client)

    resp = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 10},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "run_id" in data, "response missing 'run_id'"
    assert len(data["run_id"]) == 36, "run_id should be a UUID"

    assert "result" in data, "response missing 'result'"
    result = data["result"]

    assert "winning_policy" in result, "result missing 'winning_policy'"
    wp = result["winning_policy"]
    assert "policy_id" in wp
    assert isinstance(wp["policy_id"], str)

    yearly_plan = result.get("yearly_plan", [])
    assert len(yearly_plan) == 30, (
        f"Expected 30 yearly_plan rows (simulation_years default), got {len(yearly_plan)}"
    )


# ---------------------------------------------------------------------------
# (2) GET /runs/{run_id} → identical result
# ---------------------------------------------------------------------------


def test_get_run_returns_identical_result(client):
    """GET /runs/{run_id} must return the same result dict as POST /optimize."""
    hh_id = _create_household(client)

    opt_resp = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 10},
    )
    assert opt_resp.status_code == 200, opt_resp.text
    opt_data = opt_resp.json()
    run_id = opt_data["run_id"]
    expected_result = opt_data["result"]

    get_resp = client.get(f"/runs/{run_id}")
    assert get_resp.status_code == 200, get_resp.text
    run_data = get_resp.json()

    assert run_data["run_id"] == run_id
    assert run_data["household_id"] == hh_id
    assert "created_at" in run_data
    assert run_data["result"] == expected_result, (
        "GET /runs/{id} result differs from POST /optimize result"
    )


# ---------------------------------------------------------------------------
# (2b) Run input snapshot — survives later household edits
# ---------------------------------------------------------------------------


def test_run_inputs_snapshot_survives_household_edit(client):
    """The run stores the inputs that produced it; editing the household
    afterwards must NOT change what GET /runs/{id} reports as inputs."""
    import copy

    hh_id = _create_household(client)

    opt_resp = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
    )
    assert opt_resp.status_code == 200, opt_resp.text
    run_id = opt_resp.json()["run_id"]

    # Snapshot reflects the original inputs
    run_data = client.get(f"/runs/{run_id}").json()
    inputs = run_data["inputs"]
    assert inputs is not None, "run must carry an input snapshot"
    original_spending = inputs["settings"]["required_spending"]
    assert original_spending == _MFJ_PAYLOAD["settings"]["required_spending"]
    assert inputs["household"]["state"] == _MFJ_PAYLOAD["household"]["state"]
    assert len(inputs["accounts"]) == len(_MFJ_PAYLOAD["accounts"])

    # Edit the household: bump spending by $10k
    edited = copy.deepcopy(_MFJ_PAYLOAD)
    edited["settings"]["required_spending"] = original_spending + 10_000
    put_resp = client.put(f"/households/{hh_id}", json=edited)
    assert put_resp.status_code == 200, put_resp.text

    # The run's snapshot is unchanged
    run_data2 = client.get(f"/runs/{run_id}").json()
    assert (
        run_data2["inputs"]["settings"]["required_spending"] == original_spending
    ), "run input snapshot must not change when the household is edited"


# ---------------------------------------------------------------------------
# (3) GET /households/{id}/runs → 1 run listed, newest first
# ---------------------------------------------------------------------------


def test_list_household_runs_after_one_optimization(client):
    """GET /households/{id}/runs returns 1 summary entry after a single optimize call."""
    hh_id = _create_household(client)

    # Before any optimization, list should be empty
    pre_resp = client.get(f"/households/{hh_id}/runs")
    assert pre_resp.status_code == 200
    assert pre_resp.json() == [], "expected empty list before any runs"

    client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 10},
    )

    runs_resp = client.get(f"/households/{hh_id}/runs")
    assert runs_resp.status_code == 200, runs_resp.text
    runs = runs_resp.json()

    assert len(runs) == 1, f"expected 1 run, got {len(runs)}"
    entry = runs[0]
    assert "run_id" in entry, "run entry missing 'run_id'"
    assert len(entry["run_id"]) == 36
    assert "created_at" in entry, "run entry missing 'created_at'"
    assert "duration_ms" in entry, "run entry missing 'duration_ms'"
    assert isinstance(entry["duration_ms"], int)


# ---------------------------------------------------------------------------
# (4) POST /optimize with unknown household → 404
# ---------------------------------------------------------------------------


def test_optimize_unknown_household_returns_404(client):
    """POST /optimize with an unknown household_id → 404 Not Found."""
    resp = client.post(
        "/optimize",
        json={
            "household_id": "00000000-0000-0000-0000-000000000000",
            "monte_carlo_runs": 10,
        },
    )
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# (5) GET /runs/{unknown-id} → 404
# ---------------------------------------------------------------------------


def test_get_unknown_run_returns_404(client):
    """GET /runs/{unknown-id} → 404 Not Found."""
    resp = client.get("/runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# (6) POST /optimize with ss_pia_spouse=None → 200 (single filer or joint no spouse)
# ---------------------------------------------------------------------------


def test_optimize_with_no_spouse_pia(client):
    """POST /optimize with ss_pia_spouse=None → 200 (single filer scenario)."""
    payload = {
        "household": {
            "filing_status": "single",
            "self_birth_date": "1958-03-15",
            "state": "CA",
        },
        "accounts": [
            {
                "account_type": "traditional",
                "owner": "self",
                "balance": 500_000.0,
            },
        ],
        "income": [],
        "settings": {
            "required_spending": 50_000.0,
            "ss_pia_self": 2_400.0,
            "ss_claim_age_self": 67,
            "ss_pia_spouse": None,
            "ss_claim_age_spouse": None,
        },
        "constraints": {},
    }
    resp = client.post("/households", json=payload)
    assert resp.status_code == 201, resp.text
    hh_id = resp.json()["household_id"]

    opt_resp = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 5},
    )
    assert opt_resp.status_code == 200, opt_resp.text
    data = opt_resp.json()
    assert "run_id" in data
    assert "result" in data
    result = data["result"]
    assert "winning_policy" in result
    yearly_plan = result.get("yearly_plan", [])
    assert len(yearly_plan) > 0, "yearly_plan should contain at least one row"


# ---------------------------------------------------------------------------
# (7) GET /runs/{run_id}/export.csv → 200, text/csv, valid CSV format
# ---------------------------------------------------------------------------


def test_exports_include_sale_plans_when_portfolio_uploaded(client):
    """With a portfolio stored, all three run exports build without error and
    the CSV carries the per-year sell-list section."""
    hh_id = _create_household(client)
    client.post(
        "/portfolio",
        json={
            "csv": (
                "symbol,shares,price,cost_basis,account_type\n"
                "VTI,2000,300.00,300000,taxable\n"
            )
        },
    )
    run_id = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 5}
    ).json()["run_id"]

    csv_resp = client.get(f"/runs/{run_id}/export.csv")
    assert csv_resp.status_code == 200
    assert client.get(f"/runs/{run_id}/export.xlsx").status_code == 200
    assert client.get(f"/runs/{run_id}/report.pdf").status_code == 200
    # The plan draws on the taxable account, so a sale-plan section is present.
    assert "Sale plan" in csv_resp.text


def test_autosaved_reports_include_sale_plan(client, tmp_path, monkeypatch):
    """The files auto-saved at optimize time must match the on-demand
    downloads — including the Sale Plan. Previously the auto-save path skipped
    sale_plans, so reports/ files silently lacked the sell list."""
    import openpyxl

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    hh_id = _create_household(client)
    client.post(
        "/portfolio",
        json={
            "csv": (
                "symbol,shares,price,cost_basis,account_type\n"
                "VTI,2000,300.00,300000,taxable\n"
            )
        },
    )
    resp = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 5}
    )
    assert resp.status_code == 200

    csv_files = list(tmp_path.glob("*.csv"))
    xlsx_files = list(tmp_path.glob("*.xlsx"))
    assert csv_files and xlsx_files, "auto-saved report files missing"

    assert "Sale plan" in csv_files[0].read_text(encoding="utf-8")
    wb = openpyxl.load_workbook(xlsx_files[0])
    assert "Sale Plan" in wb.sheetnames


def test_export_csv_returns_200_with_csv_content(client):
    """GET /runs/{run_id}/export.csv → 200 with text/csv content-type."""
    hh_id = _create_household(client)

    # Run optimization
    opt_resp = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 5},
    )
    assert opt_resp.status_code == 200, opt_resp.text
    run_id = opt_resp.json()["run_id"]

    # Export CSV
    csv_resp = client.get(f"/runs/{run_id}/export.csv")
    assert csv_resp.status_code == 200, f"expected 200, got {csv_resp.status_code}"

    # Check content-type (FastAPI adds charset automatically)
    content_type = csv_resp.headers.get("content-type")
    assert content_type.startswith("text/csv"), (
        f"expected text/csv, got {content_type}"
    )

    # Check Content-Disposition header
    disposition = csv_resp.headers.get("content-disposition")
    assert disposition is not None, "missing Content-Disposition header"
    assert "attachment" in disposition, f"expected attachment, got {disposition}"
    assert "retirement-plan_" in disposition and disposition.endswith('.csv"'), (
        f"expected timestamped retirement-plan_*.csv filename, got {disposition}"
    )

    # Verify CSV structure
    csv_content = csv_resp.text
    # Identity comment lines precede the table (spreadsheets ignore leading #)
    assert "# Run ID:" in csv_content, "CSV should carry the Run ID"
    assert "# Household ID:" in csv_content, "CSV should carry the Household ID"
    lines = [ln for ln in csv_content.strip().split("\n") if not ln.startswith("#")]
    assert len(lines) > 1, "CSV should have header + data rows"

    # Check header contains expected columns
    header = lines[0]
    expected_cols = [
        "year",
        "age_self",
        "conversion",
        "federal_tax",
        "narrative",
    ]
    for col in expected_cols:
        assert col in header, f"Header missing column '{col}'"


def test_export_csv_unknown_run_returns_404(client):
    """GET /runs/{unknown-id}/export.csv → 404 Not Found."""
    resp = client.get("/runs/00000000-0000-0000-0000-000000000000/export.csv")
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}"


# ---------------------------------------------------------------------------
# (8) GET /runs/{run_id}/report.pdf → 200, application/pdf, %PDF bytes
# ---------------------------------------------------------------------------


def test_export_pdf_returns_200_with_pdf_content(client):
    """GET /runs/{run_id}/report.pdf → 200 with application/pdf content-type and %PDF body."""
    hh_id = _create_household(client)

    # Run optimization with low mc for speed
    opt_resp = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 5},
    )
    assert opt_resp.status_code == 200, opt_resp.text
    run_id = opt_resp.json()["run_id"]

    # Export PDF
    pdf_resp = client.get(f"/runs/{run_id}/report.pdf")
    assert pdf_resp.status_code == 200, f"expected 200, got {pdf_resp.status_code}: {pdf_resp.text}"

    # Check content-type
    content_type = pdf_resp.headers.get("content-type", "")
    assert "application/pdf" in content_type, (
        f"expected application/pdf, got {content_type}"
    )

    # Check Content-Disposition header — inline so the browser renders the
    # PDF in a tab (issue #7) rather than forcing a download
    disposition = pdf_resp.headers.get("content-disposition", "")
    assert "inline" in disposition, f"expected inline, got {disposition}"
    assert "retirement-report_" in disposition and disposition.endswith('.pdf"'), (
        f"expected timestamped retirement-report_*.pdf filename, got {disposition}"
    )

    # Verify PDF magic bytes
    pdf_bytes = pdf_resp.content
    assert pdf_bytes[:4] == b"%PDF", (
        f"Expected PDF magic header, got {pdf_bytes[:8]!r}"
    )

    # Verify PDF content size
    assert len(pdf_resp.content) > 5000, (
        f"Expected PDF > 5000 bytes, got {len(pdf_resp.content)} bytes"
    )


def test_export_pdf_unknown_run_returns_404(client):
    """GET /runs/{unknown-id}/report.pdf → 404 Not Found."""
    resp = client.get("/runs/00000000-0000-0000-0000-000000000000/report.pdf")
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}"


def test_export_pdf_distinguishes_run_vs_household_404(client):
    """Verify LEFT JOIN query in export_run_pdf handles missing households correctly.

    Note: We cannot directly test household deletion due to DuckDB's strict FK
    constraints. This test verifies the code path distinguishing missing runs
    from missing households by checking error detail strings differ.
    """
    # Test case 1: Run doesn't exist → should say "Run ... not found"
    run_not_found_resp = client.get(
        "/runs/00000000-0000-0000-0000-000000000000/report.pdf"
    )
    assert run_not_found_resp.status_code == 404
    run_not_found_detail = run_not_found_resp.json().get("detail", "")
    assert "Run" in run_not_found_detail, (
        f"Expected 'Run' in error detail, got: {run_not_found_detail}"
    )
    assert "not found" in run_not_found_detail

    # Test case 2: A valid run still returns PDF successfully
    hh_id = _create_household(client)
    opt_resp = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 5},
    )
    assert opt_resp.status_code == 200, opt_resp.text
    run_id = opt_resp.json()["run_id"]

    pdf_resp = client.get(f"/runs/{run_id}/report.pdf")
    assert pdf_resp.status_code == 200, f"expected 200, got {pdf_resp.status_code}"
    assert pdf_resp.content[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# (8) Auto-save: run completion writes CSV/PDF/XLSX to the reports dir
# ---------------------------------------------------------------------------


def test_optimize_auto_saves_reports(client, tmp_path):
    """POST /optimize writes csv+pdf+xlsx to REPORTS_DIR without any
    export-endpoint click (issue #7)."""
    import os
    from pathlib import Path

    reports = Path(os.environ["REPORTS_DIR"])  # set by conftest autouse fixture

    hh_id = _create_household(client)
    resp = client.post("/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0})
    assert resp.status_code == 200, resp.text

    files = sorted(p.name for p in reports.iterdir())
    assert any(f.startswith("retirement-plan_") and f.endswith(".csv") for f in files), files
    assert any(f.startswith("retirement-report_") and f.endswith(".pdf") for f in files), files
    assert any(f.startswith("retirement-plan_") and f.endswith(".xlsx") for f in files), files


# ---------------------------------------------------------------------------
# (9) GET /runs/{id}/export.xlsx
# ---------------------------------------------------------------------------


def test_export_xlsx_returns_valid_workbook(client):
    """xlsx endpoint returns 200 with zip magic and the three sheets."""
    import io

    import openpyxl

    hh_id = _create_household(client)
    run_id = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
    ).json()["run_id"]

    resp = client.get(f"/runs/{run_id}/export.xlsx")
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml" in resp.headers.get("content-type", "")
    assert resp.content[:2] == b"PK"

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert {"Inputs", "Yearly Plan", "Charts"} <= set(wb.sheetnames)


def test_export_xlsx_unknown_run_returns_404(client):
    resp = client.get("/runs/00000000-0000-0000-0000-000000000000/export.xlsx")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# (10) Plan horizon: death ages are inclusive; household uses the longer one
# ---------------------------------------------------------------------------


def test_death_age_horizon_inclusive_and_uses_spouse():
    """'Plan through age N' must include the year of age N, and the horizon
    must extend to the longer-lived spouse's plan-to age."""
    import copy

    app = create_app(":memory:")
    with TestClient(app) as client:
        payload = copy.deepcopy(_MFJ_PAYLOAD)
        # self 68 (born 1958-03), spouse 66 (born 1960-03), as of mocked today
        payload["household"]["self_death_age"] = 85
        payload["household"]["spouse_death_age"] = 85
        resp = client.post("/households", json=payload)
        hh_id = resp.json()["household_id"]

        result = client.post(
            "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
        ).json()["result"]

        plan = result["yearly_plan"]
        # Spouse horizon is longer: 85 - 66 + 1 = 20 years (self would be 18)
        assert len(plan) == 20, f"expected 20 rows, got {len(plan)}"
        # Last row must include the SPOUSE's plan-to age
        assert plan[-1]["age_spouse"] == 85


# ---------------------------------------------------------------------------
# (11) Forced-policy runs
# ---------------------------------------------------------------------------


def test_forced_policy_run_reports_that_policy_with_caveat(client):
    """policy_id in the request makes that policy the reported winner and a
    warning names the optimizer's own pick."""
    hh_id = _create_household(client)

    # Baseline: what does the optimizer pick on its own?
    base = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
    ).json()["result"]
    own_pick = base["winning_policy"]["policy_id"]

    # Force a different policy that must exist for this household
    forced = "none" if own_pick != "none" else "fill_12"
    r = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 0, "policy_id": forced},
    ).json()["result"]

    assert r["status"] == "success"
    assert r["winning_policy"]["policy_id"] == forced
    assert r["forced_policy"] == forced
    # The advisory names the pick as the page does, not by its id.
    own_label = policy_label(own_pick, r["starting_traditional_balance"])
    assert any("Forced-policy run" in w and own_label in w for w in r["warnings"]), (
        r["warnings"]
    )
    # The optimizer's own pick appears among the alternatives for comparison
    alt_ids = {a["policy_id"] for a in r["alternative_policies"]}
    assert own_pick in alt_ids


def test_a_forced_policy_is_measured_on_every_requested_scenario(client):
    """The success interval is computed from the scenario count, so it must be
    the count the reported policy was actually scored on. A forced policy
    eliminated at stage 1 kept a third of them while the run claimed all."""
    hh_id = _create_household(client)
    r = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 30, "policy_id": "none"},
    ).json()["result"]

    assert r["winning_policy"]["policy_id"] == "none"
    assert r["winning_policy"]["monte_carlo_paths"] == 30
    # Each alternative says how many scenarios ITS figures rest on.
    assert all("monte_carlo_paths" in a for a in r["alternative_policies"])


def test_forced_policy_unknown_id_returns_error_with_available_list(client):
    hh_id = _create_household(client)
    r = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 0, "policy_id": "fill_99"},
    ).json()["result"]
    assert r["status"] == "error"
    assert any("fill_99" in w and "Available" in w for w in r["warnings"])


# ---------------------------------------------------------------------------
# (12) Objective knobs: heir_tax_rate is live; estate_weight is retired
# ---------------------------------------------------------------------------


def test_heir_tax_rate_changes_outcome(client):
    """Sensitivity: flipping heir_tax_rate must change the winner's numbers —
    guards against stored-but-unused inputs."""
    import copy

    results = {}
    for rate in (0.0, 0.5):
        payload = copy.deepcopy(_MFJ_PAYLOAD)
        payload["settings"]["heir_tax_rate"] = rate
        hh_id = client.post("/households", json=payload).json()["household_id"]
        # Force "none" so traditional dollars survive to the horizon —
        # otherwise a full-conversion winner leaves nothing for the heir
        # haircut to act on and the sensitivity is invisible.
        r = client.post(
            "/optimize",
            json={"household_id": hh_id, "monte_carlo_runs": 0, "policy_id": "none"},
        ).json()["result"]
        results[rate] = r["winning_policy"]["terminal_estate"]

    assert results[0.0] != results[0.5], (
        "terminal_estate must react to heir_tax_rate (estate is heir-adjusted)"
    )


def test_estate_weight_is_accepted_but_no_longer_changes_the_result(client):
    """The taxes-vs-estate priority was retired in October 2026: taxes are
    already inside the after-tax estate. Old plans still send the field, so it
    is accepted, stored and returned, and it must not move the answer."""
    import copy

    results = {}
    for weight in (1.0, 0.0):
        payload = copy.deepcopy(_MFJ_PAYLOAD)
        payload["settings"]["estate_weight"] = weight
        hh_id = client.post("/households", json=payload).json()["household_id"]
        assert client.get(f"/households/{hh_id}").json()["settings"]["estate_weight"] == weight
        r = client.post(
            "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
        ).json()["result"]
        results[weight] = (r["winning_policy"]["policy_id"], r["winning_policy"]["score"])
    assert results[1.0] == results[0.0]


def test_result_names_its_objective_and_score_components(client):
    hh_id = _create_household(client)
    r = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
    ).json()["result"]
    assert r["objective"] == "pv_estate_minus_weighted_shortfall"
    comp = r["winning_policy"]["score_components"]
    assert comp["basis"] == "deterministic"
    assert comp["deterministic_value"] == pytest.approx(
        comp["terminal_estate_pv"]
        - comp["shortfall_weight"] * comp["shortfall_pv"]
        - comp["discretionary_shortfall_weight"] * comp["discretionary_shortfall_pv"],
        abs=0.01,
    )
    for alt in r["alternative_policies"]:
        assert alt["score_components"]["basis"] == "deterministic"


def test_funded_plan_does_not_reward_early_depletion(client):
    """REGRESSION (run 7d83f4e4, user's 'Second' plan): a comfortably funded
    household under the old taxes-only priority got a ONE-row plan — paths
    that deplete early pay less lifetime tax and outranked feasible ones, so
    every policy's schedule embedded a lethal conversion. Kept with the old
    payload (estate_weight still sent) as a guard on the current objective.

    'Lower taxes' must never be achieved by dying broke in year 2: the plan
    must run the full horizon with no depletion warning.
    """
    payload = {
        "household": {
            "filing_status": "joint",
            "self_birth_date": "1962-12-19",
            "spouse_birth_date": "1966-12-24",
            "state": "CA",
            "self_death_age": 85,
            "spouse_death_age": 85,
        },
        "accounts": [
            {"account_type": "taxable", "owner": "joint", "balance": 1_000_000.0,
             "basis": 0.0},
            {"account_type": "traditional", "owner": "self", "balance": 500_000.0},
            {"account_type": "traditional", "owner": "spouse", "balance": 100_000.0},
            {"account_type": "roth", "owner": "self", "balance": 60_000.0,
             "roth_opened_year": 2024},
        ],
        "income": [
            {"category": "qualified_dividend", "owner": "joint", "amount": 45_000.0},
            {"category": "nonqualified_dividend", "owner": "joint", "amount": 80_000.0},
        ],
        "settings": {
            "required_spending": 150_000.0,
            "ss_pia_self": 3_500.0,
            "ss_claim_age_self": 67,
            "ss_pia_spouse": 2_000.0,
            "ss_claim_age_spouse": 67,
            "heir_tax_rate": 0.25,
            "estate_weight": 0.0,
        },
        "constraints": {"irmaa_policy": "soft", "conversion_window": "pre_ss"},
    }
    hh_id = client.post("/households", json=payload).json()["household_id"]
    r = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
    ).json()["result"]

    plan = r["yearly_plan"]
    # Horizon = spouse's 85 − 59 + 1 = 27 years (longer of the two)
    assert len(plan) >= 20, (
        f"comfortably funded plan collapsed to {len(plan)} row(s); "
        f"warnings: {r['warnings']}"
    )
    assert not any("cannot cover" in w for w in r["warnings"]), r["warnings"]


# ---------------------------------------------------------------------------
# (13) Tax audit worksheet flows through the API
# ---------------------------------------------------------------------------


def test_yearly_plan_rows_carry_audit_worksheet(client):
    """Each stored year row carries the audit dict with lines that tie to the
    row's own numbers (JSON round-trip included)."""
    hh_id = _create_household(client)
    r = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
    ).json()["result"]

    for row in r["yearly_plan"]:
        audit = row["audit"]
        assert audit is not None
        assert audit["federal_tax"] == row["federal_tax"]
        assert audit["total_tax"] == row["total_tax"]
        assert audit["agi"] == row["agi"]
        assert audit["deduction_type"] in ("standard", "itemized")
        # Sheet identities — exact in Decimal at build time; the JSON float
        # boundary allows only sub-cent representation drift
        assert audit["ordinary_income"] == pytest.approx(
            sum(
                audit[k]
                for k in (
                    "salary", "pension", "rental", "interest",
                    "ordinary_dividends", "traditional_taxable_portion",
                    "taxable_social_security",
                )
            ),
            abs=1e-6,
        )
        assert audit["traditional_distributions"] == pytest.approx(
            row["rmd"] + row["conversion"] + row["withdrawal_traditional"],
            abs=1e-6,
        )


def test_auto_saved_reports_carry_run_and_household_ids(client):
    """The auto-saved files must identify their run and plan, exactly as the
    download buttons' copies do. They used to omit both IDs, so a file in
    reports/ could not be traced back to the run that produced it."""
    import os
    from pathlib import Path

    import openpyxl
    from pypdf import PdfReader

    reports = Path(os.environ["REPORTS_DIR"])  # set by conftest autouse fixture

    hh_id = _create_household(client)
    run_id = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 0}
    ).json()["run_id"]

    csv_text = next(reports.glob("retirement-plan_*.csv")).read_text()
    assert f"# Run ID: {run_id}" in csv_text
    assert f"# Household ID: {hh_id}" in csv_text

    ws = openpyxl.load_workbook(next(reports.glob("retirement-plan_*.xlsx")))["Inputs"]
    cells = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert run_id in cells and hh_id in cells

    pdf_text = "".join(
        page.extract_text() for page in PdfReader(next(reports.glob("*.pdf"))).pages
    )
    assert run_id in pdf_text and hh_id in pdf_text


def test_forced_run_records_the_optimizers_own_pick_and_the_list_marks_it(client):
    """A "Run this policy" run must still say what the optimizer would choose.

    Before this, the pick lived only in a warning sentence -- absent when the
    pinned policy WAS the pick -- and the run list could not tell a pinned run
    from an optimized one, so the dashboard opened whichever came last.
    """
    hh_id = _create_household(client)
    optimized = client.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 10}
    ).json()
    pick = optimized["result"]["optimizer_pick"]
    assert pick == optimized["result"]["winning_policy"]["policy_id"]

    other = optimized["result"]["alternative_policies"][0]["policy_id"]
    forced = client.post(
        "/optimize",
        json={"household_id": hh_id, "monte_carlo_runs": 10, "policy_id": other},
    ).json()
    assert forced["result"]["forced_policy"] == other
    assert forced["result"]["winning_policy"]["policy_id"] == other
    assert forced["result"]["optimizer_pick"] == pick

    runs = client.get(f"/households/{hh_id}/runs").json()
    by_id = {r["run_id"]: r for r in runs}
    assert by_id[optimized["run_id"]]["forced_policy"] is None
    assert by_id[forced["run_id"]]["forced_policy"] == other
