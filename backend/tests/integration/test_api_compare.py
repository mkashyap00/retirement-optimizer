"""Integration tests for POST /compare — two-scenario comparison endpoint.

TDD RED phase — written BEFORE implementation.

Test coverage:
  (1) compare "anytime" vs "pre_rmd" → 200, both results present, deltas are numbers.
  (2) Economic sanity: winning policies differ OR at least one delta is nonzero.
  (3) Unknown household → 404.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app

# ---------------------------------------------------------------------------
# Standard MFJ fixture payload (reused from test_api_optimize.py)
# ---------------------------------------------------------------------------

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


def _create_household(client: TestClient) -> str:
    """POST _MFJ_PAYLOAD and return the household_id."""
    resp = client.post("/households", json=_MFJ_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()["household_id"]


# ---------------------------------------------------------------------------
# (1) POST /compare → 200 with both results and numeric deltas
# ---------------------------------------------------------------------------


def test_compare_returns_200_with_results_and_deltas(client):
    """POST /compare with anytime vs pre_rmd → 200; result_a, result_b, and difference present."""
    hh_id = _create_household(client)

    resp = client.post(
        "/compare",
        json={
            "household_id": hh_id,
            "constraints_a": {"conversion_window": "anytime"},
            "constraints_b": {"conversion_window": "pre_rmd"},
            "monte_carlo_runs": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Both results present
    assert "result_a" in data, "response missing 'result_a'"
    assert "result_b" in data, "response missing 'result_b'"
    assert "difference" in data, "response missing 'difference'"

    result_a = data["result_a"]
    result_b = data["result_b"]
    diff = data["difference"]

    # Each result looks like an optimization result
    assert "winning_policy" in result_a
    assert "yearly_plan" in result_a
    assert "winning_policy" in result_b
    assert "yearly_plan" in result_b

    # Difference has the required fields
    assert "lifetime_taxes_delta" in diff
    assert "terminal_estate_delta" in diff
    assert "success_probability_delta" in diff
    assert "breakeven_year" in diff

    # All deltas are numbers (not None, not str)
    assert isinstance(diff["lifetime_taxes_delta"], (int, float))
    assert isinstance(diff["terminal_estate_delta"], (int, float))
    assert isinstance(diff["success_probability_delta"], (int, float))
    # breakeven_year can be int or None
    assert diff["breakeven_year"] is None or isinstance(diff["breakeven_year"], int)


# ---------------------------------------------------------------------------
# (2) Economic sanity: policies differ OR deltas nonzero
#
# The standard MFJ fixture has enough SS+pension income that anytime vs
# pre_rmd produces identical results (no conversion headroom in low brackets).
# We use an unconstrained scenario A vs max_conversion_per_year=1 (effectively
# blocks conversions since min_conversion=1000) for B, guaranteeing a diff.
# ---------------------------------------------------------------------------

_SINGLE_PAYLOAD: dict = {
    "household": {
        "filing_status": "single",
        "self_birth_date": "1966-01-01",
        "state": "TX",
    },
    "accounts": [
        {
            "account_type": "taxable",
            "owner": "self",
            "balance": 200_000.0,
            "basis": 100_000.0,
        },
        {
            "account_type": "traditional",
            "owner": "self",
            "balance": 1_500_000.0,
        },
    ],
    "income": [],
    "settings": {
        "required_spending": 70_000.0,
        "ss_pia_self": 2_000.0,
        "ss_claim_age_self": 67,
        "ss_pia_spouse": None,
        "ss_claim_age_spouse": None,
    },
    "constraints": {},
}


def test_compare_economic_sanity(client):
    """Unconstrained vs max_conversion_per_year=1 must produce nonzero deltas.

    The 60-year-old single filer with $1.5M traditional and no current income
    has ample conversion headroom, so blocking conversions should materially
    change lifetime taxes and terminal estate.
    """
    resp = client.post("/households", json=_SINGLE_PAYLOAD)
    assert resp.status_code == 201, resp.text
    hh_id = resp.json()["household_id"]

    resp = client.post(
        "/compare",
        json={
            "household_id": hh_id,
            # Scenario A: fully unconstrained
            "constraints_a": {"conversion_window": "anytime"},
            # Scenario B: max_conversion_per_year=1 is below min_conversion=1000
            #             so all conversions are blocked
            "constraints_b": {
                "conversion_window": "anytime",
                "max_conversion_per_year": 1,
            },
            "monte_carlo_runs": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    diff = data["difference"]
    policy_a = data["result_a"]["winning_policy"]["policy_id"]
    policy_b = data["result_b"]["winning_policy"]["policy_id"]

    policies_differ = policy_a != policy_b
    deltas_nonzero = (
        diff["lifetime_taxes_delta"] != 0
        or diff["terminal_estate_delta"] != 0
        or diff["success_probability_delta"] != 0
    )

    assert policies_differ or deltas_nonzero, (
        f"Expected policies to differ or deltas nonzero; "
        f"policy_a={policy_a!r}, policy_b={policy_b!r}, diff={diff}"
    )


# ---------------------------------------------------------------------------
# (3) Per-scenario overrides — spending, claim ages, priority, forced policy
#
# Sensitivity style: each knob is flipped between A and B and the deltas must
# react, guarding against accepted-but-unused override fields.
# ---------------------------------------------------------------------------


def test_compare_spending_override_changes_estate(client):
    """A spends $150k/yr, B spends $60k/yr → A must leave a smaller estate."""
    resp = client.post("/households", json=_SINGLE_PAYLOAD)
    assert resp.status_code == 201, resp.text
    hh_id = resp.json()["household_id"]

    resp = client.post(
        "/compare",
        json={
            "household_id": hh_id,
            "overrides_a": {"required_spending": 150_000},
            "overrides_b": {"required_spending": 60_000},
            "monte_carlo_runs": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    diff = resp.json()["difference"]
    assert diff["terminal_estate_delta"] < 0, (
        f"higher spending must shrink the estate: {diff}"
    )


def test_compare_claim_age_override_changes_outcome(client):
    """Delaying both claim ages to 70 (A) vs stored 67/66 (B) must change the
    numbers — including DEACTIVATING benefits for the self who is already 68.

    Policy is forced to "none" on both sides so the difference is purely the
    Social Security timing, not a different conversion winner.
    """
    hh_id = _create_household(client)

    resp = client.post(
        "/compare",
        json={
            "household_id": hh_id,
            "overrides_a": {
                "ss_claim_age_self": 70,
                "ss_claim_age_spouse": 70,
                "policy_id": "none",
            },
            "overrides_b": {"policy_id": "none"},
            "monte_carlo_runs": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    diff = resp.json()["difference"]
    assert (
        diff["lifetime_taxes_delta"] != 0 or diff["terminal_estate_delta"] != 0
    ), f"claim-age override had no effect: {diff}"


def test_compare_estate_weight_override_is_accepted_and_ignored(client):
    """Older clients still send the retired priority; it must not move the result."""
    hh_id = _create_household(client)

    resp = client.post(
        "/compare",
        json={
            "household_id": hh_id,
            "overrides_a": {"estate_weight": 0},
            "overrides_b": {"estate_weight": 1},
            "monte_carlo_runs": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["result_a"]["winning_policy"] == d["result_b"]["winning_policy"]


def test_compare_forced_policy_per_side(client):
    """policy_id in an override forces that side's reported winner."""
    hh_id = _create_household(client)

    resp = client.post(
        "/compare",
        json={
            "household_id": hh_id,
            "overrides_a": {"policy_id": "none"},
            "overrides_b": {"policy_id": "fill_12_annual"},
            "monte_carlo_runs": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["result_a"]["winning_policy"]["policy_id"] == "none"
    assert data["result_b"]["winning_policy"]["policy_id"] == "fill_12_annual"
    assert data["result_a"]["forced_policy"] == "none"
    assert data["result_b"]["forced_policy"] == "fill_12_annual"


def test_compare_unknown_policy_returns_400(client):
    """An unknown forced policy_id must fail the whole comparison with a 400
    naming the bad id (a half-errored comparison is not renderable)."""
    hh_id = _create_household(client)

    resp = client.post(
        "/compare",
        json={
            "household_id": hh_id,
            "overrides_b": {"policy_id": "fill_99"},
            "monte_carlo_runs": 0,
        },
    )
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"
    assert "fill_99" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# (4) Unknown household → 404
# ---------------------------------------------------------------------------


def test_compare_unknown_household_returns_404(client):
    """POST /compare with unknown household_id → 404."""
    resp = client.post(
        "/compare",
        json={
            "household_id": "00000000-0000-0000-0000-000000000000",
            "constraints_a": {"conversion_window": "anytime"},
            "constraints_b": {"conversion_window": "pre_rmd"},
            "monte_carlo_runs": 10,
        },
    )
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Scenario-level strategy availability and explicit clears
# ---------------------------------------------------------------------------


def test_strategy_availability_follows_the_scenarios_own_constraints(client):
    """The stored plan converts anytime; a scenario that closes the window at
    Medicare (self is 68) leaves nothing to convert. Listing strategies for
    the stored plan offered the scenario choices it could not run."""
    hh = _create_household(client)
    stored = client.get(f"/households/{hh}/policies").json()["policies"]
    assert len(stored) > 1

    resp = client.post(
        f"/households/{hh}/policies",
        json={"constraints": {"conversion_window": "pre_medicare"}, "overrides": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["policies"] == ["none"]


def test_an_explicit_null_clears_a_stored_spending_floor():
    """Omitted means "use the stored value"; an explicit null means "clear
    it". Without the difference a user could not remove a saved floor."""
    from decimal import Decimal as D

    from src.api.endpoints.compare import ScenarioOverridesIn, _apply_overrides
    from src.optimization.state import Settings

    stored = Settings(start_year=2026, required_spending=D("90000"),
                      spending_rule="guardrails", spending_floor=D("60000"))
    inherit = _apply_overrides(stored, ScenarioOverridesIn.model_validate({}))
    cleared = _apply_overrides(
        stored, ScenarioOverridesIn.model_validate({"spending_floor": None})
    )
    assert inherit.spending_floor == D("60000")
    assert cleared.spending_floor is None


def test_a_floor_does_not_apply_when_spending_is_kept_the_same():
    """The page hides the floor under "keep spending the same" but keeps the
    typed value, so it arrives with the fixed rule. It must not be applied:
    a floor prices shortfalls above it at half weight."""
    from decimal import Decimal as D

    from src.api.endpoints.compare import ScenarioOverridesIn, _apply_overrides
    from src.optimization.state import Settings

    fixed = Settings(start_year=2026, required_spending=D("160000"))
    sent = ScenarioOverridesIn.model_validate(
        {"spending_rule": "fixed", "spending_floor": 135000})
    assert _apply_overrides(fixed, sent).spending_floor is None
    cut = ScenarioOverridesIn.model_validate(
        {"spending_rule": "guardrails", "spending_floor": 135000})
    assert _apply_overrides(fixed, cut).spending_floor == D("135000")
    # Switching a stored guardrails plan to fixed drops its floor too.
    stored = Settings(start_year=2026, required_spending=D("160000"),
                      spending_rule="guardrails", spending_floor=D("135000"))
    to_fixed = ScenarioOverridesIn.model_validate({"spending_rule": "fixed"})
    assert _apply_overrides(stored, to_fixed).spending_floor is None
