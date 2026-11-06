"""Integration tests for FastAPI CRUD endpoints — written BEFORE implementation (TDD).

All tests are expected to FAIL (ImportError / 404 / etc.) until
backend/src/api/app.py and friends are created.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

_PAYLOAD = {
    "household": {
        "filing_status": "single",
        "self_birth_date": "1965-03-15",
        "state": "CA",
    },
    "accounts": [
        {"account_type": "traditional", "owner": "self", "balance": 500000.0},
        {"account_type": "taxable", "owner": "self", "balance": 200000.0, "basis": 150000.0},
        {"account_type": "roth", "owner": "self", "balance": 75000.0},
    ],
    "income": [
        {"category": "salary", "owner": "self", "amount": 120000.0, "end_year": 2030},
    ],
    "settings": {
        "required_spending": 80000.0,
        "ss_pia_self": 2500.0,
    },
    "constraints": {
        "irmaa_policy": "soft",
        "conversion_window": "anytime",
    },
}


@pytest.fixture
def client():
    """Each test gets a fresh in-memory DB via the app factory."""
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


def test_root_returns_service_info(client):
    """GET / → 200 with name, version, docs, frontend keys."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Retirement Optimizer API"
    assert "version" in data
    assert "docs" in data
    assert "frontend" in data


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client, monkeypatch):
    """GET /health → 200 {"status": "ok", "llm": <bool>}."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["llm"] is False


# ---------------------------------------------------------------------------
# POST /households
# ---------------------------------------------------------------------------


def test_create_household_returns_201_with_uuid(client):
    """POST /households → 201 {"household_id": "<uuid>"}."""
    resp = client.post("/households", json=_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert "household_id" in data
    # UUID4: 8-4-4-4-12
    assert len(data["household_id"]) == 36


# ---------------------------------------------------------------------------
# GET /households/{id}
# ---------------------------------------------------------------------------


def test_create_and_get_roundtrip_preserves_fields(client):
    """POST then GET: filing_status, account balances, required_spending survive."""
    create_resp = client.post("/households", json=_PAYLOAD)
    assert create_resp.status_code == 201
    hh_id = create_resp.json()["household_id"]

    get_resp = client.get(f"/households/{hh_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()

    # Top-level shape
    assert body["household_id"] == hh_id
    assert "household" in body
    assert "accounts" in body
    assert "income" in body
    assert "settings" in body
    assert "constraints" in body

    # Spot: household fields
    hh = body["household"]
    assert hh["filing_status"] == "single"
    assert hh["state"] == "CA"

    # Spot: account balances
    balances = {a["account_type"]: a["balance"] for a in body["accounts"]}
    assert balances["traditional"] == pytest.approx(500_000.0)
    assert balances["taxable"] == pytest.approx(200_000.0)
    assert balances["roth"] == pytest.approx(75_000.0)

    # Spot: settings required_spending
    assert body["settings"]["required_spending"] == pytest.approx(80_000.0)


def test_constraint_knobs_roundtrip(client):
    """marginal_rate_limit and max_conversion_per_year survive POST → GET, so
    the wizard values persist and a copied plan carries them."""
    payload = {
        **_PAYLOAD,
        "constraints": {
            "irmaa_policy": "soft",
            "conversion_window": "anytime",
            "marginal_rate_limit": 0.22,
            "max_conversion_per_year": 50000.0,
        },
    }
    hh_id = client.post("/households", json=payload).json()["household_id"]
    constraints = client.get(f"/households/{hh_id}").json()["constraints"]
    assert float(constraints["marginal_rate_limit"]) == pytest.approx(0.22)
    assert float(constraints["max_conversion_per_year"]) == pytest.approx(50000.0)


def test_ss_cola_roundtrip(client):
    """The projected COLA survives POST -> GET; omitted stays null (follow
    inflation) and an explicit 0 stays 0 (flat benefits)."""
    for sent, got in ((None, None), (0.0, 0.0), (0.025, 0.025)):
        settings = dict(_PAYLOAD["settings"])
        if sent is not None:
            settings["ss_cola"] = sent
        hh_id = client.post("/households", json={**_PAYLOAD, "settings": settings}
                            ).json()["household_id"]
        assert client.get(f"/households/{hh_id}").json()["settings"]["ss_cola"] == got


def test_ss_cola_rejects_a_percentage_typed_as_a_whole_number(client):
    settings = {**_PAYLOAD["settings"], "ss_cola": 3}
    assert client.post("/households", json={**_PAYLOAD, "settings": settings}
                       ).status_code == 422


def test_get_missing_household_returns_404(client):
    """GET /households/<unknown-uuid> → 404."""
    resp = client.get("/households/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /households/{id}
# ---------------------------------------------------------------------------


def test_delete_household_returns_204(client):
    """DELETE /households/{id} → 204 No Content."""
    create_resp = client.post("/households", json=_PAYLOAD)
    hh_id = create_resp.json()["household_id"]

    del_resp = client.delete(f"/households/{hh_id}")
    assert del_resp.status_code == 204


def test_delete_then_get_returns_404(client):
    """After DELETE, GET /households/{id} → 404."""
    create_resp = client.post("/households", json=_PAYLOAD)
    hh_id = create_resp.json()["household_id"]

    client.delete(f"/households/{hh_id}")

    get_resp = client.get(f"/households/{hh_id}")
    assert get_resp.status_code == 404


def test_delete_missing_household_returns_404(client):
    """DELETE on a non-existent id → 404."""
    resp = client.delete("/households/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /households (list)
# ---------------------------------------------------------------------------


def test_list_households_initially_empty(client):
    """GET /households → [] when no households exist."""
    resp = client.get("/households")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_households_grows_after_create(client):
    """GET /households list length increases after POST."""
    client.post("/households", json=_PAYLOAD)
    resp = client.get("/households")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert "household_id" in item
    assert item["filing_status"] == "single"
    assert item["state"] == "CA"
    assert "created_at" in item


# ---------------------------------------------------------------------------
# PUT /households/{id}
# ---------------------------------------------------------------------------


def test_put_roundtrip_updates_fields_and_no_duplicate_rows(client):
    """POST → PUT with changed settings and extra account → GET reflects exactly the new state."""
    import copy

    create_resp = client.post("/households", json=_PAYLOAD)
    assert create_resp.status_code == 201
    hh_id = create_resp.json()["household_id"]

    updated = copy.deepcopy(_PAYLOAD)
    updated["settings"]["required_spending"] = 90000.0
    updated["accounts"].append(
        {"account_type": "roth", "owner": "self", "balance": 50000.0}
    )

    put_resp = client.put(f"/households/{hh_id}", json=updated)
    assert put_resp.status_code == 200
    assert put_resp.json() == {"household_id": hh_id}

    body = client.get(f"/households/{hh_id}").json()
    assert body["settings"]["required_spending"] == pytest.approx(90000.0)
    # 3 original accounts + 1 added, none duplicated
    assert len(body["accounts"]) == 4


def test_put_missing_household_returns_404(client):
    """PUT on an unknown id → 404."""
    resp = client.put(
        "/households/00000000-0000-0000-0000-000000000000", json=_PAYLOAD
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Transaction rollback on POST failure
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Nickname CRUD
# ---------------------------------------------------------------------------


def test_create_with_nickname_returned_in_list_and_get(client):
    """POST with nickname → list + get both return the nickname."""
    hh_with_nick = {**_PAYLOAD["household"], "nickname": "Retire at 65"}
    payload_with_nick = {**_PAYLOAD, "household": hh_with_nick}
    resp = client.post("/households", json=payload_with_nick)
    assert resp.status_code == 201
    hh_id = resp.json()["household_id"]

    # list endpoint includes nickname
    items = client.get("/households").json()
    assert len(items) == 1
    assert items[0]["nickname"] == "Retire at 65"

    # get detail includes nickname in nested household object
    body = client.get(f"/households/{hh_id}").json()
    assert body["household"]["nickname"] == "Retire at 65"


def test_create_without_nickname_backward_compatible(client):
    """POST without nickname (old payload shape) → nickname is None; no error."""
    resp = client.post("/households", json=_PAYLOAD)
    assert resp.status_code == 201
    hh_id = resp.json()["household_id"]

    items = client.get("/households").json()
    assert items[0]["nickname"] is None

    body = client.get(f"/households/{hh_id}").json()
    assert body["household"]["nickname"] is None


def test_put_updates_nickname(client):
    """PUT with a different nickname updates the stored value."""
    resp = client.post("/households", json=_PAYLOAD)
    hh_id = resp.json()["household_id"]

    hh_updated = {**_PAYLOAD["household"], "nickname": "Early Retire"}
    updated = {**_PAYLOAD, "household": hh_updated}
    client.put(f"/households/{hh_id}", json=updated)

    body = client.get(f"/households/{hh_id}").json()
    assert body["household"]["nickname"] == "Early Retire"


def test_put_without_nickname_clears_existing(client):
    """POST with nickname → PUT without nickname key → GET returns None (replace semantics)."""
    # POST with nickname
    hh_with_nick = {**_PAYLOAD["household"], "nickname": "Retire at 65"}
    payload_with_nick = {**_PAYLOAD, "household": hh_with_nick}
    resp = client.post("/households", json=payload_with_nick)
    hh_id = resp.json()["household_id"]

    # Verify nickname was stored
    body = client.get(f"/households/{hh_id}").json()
    assert body["household"]["nickname"] == "Retire at 65"

    # PUT with same payload but household object omits nickname key (replace semantics)
    updated = {**_PAYLOAD}  # This household has no nickname key
    put_resp = client.put(f"/households/{hh_id}", json=updated)
    assert put_resp.status_code == 200

    # GET should show nickname cleared to None
    body = client.get(f"/households/{hh_id}").json()
    assert body["household"]["nickname"] is None


def test_create_transaction_rolls_back_on_settings_failure(monkeypatch):
    """If the settings INSERT raises, the transaction rolls back — no orphan household."""
    from src.api.app import create_app
    from src.data.database import Database

    app = create_app(":memory:")

    original_execute = Database.execute

    def failing_execute(self, sql, params=None):
        if "INSERT INTO settings" in sql:
            raise RuntimeError("simulated settings-insert failure")
        return original_execute(self, sql, params)

    monkeypatch.setattr(Database, "execute", failing_execute)

    with TestClient(app) as c:
        resp = c.post("/households", json=_PAYLOAD)
        assert resp.status_code == 500

        # No orphaned household row should exist
        items = c.get("/households").json()
        assert items == []


@pytest.mark.parametrize("path, value", [
    (("accounts", 0, "balance"), -1),
    (("settings", "required_spending"), -50000),
    (("household", "state"), "ZZ"),
    (("income", 0, "end_year"), 2020),  # before its start year below
])
def test_an_invalid_household_is_rejected_and_not_stored(client, path, value):
    import copy

    payload = copy.deepcopy(_PAYLOAD)
    payload["income"][0]["start_year"] = 2025
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    resp = client.post("/households", json=payload)
    assert resp.status_code == 422
    assert client.get("/households").json() == []


def test_a_failed_create_is_logged_without_the_payload(client, monkeypatch, caplog):
    import logging

    import src.api.endpoints.households as households_mod

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(households_mod, "_insert_children", boom)
    with caplog.at_level(logging.ERROR, logger="src.api.endpoints.households"):
        resp = client.post("/households", json=_PAYLOAD)
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to create household"
    [record] = [r for r in caplog.records if r.name == "src.api.endpoints.households"]
    assert record.getMessage().startswith("create household ")
    assert "disk full" in caplog.text           # the traceback is kept
    assert str(_PAYLOAD["settings"]["required_spending"]) not in record.getMessage()


def test_capital_gains_round_trip(client):
    """Gains already realized are saved and read back; a plan without them
    reads back as None."""
    gains = {"tax_year": 2026, "short_term": -2500.0, "long_term": 18000.0,
             "carryover_short_term": 0.0, "carryover_long_term": 4000.0}
    hid = client.post("/households", json={**_PAYLOAD, "capital_gains": gains}).json()[
        "household_id"
    ]
    assert client.get(f"/households/{hid}").json()["capital_gains"] == gains

    plain = client.post("/households", json=_PAYLOAD).json()["household_id"]
    assert client.get(f"/households/{plain}").json()["capital_gains"] is None
