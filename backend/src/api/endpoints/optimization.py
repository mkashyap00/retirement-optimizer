"""Optimization endpoints.

Routes:
  POST  /optimize                     → run optimizer, persist result, return {run_id, result}
  POST  /optimize/jobs                → start a background joint claim-age search → 202 {job_id}
  GET   /optimize/jobs/active         → the queued/running job, or null
  GET   /optimize/jobs/{job_id}       → status, phase, progress, run_id, error
  GET   /runs/{run_id}                → retrieve a stored run by id
  GET   /households/{id}/runs         → list run summaries for a household (newest first)

Engine Construction
-------------------
Tax/benefit engines are constructed once at module load time and shared across
all requests.  :class:`~src.data.tax_rules.rules.TaxRules` is effectively
stateless after construction (its ``_warned_*`` deduplication sets only affect
log verbosity, not correctness), so module-level sharing is safe.  Avoiding
per-request construction saves ~50 ms of data-parsing overhead per call.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.assemble import build_optimizer_inputs, claim_preview_inputs
from src.api.dependencies import get_db
from src.api.jobs import JobBusyError, JobRegistry
from src.api.models import ClaimPreviewIn, OptimizeJobRequest, OptimizeRequest
from src.api.sale_plans import run_sale_plans
from src.api.snapshot import household_snapshot
from src.data.database import Database
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.claiming import (
    AgeControl,
    ClaimControls,
    ClaimInputError,
    check_pinned_ages,
    claim_age_preview,
    enumerate_scenarios,
    require_claim_ages,
    with_claim_ages,
)
from src.optimization.joint import JointSearchParams, run_joint_optimization
from src.optimization.optimizer import run_optimization
from src.optimization.search import search
from src.optimization.state import Engines
from src.reports.storage import save_run_reports

logger = logging.getLogger(__name__)

router = APIRouter(tags=["optimization"])

# ---------------------------------------------------------------------------
# Module-level engines — constructed once, shared across all requests.
# ---------------------------------------------------------------------------

_rules = TaxRules()
_ENGINES = Engines(
    federal=FederalTaxEngine(_rules),
    state=StateTaxEngine(_rules),
    irmaa=IRMAACalculator(_rules),
    rmd=RMDCalculator(_rules),
    ss=SocialSecurityCalculator(),
    rules=_rules,
)


def _today() -> date:
    """Return today's date. Tests can monkeypatch this for deterministic behavior."""
    return date.today()


def _capture_inputs(db: Database, household_id: str, today: date):
    """Optimizer inputs and the household snapshot, read in ONE transaction.

    Both run several queries; reading them separately let an edit landing in
    between persist a snapshot that is not what the run used. Returns
    ``(state, settings, constraints, snapshot)``; 404 if the household is gone.
    """
    db.execute("BEGIN TRANSACTION")
    try:
        state, settings, constraints = build_optimizer_inputs(db, household_id, today=today)
        snapshot = household_snapshot(db, household_id)
        if snapshot is None:
            raise KeyError(f"household {household_id} not found")
    except KeyError as exc:
        db.execute("ROLLBACK")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BaseException:
        db.execute("ROLLBACK")
        raise
    db.execute("COMMIT")
    return state, settings, constraints, snapshot


def _persist_run(db: Database, household_id: str, result: dict, request: dict,
                 inputs_snapshot: dict) -> str:
    """Insert the ``runs`` row and auto-save its reports; returns the run id."""
    run_id = str(uuid.uuid4())
    now = datetime.now()
    # key must match run_optimization's output contract (optimizer.py)
    duration_ms = int(result.get("computation_time_seconds", 0.0) * 1000)

    db.execute(
        "INSERT INTO runs "
        "(id, household_id, created_at, duration_ms, request_json, result_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            run_id,
            household_id,
            now,
            duration_ms,
            json.dumps({**request, "inputs": inputs_snapshot}, default=float),
            json.dumps(result, default=float),
        ],
    )

    # Auto-save CSV/PDF/XLSX to reports/ so the files exist as soon as the
    # results are shown (issue #7).  Failures here must never fail the run —
    # the result is already persisted; file copies are a convenience.
    try:
        # Round-trip through JSON so the report modules see the same
        # float-only payload the export endpoints would read back from the DB.
        result_for_reports = json.loads(json.dumps(result, default=float))
        # Same sale plan the download endpoints attach, so the auto-saved
        # files match what the user gets by clicking CSV/Excel/PDF.
        sale_plans = run_sale_plans(db, result_for_reports, _today())
        save_run_reports(
            now,
            result_for_reports,
            inputs_snapshot,
            sale_plans=sale_plans,
            run_id=run_id,
            household_id=household_id,
        )
    except Exception:
        logger.exception("report auto-save failed for run %s", run_id)
    return run_id


