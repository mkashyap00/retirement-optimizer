"""Claim-age inputs through the API: the receiving flags, pinned ages on
/optimize, and compare's what-if claim ages."""
from __future__ import annotations

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app

THIS_YEAR = date.today().year

# Self is 62 and still earning through next year; spouse is 61. Neither has claimed.
_PAYLOAD: dict = {
    "household": {
        "filing_status": "joint",
        "self_birth_date": f"{THIS_YEAR - 62}-01-01",
        "spouse_birth_date": f"{THIS_YEAR - 61}-01-01",
        "state": "TX",
    },
    "accounts": [
        {"account_type": "taxable", "owner": "joint", "balance": 300_000.0, "basis": 200_000.0},
        {"account_type": "traditional", "owner": "self", "balance": 900_000.0},
    ],
    "income": [
        {"category": "salary", "owner": "self", "amount": 90_000.0,
         "start_year": THIS_YEAR, "end_year": THIS_YEAR + 1},
    ],
    "settings": {
        "required_spending": 80_000.0,
        "ss_pia_self": 2_800.0, "ss_claim_age_self": 67, "ss_receiving_self": False,
        "ss_pia_spouse": 1_400.0, "ss_claim_age_spouse": 67, "ss_receiving_spouse": False,
    },
    "constraints": {},
}


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


def test_receiving_flags_round_trip(client):
    hh = _create(client)
    s = client.get(f"/households/{hh}").json()["settings"]
    assert (s["ss_receiving_self"], s["ss_receiving_spouse"]) == (False, False)


@pytest.mark.parametrize("settings", [
    {"ss_receiving_self": True},                               # claimed at 67 while 62?
    {"ss_receiving_self": False, "ss_claim_age_self": 62,
     "ss_receiving_spouse": False, "ss_claim_age_spouse": 62},  # spouse's 62 is past
])
def test_a_claim_age_contradicting_the_receiving_flag_is_422(client, settings):
    payload = copy.deepcopy(_PAYLOAD)
    payload["household"]["spouse_birth_date"] = f"{THIS_YEAR - 64}-01-01"
    payload["settings"].update(settings)
    resp = client.post("/households", json=payload)
    assert resp.status_code == 422, resp.text


def test_a_plan_gone_stale_is_refused_not_guessed(client, monkeypatch):
    """'Not yet receiving, claim at 67' stops making sense once self is 68."""
    import src.api.endpoints.optimization as opt

    hh = _create(client)
    monkeypatch.setattr(opt, "_today", lambda: date(THIS_YEAR + 6, 6, 1))
    resp = client.post("/optimize", json={"household_id": hh, "monte_carlo_runs": 0})
    assert resp.status_code == 422
    assert "not yet receiving" in resp.json()["detail"]


def test_pinned_claim_ages_are_echoed_and_leave_the_stored_plan_alone(client):
    hh = _create(client)
    resp = client.post("/optimize", json={
        "household_id": hh, "monte_carlo_runs": 0,
        "ss_claim_age_self": 70, "ss_claim_age_spouse": 62,
    })
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result["claim_ages"] == {"self": 70, "spouse": 62}
    assert result["pinned_claim_ages"] == {"self": 70, "spouse": 62}
    stored = client.get(f"/households/{hh}").json()["settings"]
    assert (stored["ss_claim_age_self"], stored["ss_claim_age_spouse"]) == (67, 67)

    plain = client.post("/optimize", json={"household_id": hh, "monte_carlo_runs": 0})
    assert plain.json()["result"]["claim_ages"] == {"self": 67, "spouse": 67}
    assert plain.json()["result"]["pinned_claim_ages"] is None


def test_an_ineligible_pinned_age_is_422(client):
    """Self earns a salary through next year: claiming at 62 or 63 overlaps it."""
    hh = _create(client)
    resp = client.post("/optimize", json={
        "household_id": hh, "monte_carlo_runs": 0, "ss_claim_age_self": 62,
    })
    assert resp.status_code == 422
    assert "salary" in resp.json()["detail"]


def test_unstated_receiving_past_the_claim_age_is_labeled_legacy_inference(client):
    payload = copy.deepcopy(_PAYLOAD)
    payload["household"]["self_birth_date"] = f"{THIS_YEAR - 68}-01-01"
    payload["income"] = []
    for k in ("ss_receiving_self", "ss_receiving_spouse"):
        payload["settings"].pop(k)
    hh = client.post("/households", json=payload).json()["household_id"]
    warnings = client.post(
        "/optimize", json={"household_id": hh, "monte_carlo_runs": 0}
    ).json()["result"]["warnings"]
    assert any("legacy inference" in w and "(self)" in w for w in warnings)
    assert not any("(spouse)" in w and "legacy" in w for w in warnings)


def test_over_70_and_not_receiving_is_labeled_an_assumed_filing(client):
    payload = copy.deepcopy(_PAYLOAD)
    payload["household"]["self_birth_date"] = f"{THIS_YEAR - 72}-01-01"
    payload["income"] = []
    payload["settings"]["ss_claim_age_self"] = 70
    hh = client.post("/households", json=payload)
    assert hh.status_code == 201, hh.text
    warnings = client.post(
        "/optimize", json={"household_id": hh.json()["household_id"], "monte_carlo_runs": 0}
    ).json()["result"]["warnings"]
    assert any("assumed filing" in w for w in warnings)


def test_a_compare_claim_age_override_moves_this_years_benefit():
    """Self is 66 and stored to claim at 70. A what-if claim at 66 must pay
    this year: year 0's conversion sizing reads the benefit from State."""
    from decimal import Decimal as D

    from src.api.endpoints.compare import ScenarioOverridesIn, _scenario_inputs
    from src.optimization.state import Settings, State

    state = State(
        year=2026, age_self=66, age_spouse=None, balance_taxable=D("0"),
        balance_traditional=D("500000"), balance_roth=D("0"), basis_taxable=D("0"),
        filing_status="single", state_code="TX",
    )
    settings = Settings(start_year=2026, required_spending=D("50000"),
                        ss_pia_self=D("2500"), ss_claim_age_self=70, birth_year_self=1960)
    s_state, s_settings = _scenario_inputs(
        state, settings, ScenarioOverridesIn.model_validate({"ss_claim_age_self": 66})
    )
    assert s_settings.ss_claim_age_self == 66
    assert s_state.social_security > 0 and state.social_security == 0
