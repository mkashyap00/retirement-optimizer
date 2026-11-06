"""Deleting a household removes every row that references it, or none.

DuckDB cannot delete a parent row in the same transaction that deleted its
children (its foreign-key check still sees them), so deletion is two steps:
every child table in one transaction, then the household. These pin that a
legacy per-household portfolio no longer blocks the second step after the
first has committed, and that a failure inside the first leaves nothing
half-deleted.
"""
import re

import pytest
from fastapi import HTTPException
from src.api.endpoints.households import create_household, delete_household
from src.api.models import HouseholdPayload
from src.data.database import DEFAULT_PROFILE_ID, Database

_CHILD_TABLES = ("accounts", "income_sources", "settings", "runs", "portfolios")


def _payload():
    return HouseholdPayload(**{
        "household": {"filing_status": "single", "self_birth_date": "1960-01-01",
                      "state": "CA"},
        "accounts": [{"account_type": "taxable", "owner": "self",
                      "balance": "100000", "basis": "100000"}],
        "income": [{"category": "pension", "owner": "self", "amount": "10000"}],
        "settings": {"required_spending": "50000", "ss_pia_self": "0"},
    })


@pytest.fixture
def db_with_legacy_portfolio():
    db = Database(":memory:")
    db.connect()
    hid = create_household(_payload(), db)["household_id"]
    # A portfolio uploaded before profiles existed: still in the legacy
    # table, still pointing at the household.
    db.execute(
        "INSERT INTO portfolios (household_id, lots_json, warnings_json) "
        "VALUES (?, '[{\"t\":1}]', '[]')",
        [hid],
    )
    db.execute(
        "INSERT INTO profile_portfolios (profile_id, lots_json, warnings_json) "
        "VALUES (?, '[{\"t\":1}]', '[]')",
        [DEFAULT_PROFILE_ID],
    )
    yield db, hid
    db.close()


def _counts(db, hid):
    rows = {t: db.fetch_one(f"SELECT count(*) FROM {t} WHERE household_id = ?", [hid])[0]
            for t in _CHILD_TABLES}
    rows["households"] = db.fetch_one(
        "SELECT count(*) FROM households WHERE id = ?", [hid])[0]
    return rows


def test_a_household_with_a_legacy_portfolio_is_deleted_whole(db_with_legacy_portfolio):
    db, hid = db_with_legacy_portfolio
    resp = delete_household(hid, db)
    assert resp.status_code == 204
    assert all(n == 0 for n in _counts(db, hid).values()), _counts(db, hid)
    # The app-level portfolio the user actually uses is untouched.
    assert db.fetch_one("SELECT count(*) FROM profile_portfolios")[0] == 1


class _FailOn(Database):
    """A database whose execute() fails on one statement, like a crash would."""

    def __init__(self, inner, table):
        self.__dict__.update(inner.__dict__)
        self._pattern = re.compile(rf'DELETE FROM "?{table}"?\b')

    def execute(self, sql, params=None):
        if self._pattern.search(sql):
            raise RuntimeError("injected failure")
        return super().execute(sql, params)


def test_a_failure_part_way_through_deletes_nothing(db_with_legacy_portfolio):
    db, hid = db_with_legacy_portfolio
    before = _counts(db, hid)
    with pytest.raises(HTTPException) as exc:
        delete_household(hid, _FailOn(db, "settings"))
    assert exc.value.status_code == 500
    assert _counts(db, hid) == before