# ---------------------------------------------------------------------------
# POST /optimize
# ---------------------------------------------------------------------------


@router.post("/optimize", status_code=200)
def optimize(payload: OptimizeRequest, db: Database = Depends(get_db)) -> dict:
    """Run the optimization pipeline for a stored household and persist the run.

    Assembles optimizer inputs from the database, executes the full pipeline
    (rule search + Monte Carlo scoring), stores the run in the ``runs``
    table, and returns the result.

    Returns 200 ``{"run_id": ..., "result": ...}`` or 404 if the household
    does not exist.
    """
    state, settings, constraints, inputs_snapshot = _capture_inputs(
        db, payload.household_id, _today()
    )

    pinned_ages = (payload.ss_claim_age_self, payload.ss_claim_age_spouse)
    if pinned_ages != (None, None):
        check_pinned_ages(state, settings, *pinned_ages)
        state, settings = with_claim_ages(state, settings, _ENGINES, *pinned_ages)

    result = run_optimization(
        state,
        _ENGINES,
        settings,
        constraints,
        monte_carlo_runs=payload.monte_carlo_runs,
        forced_policy=payload.policy_id,
    )
    # Echoed so the result says it ran at requested ages, not the stored ones.
    result["pinned_claim_ages"] = (
        {"self": pinned_ages[0], "spouse": pinned_ages[1]}
        if pinned_ages != (None, None) else None
    )

    # The run carries its own copy of the inputs: the household can be edited
    # later, and the results page / exports must show the run's inputs.
    run_id = _persist_run(db, payload.household_id, result, {
        "household_id": payload.household_id,
        "monte_carlo_runs": payload.monte_carlo_runs,
        "policy_id": payload.policy_id,
        "ss_claim_age_self": payload.ss_claim_age_self,
        "ss_claim_age_spouse": payload.ss_claim_age_spouse,
    }, inputs_snapshot)
    return {"run_id": run_id, "result": result}


# ---------------------------------------------------------------------------
# Background joint search: POST /optimize/jobs, GET /optimize/jobs/...
# ---------------------------------------------------------------------------


@router.post("/claim-ages/preview")
def preview_claim_ages(payload: ClaimPreviewIn) -> dict:
    """Per person, what a claim-age search would try for an UNSAVED plan:
    eligible ages, skipped ages with reasons, or why the age is fixed. The
    same rules the search applies (``claiming.claim_age_preview``)."""
    state, settings = claim_preview_inputs(payload, _today())
    return claim_age_preview(state, settings)


@router.get("/households/{household_id}/claim-ages")
def household_claim_ages(household_id: str, db: Database = Depends(get_db)) -> dict:
    """The same preview for a saved plan, read the way a run reads it. Stored
    inputs a run would refuse come back as ``{"error": ...}``, not a 422, so
    the setup can say what to fix."""
    try:
        state, settings, _ = build_optimizer_inputs(db, household_id, today=_today())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClaimInputError as exc:
        return {"error": str(exc)}
    return claim_age_preview(state, settings)


def _jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs


@router.post("/optimize/jobs", status_code=202)
def submit_optimize_job(
    payload: OptimizeJobRequest, request: Request, db: Database = Depends(get_db)
) -> dict:
    """Start a joint claim-age + conversion search in the background.

    Inputs are captured and validated HERE, in the request: a missing
    household is a 404, contradictory or unsearchable claim inputs and a grid
    with no eligible pair are 422, and a job already running is 409 -- none
    of them wait for the worker. Returns 202 ``{job_id, status}``; poll
    ``GET /optimize/jobs/{job_id}`` for the run id.
    """
    jobs = _jobs(request)
    busy = jobs.active()
    if busy is not None:
        raise HTTPException(status_code=409,
                            detail={"message": "An optimization is already running.",
                                    "job_id": busy["id"]})

    today = _today()
    state, settings, constraints, inputs_snapshot = _capture_inputs(
        db, payload.household_id, today
    )
    cs = payload.claim_search
    controls = ClaimControls(AgeControl(cs.self_.mode, cs.self_.age),
                             AgeControl(cs.spouse.mode, cs.spouse.age))
    check_pinned_ages(
        state, settings,
        cs.self_.age if cs.self_.mode == "fixed" else None,
        cs.spouse.age if cs.spouse.mode == "fixed" else None,
    )
    scenarios, exclusions = enumerate_scenarios(state, settings, _ENGINES, controls)
    if not any(sc.eligible for sc in scenarios):
        raise ClaimInputError(
            "No claim-age pair is eligible for these inputs: "
            + "; ".join(f"{e.person} {e.age}: {e.reason}" for e in exclusions)
        )
    params = JointSearchParams(
        monte_carlo_runs=payload.monte_carlo_runs,
        stage1_runs=payload.stage1_runs,
        per_scenario_breadth=payload.per_scenario_breadth,
    )
    request_record = {
        "household_id": payload.household_id,
        "monte_carlo_runs": payload.monte_carlo_runs,
        "stage1_runs": payload.stage1_runs,
        "per_scenario_breadth": payload.per_scenario_breadth,
        "claim_search": payload.claim_search.model_dump(by_alias=True),
        # The ages and the year-0 state were computed for this date.
        "valuation_date": today.isoformat(),
    }

    def work(progress) -> str:
        result = run_joint_optimization(
            state, _ENGINES, settings, constraints, controls, params, on_progress=progress,
        )
        if result.get("status") != "success":
            raise RuntimeError(result.get("message") or result.get("error") or "search failed")
        # Saving the run and writing its reports is a phase of its own: the
        # page shows "Prepare results" while it happens.
        progress("prepare", 0, 1)
        return _persist_run(db, payload.household_id, result, request_record, inputs_snapshot)

    try:
        job = jobs.submit(payload.household_id, work)
    except JobBusyError as exc:  # lost a race with another submit
        raise HTTPException(status_code=409,
                            detail={"message": "An optimization is already running.",
                                    "job_id": exc.active_id}) from exc
    return {"job_id": job["id"], "status": job["status"]}


