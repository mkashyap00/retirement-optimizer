"""POST /optimize/jobs → poll → a persisted joint run."""
from __future__ import annotations

import copy
import json
import threading
import time
from datetime import date

import pytest
import src.api.endpoints.optimization as opt_endpoint
from fastapi.testclient import TestClient
from src.api.app import create_app

THIS_YEAR = date.today().year

# Both 69 and not yet claiming: a 2×2 grid (69 or 70 each), 11-year horizon.
_PAYLOAD: dict = {
    "household": {
        "filing_status": "joint",
        "self_birth_date": f"{THIS_YEAR - 69}-01-01",
        "spouse_birth_date": f"{THIS_YEAR - 69}-01-01",
        "state": "TX", "self_death_age": 80, "spouse_death_age": 80,
    },
    "accounts": [
        {"account_type": "taxable", "owner": "joint", "balance": 300_000.0, "basis": 200_000.0},
        {"account_type": "traditional", "owner": "self", "balance": 1_200_000.0},
    ],
    "income": [],
    "settings": {
        "required_spending": 70_000.0,
        "ss_pia_self": 3_000.0, "ss_claim_age_self": 70, "ss_receiving_self": False,
        "ss_pia_spouse": 1_800.0, "ss_claim_age_spouse": 70, "ss_receiving_spouse": False,
    },
    "constraints": {},
}
_SEARCH_BOTH = {"self": {"mode": "search"}, "spouse": {"mode": "search"}}
_SMALL = {"monte_carlo_runs": 6, "stage1_runs": 2, "claim_search": _SEARCH_BOTH}


@pytest.fixture
def client():
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c


def _create(client, **settings) -> str:
    payload = copy.deepcopy(_PAYLOAD)
    payload["settings"].update(settings)
    resp = client.post("/households", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["household_id"]


def _poll(client, job_id: str, timeout: float = 300.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/optimize/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_a_job_persists_a_joint_run_with_its_input_snapshot(client):
    hh = _create(client)
    resp = client.post("/optimize/jobs", json={"household_id": hh, **_SMALL})
    assert resp.status_code == 202, resp.text
    job = _poll(client, resp.json()["job_id"])
    assert job["status"] == "done", job
    # The last phase reported is saving the run ("Prepare results").
    assert job["phase"] == "prepare"

    run = client.get(f"/runs/{job['run_id']}").json()
    result = run["result"]
    assert result["search"]["mode"] == "joint"
    assert result["winning_policy"]["key"] == result["joint_winner"]["key"]
    assert result["search"]["schedules"][result["joint_winner"]["key"]] is not None
    # The snapshot is the household as it was read for the run.
    assert run["inputs"] == client.get(f"/households/{hh}").json()

    runs = client.get(f"/households/{hh}/runs").json()
    assert [r["claim_search"] for r in runs] == [True]

    # The stored run exports with its claim-age section through the download endpoints.
    csv = client.get(f"/runs/{job['run_id']}/export.csv")
    assert csv.status_code == 200 and "# Explore other Social Security claim ages" in csv.text
    assert client.get(f"/runs/{job['run_id']}/export.xlsx").status_code == 200
    assert client.get(f"/runs/{job['run_id']}/report.pdf").status_code == 200


def test_the_request_record_carries_the_search_controls_and_date(client):
    hh = _create(client)
    job = _poll(client, client.post(
        "/optimize/jobs",
        json={"household_id": hh, **_SMALL,
              "claim_search": {"self": {"mode": "search"},
                               "spouse": {"mode": "fixed", "age": 69}}},
    ).json()["job_id"])
    db = client.app.state.db
    request = json.loads(db.fetch_one("SELECT request_json FROM runs WHERE id = ?",
                                      [job["run_id"]])[0])
    assert request["claim_search"] == {"self": {"mode": "search", "age": None},
                                       "spouse": {"mode": "fixed", "age": 69}}
    assert request["valuation_date"] == date.today().isoformat()
    assert (request["monte_carlo_runs"], request["stage1_runs"]) == (6, 2)
    result = client.get(f"/runs/{job['run_id']}").json()["result"]
    assert {s["claim_age_spouse"] for s in result["search"]["scenarios"]} == {69}


def test_a_second_job_is_409_while_one_runs(client, monkeypatch):
    hh = _create(client)
    started, release = threading.Event(), threading.Event()
    real = opt_endpoint.run_joint_optimization

    def slow(*args, on_progress=None, **kw):
        started.set()
        release.wait(30)
        return real(*args, on_progress=on_progress, **kw)

    monkeypatch.setattr(opt_endpoint, "run_joint_optimization", slow)
    first = client.post("/optimize/jobs", json={"household_id": hh, **_SMALL}).json()
    assert started.wait(10)
    busy = client.post("/optimize/jobs", json={"household_id": hh, **_SMALL})
    assert busy.status_code == 409
    assert busy.json()["detail"]["job_id"] == first["job_id"]
    assert client.get("/optimize/jobs/active").json()["id"] == first["job_id"]
    release.set()
    assert _poll(client, first["job_id"])["status"] == "done"
    assert client.get("/optimize/jobs/active").json() is None


def test_unknown_job_is_404(client):
    assert client.get("/optimize/jobs/does-not-exist").status_code == 404


def test_validation_errors_come_back_in_the_request(client):
    assert client.post("/optimize/jobs", json={"household_id": "missing"}).status_code == 404
    hh = _create(client, ss_receiving_self=None, ss_claim_age_self=67)
    resp = client.post("/optimize/jobs", json={"household_id": hh, **_SMALL})
    assert resp.status_code == 422 and "self" in resp.json()["detail"]
    hh = _create(client)
    resp = client.post("/optimize/jobs", json={
        "household_id": hh, **_SMALL,
        "claim_search": {"self": {"mode": "fixed", "age": 62}, "spouse": {"mode": "search"}},
    })
    assert resp.status_code == 422
    assert client.get("/optimize/jobs/active").json() is None


def test_a_plan_without_claim_ages_can_only_be_searched(client):
    """No age chosen: a search runs without "your ages" baselines; anything
    that would hold the blank age fixed is refused rather than modelling no
    benefit."""
    hh = _create(client, ss_claim_age_self=None, ss_claim_age_spouse=None)
    for path, body in (
        ("/optimize", {"household_id": hh, "monte_carlo_runs": 0}),
        ("/optimize/jobs", {"household_id": hh, "monte_carlo_runs": 6, "stage1_runs": 2,
                            "claim_search": {"self": {"mode": "search"},
                                             "spouse": {"mode": "fixed"}}}),
    ):
        resp = client.post(path, json=body)
        assert resp.status_code == 422, (path, resp.text)
        assert "claim age" in resp.text
    assert client.get(f"/households/{hh}/policies").status_code == 422

    resp = client.post("/optimize/jobs", json={"household_id": hh, **_SMALL})
    assert resp.status_code == 202, resp.text
    job = _poll(client, resp.json()["job_id"])
    assert job["status"] == "done", job
    result = client.get(f"/runs/{job['run_id']}").json()["result"]
    assert set(result["search"]["baselines"]) == {"winner_ages_no_conversion"}
    # The exports read such a run too.
    for path in ("report.pdf", "export.xlsx", "export.csv"):
        assert client.get(f"/runs/{job['run_id']}/{path}").status_code == 200, path
    csv = client.get(f"/runs/{job['run_id']}/export.csv").text
    assert "No comparison claim ages were provided." in csv
