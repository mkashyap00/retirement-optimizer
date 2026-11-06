"""A household as stored, in the same nested shape the API accepts.

Read by ``GET /households/{id}`` and by the optimization endpoints, which save
this snapshot with each run so its results always show the inputs it used.
"""
from __future__ import annotations

import json

from src.data.database import Database


def household_snapshot(db: Database, household_id: str) -> dict | None:
    """The full nested payload for *household_id*, or None if it does not exist."""
    hh = db.fetch_one(
        "SELECT id, filing_status, self_birth_date, spouse_birth_date, state, nickname, "
        "self_death_age, spouse_death_age "
        "FROM households WHERE id = ?",
        [household_id],
    )
    if hh is None:
        return None

    acc_rows = db.fetch_all(
        "SELECT account_type, owner, balance, basis, roth_opened_year "
        "FROM accounts WHERE household_id = ?",
        [household_id],
    )
    accounts = [
        {
            "account_type": r[0],
            "owner": r[1],
            "balance": float(r[2]),
            "basis": float(r[3]) if r[3] is not None else None,
            "roth_opened_year": r[4],
        }
        for r in acc_rows
    ]

    inc_rows = db.fetch_all(
        "SELECT category, owner, amount, start_year, end_year "
        "FROM income_sources WHERE household_id = ?",
        [household_id],
    )
    income = [
        {
            "category": r[0],
            "owner": r[1],
            "amount": float(r[2]),
            "start_year": r[3],
            "end_year": r[4],
        }
        for r in inc_rows
    ]

    sett = db.fetch_one(
        "SELECT required_spending, inflation, nominal_return, "
        "ss_pia_self, ss_claim_age_self, ss_pia_spouse, ss_claim_age_spouse, "
        "heir_tax_rate, estate_weight, spending_rule, spending_floor, "
        "constraints_json, ss_cola, ss_receiving_self, ss_receiving_spouse, "
        "capital_gains_json "
        "FROM settings WHERE household_id = ?",
        [household_id],
    )
    settings: dict = {}
    constraints: dict = {}
    capital_gains: dict | None = None
    if sett is not None:
        settings = {
            "required_spending": float(sett[0]),
            "inflation": float(sett[1]),
            "nominal_return": float(sett[2]),
            "ss_pia_self": float(sett[3]),
            "ss_claim_age_self": sett[4],
            "ss_pia_spouse": float(sett[5]) if sett[5] is not None else None,
            "ss_claim_age_spouse": sett[6],
            "heir_tax_rate": float(sett[7]) if sett[7] is not None else None,
            "estate_weight": float(sett[8]) if sett[8] is not None else None,
            "spending_rule": sett[9],
            "spending_floor": float(sett[10]) if sett[10] is not None else None,
            "ss_cola": float(sett[12]) if sett[12] is not None else None,
            "ss_receiving_self": sett[13],
            "ss_receiving_spouse": sett[14],
        }
        constraints = json.loads(sett[11]) if sett[11] else {}
        if sett[15]:
            # Decimals round-trip as strings in the stored JSON; the API's
            # money is floats everywhere else.
            capital_gains = {
                k: (v if k == "tax_year" else float(v))
                for k, v in json.loads(sett[15]).items()
            }

    return {
        "household_id": str(hh[0]),
        "household": {
            "filing_status": hh[1],
            "self_birth_date": str(hh[2]),
            "spouse_birth_date": str(hh[3]) if hh[3] is not None else None,
            "state": hh[4],
            "nickname": hh[5],
            "self_death_age": hh[6],
            "spouse_death_age": hh[7],
        },
        "accounts": accounts,
        "income": income,
        "settings": settings,
        "constraints": constraints,
        "capital_gains": capital_gains,
    }