@router.get("/optimize/jobs/active")
def get_active_optimize_job(request: Request) -> dict | None:
    """The queued or running job, so a reloaded page can resume polling."""
    return _jobs(request).active()


@router.get("/optimize/jobs/{job_id}")
def get_optimize_job(job_id: str, request: Request) -> dict:
    """``{id, household_id, status, phase, progress{done,total}, run_id, error,
    created_at, started_at, finished_at}``. 404 for an unknown id -- which,
    since jobs live in memory, includes every job from before a restart."""
    job = _jobs(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job


# ---------------------------------------------------------------------------
# GET /households/{household_id}/policies
# ---------------------------------------------------------------------------


@router.get("/households/{household_id}/policies")
def list_policies(household_id: str, db: Database = Depends(get_db)) -> dict:
    """Conversion strategies actually available for this household's inputs.

    Which policies exist is a property of the INPUTS, not a fixed list. A rule
    that never finds room (a salary already above the 12% bracket for the
    whole horizon) is not generated, the ``<rule>_thru_<YYYY>`` years depend
    on when each rule converts, and the conversion window, an IRMAA-avoid
    setting and a bracket cap all prune the list too.

    Without this, a UI offering a static menu lets the user pick something the
    optimizer cannot run, and the only feedback is an HTTP 400 after they hit
    Compare.
    """
    try:
        state, settings, constraints = build_optimizer_inputs(
            db, household_id, today=_today()
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    require_claim_ages(state, settings)
    policies = search(state, _ENGINES, settings, constraints)
    return {"policies": sorted({p.policy_id for p in policies})}


# ---------------------------------------------------------------------------
# GET /runs/{run_id}
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Database = Depends(get_db)) -> dict:
    """Return a stored optimization run by id.

    Returns ``{run_id, household_id, created_at, result, inputs}`` or 404 if
    not found.  ``inputs`` is the input snapshot taken when the run was
    created (None for runs predating input snapshots).
    """
    row = db.fetch_one(
        "SELECT id, household_id, created_at, result_json, request_json "
        "FROM runs WHERE id = ?",
        [run_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    request = json.loads(row[4]) if row[4] else {}

    return {
        "run_id": str(row[0]),
        "household_id": str(row[1]),
        "created_at": str(row[2]),
        "result": json.loads(row[3]),
        "inputs": request.get("inputs"),
    }


# ---------------------------------------------------------------------------
# GET /households/{household_id}/runs
# ---------------------------------------------------------------------------


@router.get("/households/{household_id}/runs")
def list_household_runs(
    household_id: str, db: Database = Depends(get_db)
) -> list[dict]:
    """Return a summary list of all runs for a household, newest first.

    Each entry: ``{run_id, created_at, duration_ms, forced_policy, claim_search}``.
    ``forced_policy`` is None for an optimized run and the pinned policy id
    for a "Run this policy" run, so callers can find the plan's latest
    *optimized* result rather than whichever run came last.
    Returns an empty list when no runs exist for the household.
    """
    rows = db.fetch_all(
        "SELECT id, created_at, duration_ms, "
        "json_extract_string(result_json, '$.forced_policy'), "
        "json_extract_string(result_json, '$.search.mode') "
        "FROM runs WHERE household_id = ? "
        "ORDER BY created_at DESC",
        [household_id],
    )
    return [
        {
            "run_id": str(row[0]),
            "created_at": str(row[1]),
            "duration_ms": row[2],
            "forced_policy": row[3],
            # A joint claim-age search ("joint" or "joint_deterministic").
            "claim_search": row[4] is not None,
        }
        for row in rows
    ]
