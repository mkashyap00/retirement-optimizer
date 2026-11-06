"""The stored portfolio's tax lots, and the sell list a run's exports carry.

Shared by the portfolio endpoints (which store the lots), the reports
endpoints and the optimization endpoints (which attach a sell list to a run).
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from src.data.database import DEFAULT_PROFILE_ID, Database
from src.portfolio.lot_selector import select_lots
from src.portfolio.models import TaxLot


def lot_to_dict(lot: TaxLot) -> dict:
    return {
        "ticker": lot.ticker,
        "lot_date": lot.lot_date.isoformat() if lot.lot_date else None,
        "shares": str(lot.shares),
        "cost_basis_per_share": str(lot.cost_basis_per_share),
        "current_price": str(lot.current_price),
        "account_type": lot.account_type,
        "long_term": lot.long_term,
    }


def lot_from_dict(d: dict) -> TaxLot:
    lot_date = date.fromisoformat(d["lot_date"]) if d.get("lot_date") else None
    return TaxLot(
        ticker=d["ticker"],
        lot_date=lot_date,
        shares=Decimal(d["shares"]),
        cost_basis_per_share=Decimal(d["cost_basis_per_share"]),
        current_price=Decimal(d["current_price"]),
        account_type=d["account_type"],
        long_term=d.get("long_term"),
    )


def run_sale_plans(db: Database, result: dict, as_of: date) -> dict | None:
    """Build the sell list for the FIRST taxable-withdrawal year, or None.

    This is an annual-cadence tool: every year is priced against the
    **uploaded holdings at their uploaded prices**, so future years would show
    a nearly identical sell list, and the user re-runs the plan next year with
    a fresh portfolio. Only the first year that actually draws on the taxable
    account is actionable, so that is the one year the export carries.

    ``as_of`` in the output is the date the prices are from -- the upload, not
    this export; ``generated_on`` is *as_of* the argument, which also dates
    holding periods. Each year keeps what the selector found: the cash it
    actually raised, any amount the holdings could not cover, and its warnings.
    """
    row = db.fetch_one(
        "SELECT lots_json, warnings_json, uploaded_at FROM profile_portfolios "
        "WHERE profile_id = ?",
        [DEFAULT_PROFILE_ID],
    )
    if row is None:
        return None

    lots = [lot_from_dict(d) for d in json.loads(row[0])]
    ingest_warnings: list[str] = json.loads(row[1]) if row[1] else []
    uploaded = row[2]
    prices_as_of = uploaded.date() if hasattr(uploaded, "date") else as_of
    years: list[dict] = []
    for r in result.get("yearly_plan", []):
        withdrawal = r.get("withdrawal_taxable", 0) or 0
        if withdrawal <= 0:
            continue
        plan = select_lots(lots, Decimal(str(withdrawal)), as_of=as_of)
        years.append(
            {
                "year": r.get("year"),
                "target_cash": float(withdrawal),
                "cash_raised": float(plan.cash_raised),
                "cash_short": max(0.0, float(withdrawal) - float(plan.cash_raised)),
                "warnings": ingest_warnings + plan.warnings,
                "sold": [
                    {
                        "ticker": s.lot.ticker,
                        "holding_period": s.lot.holding_period(as_of),
                        "shares_sold": float(s.shares_sold),
                        "proceeds": float(s.proceeds),
                        "realized_gain": float(s.realized_gain),
                    }
                    for s in plan.sold
                ],
            }
        )
        break  # only the first (actionable) withdrawal year — re-run yearly

    if not years:
        return None
    return {
        "as_of": prices_as_of.isoformat(),
        "generated_on": as_of.isoformat(),
        "years": years,
    }
