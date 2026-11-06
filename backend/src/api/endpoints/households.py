"""Household CRUD router.

Decimals are stored and returned as floats (not strings).
All timestamps come from datetime.now() in Python; UUIDs from uuid.uuid4().
FK constraints exist in the schema but DuckDB does not enforce them at runtime,
so cascade is implemented via explicit DELETEs in dependency order.
All multi-INSERT operations are wrapped in explicit BEGIN/COMMIT/ROLLBACK
transactions so a mid-sequence failure cannot leave orphaned rows.
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response

from src.api.dependencies import get_db
from src.api.models import HouseholdPayload
from src.api.snapshot import household_snapshot
from src.data.database import Database

# Failures log the operation, household id and traceback -- never the payload,
# which holds the household's financial inputs.
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/households", tags=["households"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_children(db: Database, hh_id: str, payload: HouseholdPayload, now: datetime) -> None:
    """Insert accounts, income_sources, and settings for *hh_id*.

    Called inside an already-open transaction — the caller is responsible for
    COMMIT/ROLLBACK.
    """
    for account in payload.accounts:
        db.execute(
            "INSERT INTO accounts "
            "(id, household_id, account_type, owner, balance, basis, roth_opened_year, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                str(uuid.uuid4()),
                hh_id,
                account.account_type,
                account.owner,
                float(account.balance),
                float(account.basis) if account.basis is not None else None,
                account.roth_opened_year,
                now,
            ],
        )

    for income in payload.income:
        db.execute(
            "INSERT INTO income_sources "
            "(id, household_id, category, owner, amount, start_year, end_year) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                str(uuid.uuid4()),
                hh_id,
                income.category,
                income.owner,
                float(income.amount),
                income.start_year,
                income.end_year,
            ],
        )

    s = payload.settings
    db.execute(
        "INSERT INTO settings "
        "(household_id, required_spending, inflation, nominal_return, "
        "ss_pia_self, ss_claim_age_self, ss_pia_spouse, ss_claim_age_spouse, "
        "heir_tax_rate, estate_weight, spending_rule, spending_floor, "
        "constraints_json, ss_cola, ss_receiving_self, ss_receiving_spouse, "
        "capital_gains_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            hh_id,
            float(s.required_spending),
            float(s.inflation),
            float(s.nominal_return),
            float(s.ss_pia_self),
            s.ss_claim_age_self,
            float(s.ss_pia_spouse) if s.ss_pia_spouse is not None else None,
            s.ss_claim_age_spouse,
            float(s.heir_tax_rate) if s.heir_tax_rate is not None else None,
            float(s.estate_weight) if s.estate_weight is not None else None,
            s.spending_rule,
            float(s.spending_floor) if s.spending_floor is not None else None,
            payload.constraints.model_dump_json(),
            float(s.ss_cola) if s.ss_cola is not None else None,
            s.ss_receiving_self,
            s.ss_receiving_spouse,
            payload.capital_gains.model_dump_json() if payload.capital_gains else None,
        ],
    )


# ---------------------------------------------------------------------------
# POST /households
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
def create_household(payload: HouseholdPayload, db: Database = Depends(get_db)) -> dict:
    """Insert household + accounts + income_sources + settings. Returns household_id."""
    hh_id = str(uuid.uuid4())
    now = datetime.now()

    try:
        db.execute("BEGIN TRANSACTION")

        db.execute(
            "INSERT INTO households "
            "(id, filing_status, self_birth_date, spouse_birth_date, state, "
            "nickname, self_death_age, spouse_death_age, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                hh_id,
                payload.household.filing_status,
                str(payload.household.self_birth_date),
                str(payload.household.spouse_birth_date)
                if payload.household.spouse_birth_date is not None
                else None,
                payload.household.state,
                payload.household.nickname,
                payload.household.self_death_age,
                payload.household.spouse_death_age,
                now,
                now,
            ],
        )

        _insert_children(db, hh_id, payload, now)

        db.execute("COMMIT")
    except Exception as exc:
        db.execute("ROLLBACK")
        logger.exception("create household %s failed", hh_id)
        raise HTTPException(status_code=500, detail="Failed to create household") from exc

    return {"household_id": hh_id}


# ---------------------------------------------------------------------------
# GET /households
# ---------------------------------------------------------------------------


@router.get("")
def list_households(db: Database = Depends(get_db)) -> list[dict]:
    """Return lightweight summary of every household."""
    rows = db.fetch_all(
        "SELECT id, filing_status, state, created_at, nickname "
        "FROM households ORDER BY created_at DESC"
    )
    return [
        {
            "household_id": str(row[0]),
            "filing_status": row[1],
            "state": row[2],
            "created_at": str(row[3]),
            "nickname": row[4],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# GET /households/{household_id}
# ---------------------------------------------------------------------------


@router.get("/{household_id}")
def get_household(household_id: str, db: Database = Depends(get_db)) -> dict:
    """Return the full nested payload for a household."""
    snapshot = household_snapshot(db, household_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return snapshot


# ---------------------------------------------------------------------------
# PUT /households/{household_id}
# ---------------------------------------------------------------------------


@router.put("/{household_id}")
def update_household(
    household_id: str, payload: HouseholdPayload, db: Database = Depends(get_db)
) -> dict:
    """Transactional replace: update household row, delete + re-insert child rows.

    Runs are intentionally KEPT: each run snapshots the inputs that produced
    it (see optimization.py), so past results remain a valid historical
    record even after the household is edited.

    Returns 200 ``{"household_id": id}`` or 404 if the id does not exist.
    """
    hh = db.fetch_one("SELECT id FROM households WHERE id = ?", [household_id])
    if hh is None:
        raise HTTPException(status_code=404, detail="Household not found")

    now = datetime.now()

    try:
        db.execute("BEGIN TRANSACTION")

        # Delete child rows (dependency order) — but NOT runs (see docstring)
        db.execute("DELETE FROM settings WHERE household_id = ?", [household_id])
        db.execute("DELETE FROM income_sources WHERE household_id = ?", [household_id])
        db.execute("DELETE FROM accounts WHERE household_id = ?", [household_id])

        # Update the household row itself
        db.execute(
            "UPDATE households "
            "SET filing_status=?, self_birth_date=?, spouse_birth_date=?, "
            "state=?, nickname=?, self_death_age=?, spouse_death_age=?, updated_at=? "
            "WHERE id=?",
            [
                payload.household.filing_status,
                str(payload.household.self_birth_date),
                str(payload.household.spouse_birth_date)
                if payload.household.spouse_birth_date is not None
                else None,
                payload.household.state,
                payload.household.nickname,
                payload.household.self_death_age,
                payload.household.spouse_death_age,
                now,
                household_id,
            ],
        )

        # Re-insert children
        _insert_children(db, household_id, payload, now)

        db.execute("COMMIT")
    except Exception as exc:
        db.execute("ROLLBACK")
        logger.exception("update household %s failed", household_id)
        raise HTTPException(status_code=500, detail="Failed to update household") from exc

    return {"household_id": household_id}


# ---------------------------------------------------------------------------
# DELETE /households/{household_id}
# ---------------------------------------------------------------------------


@router.delete("/{household_id}", status_code=204)
def delete_household(
    household_id: str, db: Database = Depends(get_db)
) -> Response:
    """Delete a household and all child rows. Returns 204 or 404."""
    hh = db.fetch_one("SELECT id FROM households WHERE id = ?", [household_id])
    if hh is None:
        raise HTTPException(status_code=404, detail="Household not found")

    # Child rows first: DuckDB has no FK cascade. Every referencing table is
    # read from the catalogue, so none can be missed -- a hard-coded list left
    # out the legacy `portfolios` table, and the household delete then failed
    # AFTER its accounts and settings were gone. (The legacy row was copied to
    # the profile store on migration and is never read; the profile's own
    # portfolio is untouched.)
    children = db.fetch_all(
        "SELECT table_name, constraint_column_names[1] FROM duckdb_constraints() "
        "WHERE constraint_type = 'FOREIGN KEY' AND referenced_table = 'households'"
    )
    # All children in one transaction, so a failure deletes nothing. The
    # household itself cannot join it: DuckDB's FK check still sees children
    # deleted earlier in the same transaction and refuses. Once they are
    # committed nothing references it, so that second step cannot fail on a
    # constraint.
    db.execute("BEGIN")
    try:
        for table, column in children:
            db.execute(f'DELETE FROM "{table}" WHERE "{column}" = ?', [household_id])
        db.execute("COMMIT")
    except Exception as exc:
        db.execute("ROLLBACK")
        logger.exception("delete household %s failed", household_id)
        raise HTTPException(status_code=500, detail="Failed to delete household") from exc
    db.execute("DELETE FROM households WHERE id = ?", [household_id])

    return Response(status_code=204)
