"""Claim-age preview: the search's eligibility rules before anything runs."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app

Y = date.today().year


@pytest.fixture
def client():
    with TestClient(create_app(":memory:")) as c:
        yield c


def _preview(client, **over):
    body = {
        "household": {"filing_status": "joint", "state": "TX",
                      "self_birth_date": f"{Y - 62}-01-01",
                      "spouse_birth_date": f"{Y - 61}-01-01"},
        # Self earns through next year: 62 and 63 overlap it before FRA.
        "income": [{"category": "salary", "owner": "self", "amount": 90000,
                    "start_year": Y, "end_year": Y + 1}],
        "ss_pia_self": 2800, "ss_claim_age_self": 67, "ss_receiving_self": False,
        "ss_pia_spouse": 1400, "ss_claim_age_spouse": 67, "ss_receiving_spouse": False,
    }
    body.update(over)
    r = client.post("/claim-ages/preview", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_searchable_people_get_eligible_ages_and_reasons(client):
    p = _preview(client)
    assert p["self"]["status"] == "searchable"
    assert p["self"]["ages"] == [64, 65, 66, 67, 68, 69, 70]
    assert [e["age"] for e in p["self"]["exclusions"]] == [62, 63]
    assert "before full retirement age" in p["self"]["exclusions"][0]["reason"]
    assert p["spouse"]["ages"] == list(range(62, 71)) and p["spouse"]["exclusions"] == []
    assert p["self"]["entered_age"] == 67


def test_receiving_fixes_the_age_and_unknown_asks(client):
    p = _preview(client, ss_receiving_self=True, ss_claim_age_self=62,
                 ss_receiving_spouse=None, ss_claim_age_spouse=62,
                 household={"filing_status": "joint", "state": "TX",
                            "self_birth_date": f"{Y - 62}-01-01",
                            "spouse_birth_date": f"{Y - 64}-01-01"})
    assert p["self"]["status"] == "receiving" and p["self"]["ages"] == [62]
    assert p["spouse"]["status"] == "needs_answer"


def test_contradictions_and_missing_benefits_are_reported(client):
    p = _preview(client, ss_receiving_self=True, ss_claim_age_self=67, ss_pia_spouse=None)
    assert p["self"]["status"] == "invalid" and "later than their age" in p["self"]["message"]
    assert p["spouse"]["status"] == "no_benefit"


def test_a_single_filer_has_no_spouse(client):
    p = _preview(client, household={"filing_status": "single", "state": "TX",
                                    "self_birth_date": f"{Y - 62}-01-01"})
    assert p["spouse"] is None


def test_a_saved_plan_previews_the_way_a_run_reads_it(client):
    payload = {
        "household": {"filing_status": "joint", "state": "TX",
                      "self_birth_date": f"{Y - 62}-01-01",
                      "spouse_birth_date": f"{Y - 61}-01-01"},
        "accounts": [{"account_type": "traditional", "owner": "self", "balance": 500000}],
        "income": [{"category": "salary", "owner": "self", "amount": 90000,
                    "start_year": Y, "end_year": Y + 1}],
        "settings": {"required_spending": 60000,
                     "ss_pia_self": 2800, "ss_claim_age_self": 67, "ss_receiving_self": False,
                     "ss_pia_spouse": 1400, "ss_claim_age_spouse": 67,
                     "ss_receiving_spouse": False},
        "constraints": {},
    }
    hh = client.post("/households", json=payload).json()["household_id"]
    p = client.get(f"/households/{hh}/claim-ages").json()
    assert p["self"]["ages"] == [64, 65, 66, 67, 68, 69, 70]
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/households/{missing}/claim-ages").status_code == 404
