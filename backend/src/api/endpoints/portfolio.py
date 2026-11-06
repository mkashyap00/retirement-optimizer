"""Portfolio tax-lot API endpoints.

The portfolio is keyed to the app-level **default profile**, not a household,
so one uploaded snapshot serves every plan and run (see
``DEFAULT_PROFILE_ID``). Reconciliation against a specific plan's Accounts
figures is optional — pass ``household_id`` on upload to enable it.

Routes
------
``POST /portfolio``
    Upload a CSV of tax lots to the default profile. Optional query param
    ``household_id`` reconciles the upload against that plan's balances/basis.

``GET /portfolio/sale-plan``
    Load the stored portfolio and run the loss-first/HIFO lot selector.
    Query param: ``target_cash`` (float, required).

``GET /portfolio/sale-plan.csv`` / ``.pdf``
    The same sell list as a dated, downloadable export (a point-in-time
    execution aid — prices are as of today). Query params: ``target_cash``
    (required), plus optional ``spend``, ``convtax``, ``year`` for context.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from src.api.dependencies import get_db
from src.api.sale_plans import lot_from_dict, lot_to_dict
from src.data.database import DEFAULT_PROFILE_ID, Database
from src.portfolio.ingest import ingest_csv
from src.portfolio.lot_selector import select_lots
from src.portfolio.models import TaxLot
from src.reports.sale_plan_export import build_sale_plan_csv, build_sale_plan_pdf

router = APIRouter(tags=["portfolio"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PortfolioUploadRequest(BaseModel):
    csv: str


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


# Reconciliation: uploaded totals vs the plan's stored account balances.
# Beyond this fraction apart, warn — stale prices are the usual culprit.
_RECON_TOLERANCE = Decimal("0.05")


def _reconciliation_warnings(
    db: Database, household_id: str, lots: list[TaxLot]
) -> list[str]:
    """Compare uploaded positions to the plan's Accounts-screen figures.

    Two checks: market value per account type against plan *balances*, and
    the uploaded taxable cost basis against the plan's taxable *cost basis*
    (the aggregate the Accounts wizard collects).
    """
    rows = db.fetch_all(
        "SELECT account_type, SUM(balance), SUM(basis) FROM accounts "
        "WHERE household_id = ? GROUP BY account_type",
        [household_id],
    )
    plan_balances = {r[0]: Decimal(str(r[1])) for r in rows}
    plan_basis = {
        r[0]: Decimal(str(r[2])) for r in rows if r[2] is not None
    }

    uploaded_value: dict[str, Decimal] = {}
    uploaded_basis: dict[str, Decimal] = {}
    for lot in lots:
        uploaded_value[lot.account_type] = (
            uploaded_value.get(lot.account_type, Decimal("0")) + lot.market_value
        )
        uploaded_basis[lot.account_type] = (
            uploaded_basis.get(lot.account_type, Decimal("0")) + lot.total_cost_basis
        )

    warnings: list[str] = []
    for acct, uploaded in sorted(uploaded_value.items()):
        plan = plan_balances.get(acct)
        if plan is None or plan == 0:
            continue
        if abs(uploaded - plan) / plan > _RECON_TOLERANCE:
            warnings.append(
                f"Uploaded {acct} positions total ${uploaded:,.0f} but the plan's "
                f"{acct} balance is ${plan:,.0f}. Prices change daily — re-export "
                "your positions with current prices, or update the plan's balances."
            )

    # Cost-basis reconciliation (taxable only — basis drives gain estimates).
    uploaded_tax_basis = uploaded_basis.get("taxable")
    plan_tax_basis = plan_basis.get("taxable")
    if (
        uploaded_tax_basis is not None
        and plan_tax_basis is not None
        and plan_tax_basis != 0
        and abs(uploaded_tax_basis - plan_tax_basis) / plan_tax_basis > _RECON_TOLERANCE
    ):
        warnings.append(
            f"Uploaded taxable cost basis totals ${uploaded_tax_basis:,.0f} but the "
            f"plan's taxable cost basis is ${plan_tax_basis:,.0f}. Check that the "
            "positions and the Accounts screen describe the same holdings."
        )
    return warnings


# ---------------------------------------------------------------------------
# POST /portfolio
# ---------------------------------------------------------------------------


@router.post("/portfolio")
def upload_portfolio(
    body: PortfolioUploadRequest,
    household_id: str | None = Query(
        None, description="Optional plan to reconcile the upload against"
    ),
    db: Database = Depends(get_db),
) -> dict:
    """Parse a CSV of tax lots and store it for the default profile.

    When *household_id* is supplied (e.g. arriving from a plan's results
    page), the upload is reconciled against that plan's Accounts figures.

    Returns ``{"lots": <count>, "warnings": [...]}``.

    Raises:
        404: A supplied *household_id* does not exist.
        400: CSV parse error (ValueError from ingest_csv).
    """
    try:
        lots, warnings = ingest_csv(body.csv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if household_id is not None:
        hh = db.fetch_one("SELECT id FROM households WHERE id = ?", [household_id])
        if hh is None:
            raise HTTPException(status_code=404, detail="Household not found")
        warnings = warnings + _reconciliation_warnings(db, household_id, lots)

    lots_json = json.dumps([lot_to_dict(lot) for lot in lots])
    warnings_json = json.dumps(warnings)
    now = datetime.now()

    db.execute(
        """
        INSERT INTO profile_portfolios (profile_id, uploaded_at, lots_json, warnings_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (profile_id) DO UPDATE
            SET uploaded_at   = excluded.uploaded_at,
                lots_json     = excluded.lots_json,
                warnings_json = excluded.warnings_json
        """,
        [DEFAULT_PROFILE_ID, now, lots_json, warnings_json],
    )

    return {"lots": len(lots), "warnings": warnings}


# ---------------------------------------------------------------------------
# GET /portfolio  — stored holdings summary (for the holdings-only tab)
# ---------------------------------------------------------------------------


@router.get("/portfolio")
def get_portfolio(db: Database = Depends(get_db)) -> dict:
    """Return the default profile's stored holdings, or an empty summary.

    Returns ``{"positions": [...], "uploaded_at": <iso|null>, "warnings": [...]}``.
    """
    row = db.fetch_one(
        "SELECT lots_json, warnings_json, uploaded_at "
        "FROM profile_portfolios WHERE profile_id = ?",
        [DEFAULT_PROFILE_ID],
    )
    if row is None:
        return {"positions": [], "uploaded_at": None, "warnings": []}

    lots_data, warnings_data, uploaded_at = row
    lots = [lot_from_dict(d) for d in json.loads(lots_data)]
    today = date.today()
    positions = [
        {
            "ticker": lot.ticker,
            "account_type": lot.account_type,
            "shares": float(lot.shares),
            "price": float(lot.current_price),
            "market_value": float(lot.market_value),
            "cost_basis": float(lot.total_cost_basis),
            "holding_period": lot.holding_period(today),
        }
        for lot in lots
    ]
    return {
        "positions": positions,
        "uploaded_at": (
            uploaded_at.isoformat()
            if hasattr(uploaded_at, "isoformat")
            else str(uploaded_at)
        ),
        "warnings": json.loads(warnings_data),
    }


# ---------------------------------------------------------------------------
# Sale-plan computation (shared by the JSON endpoint and the CSV/PDF exports)
# ---------------------------------------------------------------------------


def _compute_sale_plan(db: Database, target_cash: float, as_of: date) -> dict:
    """Load the default profile's portfolio and run the lot selector.

    Returns the plan as a JSON-serialisable dict. Raises 404 if no portfolio
    has been uploaded yet.
    """
    row = db.fetch_one(
        "SELECT lots_json, warnings_json FROM profile_portfolios WHERE profile_id = ?",
        [DEFAULT_PROFILE_ID],
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No portfolio uploaded yet",
        )

    lots_data, warnings_data = row
    lots = [lot_from_dict(d) for d in json.loads(lots_data)]
    ingest_warnings: list[str] = json.loads(warnings_data)

    plan = select_lots(lots, Decimal(str(target_cash)), as_of=as_of)

    # Merge ingest warnings into the plan warnings (ingest warnings first)
    all_warnings = ingest_warnings + plan.warnings

    sold_items = [
        {
            "ticker": s.lot.ticker,
            "account_type": s.lot.account_type,
            "lot_date": s.lot.lot_date.isoformat() if s.lot.lot_date else None,
            "holding_period": s.lot.holding_period(as_of),
            "shares_sold": float(s.shares_sold),
            "proceeds": float(s.proceeds),
            "realized_gain": float(s.realized_gain),
        }
        for s in plan.sold
    ]

    return {
        "profile_id": DEFAULT_PROFILE_ID,
        "target_cash": target_cash,
        "cash_raised": float(plan.cash_raised),
        "realized_lt_gain": float(plan.realized_lt_gain),
        "realized_st_gain": float(plan.realized_st_gain),
        "sold": sold_items,
        "warnings": all_warnings,
    }


# ---------------------------------------------------------------------------
# GET /portfolio/sale-plan
# ---------------------------------------------------------------------------


@router.get("/portfolio/sale-plan")
def get_sale_plan(
    target_cash: float = Query(..., description="Cash proceeds required in dollars"),
    db: Database = Depends(get_db),
) -> dict:
    """Run the lot-selection algorithm for the default profile and return JSON.

    Raises:
        404: No portfolio uploaded yet.
    """
    return _compute_sale_plan(db, target_cash, as_of=date.today())


# ---------------------------------------------------------------------------
# GET /portfolio/sale-plan.csv  and  .pdf  (dated exports)
# ---------------------------------------------------------------------------


@router.get("/portfolio/sale-plan.csv")
def export_sale_plan_csv(
    target_cash: float = Query(..., description="Cash proceeds required in dollars"),
    spend: float | None = Query(None, description="Portion funding spending"),
    convtax: float | None = Query(None, description="Portion funding conversion tax"),
    year: int | None = Query(None, description="Plan year this sale funds"),
    db: Database = Depends(get_db),
) -> Response:
    """Dated CSV of the sell list — a point-in-time execution aid."""
    as_of = date.today()
    plan = _compute_sale_plan(db, target_cash, as_of=as_of)
    csv_bytes = build_sale_plan_csv(
        plan, as_of=as_of, spend=spend, convtax=convtax, year=year
    )
    fname = f"sale-plan-{as_of.isoformat()}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/portfolio/sale-plan.pdf")
def export_sale_plan_pdf(
    target_cash: float = Query(..., description="Cash proceeds required in dollars"),
    spend: float | None = Query(None, description="Portion funding spending"),
    convtax: float | None = Query(None, description="Portion funding conversion tax"),
    year: int | None = Query(None, description="Plan year this sale funds"),
    db: Database = Depends(get_db),
) -> Response:
    """Dated PDF of the sell list — a point-in-time execution aid."""
    as_of = date.today()
    plan = _compute_sale_plan(db, target_cash, as_of=as_of)
    pdf_bytes = build_sale_plan_pdf(
        plan, as_of=as_of, spend=spend, convtax=convtax, year=year
    )
    fname = f"sale-plan-{as_of.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
