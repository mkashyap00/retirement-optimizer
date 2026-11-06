"""Reports endpoints.

Routes:
  GET   /runs/{run_id}/export.csv     → yearly plan as CSV
  GET   /runs/{run_id}/export.xlsx    → Excel workbook (inputs + plan + charts)
  GET   /runs/{run_id}/report.pdf     → full PDF report
  POST  /runs/{run_id}/narrative      → optional LLM-generated narrative

Server-side copies are written to reports/ automatically when a run
completes (see optimization.py + src/reports/storage.py); these endpoints
serve the bytes on demand.
"""

from __future__ import annotations

import json
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from src.api.dependencies import get_db
from src.api.sale_plans import run_sale_plans
from src.data.database import Database
from src.reports.csv_export import yearly_plan_csv
from src.reports.llm_client import AnthropicClient, LLMClient, OpenAICompatibleClient
from src.reports.llm_narrative import generate_narrative, load_system_prompt
from src.reports.pdf_export import build_pdf
from src.reports.storage import ts_slug
from src.reports.xlsx_export import build_xlsx

router = APIRouter(tags=["reports"])


def get_llm_client() -> LLMClient:
    """Factory: local OpenAI-compatible endpoint when LLM_BASE_URL is set
    (llama.cpp server, LM Studio, Ollama, vLLM), else the Anthropic SDK.

    Overridden in tests via ``monkeypatch`` to inject a
    :class:`~src.reports.llm_client.FakeClient`.
    """
    base_url = os.environ.get("LLM_BASE_URL")
    if base_url:
        return OpenAICompatibleClient(
            base_url=base_url,
            api_key=os.environ.get("LLM_API_KEY", "local"),
            model=os.environ.get("LLM_MODEL", "local-model"),
        )
    try:
        return AnthropicClient()
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="anthropic package not installed — pip install -e '.[llm]'"
        ) from exc


@router.get("/runs/{run_id}/export.csv")
def export_run_csv(run_id: str, db: Database = Depends(get_db)) -> Response:
    """Export yearly plan for a stored run as CSV.

    Fetches the run from the database, converts yearly_plan to CSV format,
    and returns it with appropriate Content-Disposition header for download.

    Args:
        run_id: UUID of the stored optimization run.
        db: Database dependency.

    Returns:
        CSV file with Content-Disposition: attachment header.

    Raises:
        404 if run not found.
    """
    row = db.fetch_one(
        "SELECT result_json, created_at, household_id FROM runs WHERE id = ?",
        [run_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    result_json_str, created_at, household_id = row

    # Parse result JSON
    result = json.loads(result_json_str)

    # Generate CSV
    csv_content = yearly_plan_csv(
        result,
        run_id=run_id,
        household_id=str(household_id),
        sale_plans=run_sale_plans(db, result, date.today()),
    )

    filename = f"retirement-plan_{ts_slug(created_at)}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/export.xlsx")
def export_run_xlsx(run_id: str, db: Database = Depends(get_db)) -> Response:
    """Export a stored run as an Excel workbook.

    Sheets: Results (winner, summary cards, advisories), Inputs (run's input
    snapshot), Yearly Plan, Alternatives, Tax Audit, Charts (native Excel
    charts for balances, taxes, and conversions), and Sale Plan when a
    portfolio exists.

    Raises:
        404 if run not found.
    """
    row = db.fetch_one(
        "SELECT result_json, request_json, created_at, household_id "
        "FROM runs WHERE id = ?",
        [run_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    result_json_str, request_json, created_at, household_id = row
    result = json.loads(result_json_str)
    request = json.loads(request_json) if request_json else {}

    xlsx_bytes = build_xlsx(
        result,
        inputs=request.get("inputs"),
        run_id=run_id,
        household_id=str(household_id),
        sale_plans=run_sale_plans(db, result, date.today()),
    )

    filename = f"retirement-plan_{ts_slug(created_at)}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/report.pdf")
def export_run_pdf(run_id: str, db: Database = Depends(get_db)) -> Response:
    """Export a full PDF report for a stored optimization run.

    Fetches the run and household data from the database, builds a multi-page
    PDF via ReportLab, and returns it with appropriate headers for download.

    Args:
        run_id: UUID of the stored optimization run.
        db: Database dependency.

    Returns:
        PDF file with Content-Disposition: attachment header.

    Raises:
        404 if run not found or household not found.
    """
    row = db.fetch_one(
        "SELECT r.result_json, h.filing_status, h.state, r.created_at, "
        "r.request_json, r.llm_narrative, r.household_id "
        "FROM runs r LEFT JOIN households h ON h.id = r.household_id "
        "WHERE r.id = ?",
        [run_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    (
        result_json,
        filing_status,
        state,
        created_at,
        request_json,
        llm_narrative,
        household_id,
    ) = row

    # Check if household was deleted (result_json exists but household fields are NULL)
    if filing_status is None or state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Household for run {run_id!r} not found"
        )

    result = json.loads(result_json)

    # Build the household context dict passed to build_pdf
    household = {
        "filing_status": filing_status,
        "state": state,
        "run_date": str(date.today()),
        "run_id": run_id,
        "household_id": str(household_id),
    }

    # Input snapshot taken at run time (None for runs predating snapshots)
    request = json.loads(request_json) if request_json else {}
    inputs = request.get("inputs")

    pdf_bytes = build_pdf(
        result,
        household,
        inputs=inputs,
        advisor_text=llm_narrative,
        sale_plans=run_sale_plans(db, result, date.today()),
    )

    filename = f"retirement-report_{ts_slug(created_at)}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        # inline: browsers render the PDF in a tab instead of forcing a download
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/runs/{run_id}/narrative")
def narrative_run(run_id: str, db: Database = Depends(get_db)) -> dict:
    """Generate an optional LLM-enhanced narrative for a stored run.

    Requires ``ANTHROPIC_API_KEY`` to be set in the environment.  Returns
    501 when the key is absent so the frontend can hide the button when
    the feature is unconfigured.

    Args:
        run_id: UUID of the stored optimization run.
        db: Database dependency.

    Returns:
        ``{"narrative": "<plain-language text>"}``

    Raises:
        501 if ``ANTHROPIC_API_KEY`` is not set.
        404 if the run does not exist.
    """
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_BASE_URL")):
        raise HTTPException(
            status_code=501,
            detail="No LLM configured — set ANTHROPIC_API_KEY or LLM_BASE_URL",
        )

    row = db.fetch_one(
        "SELECT result_json, request_json FROM runs WHERE id = ?",
        [run_id],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    result = json.loads(row[0])
    request = json.loads(row[1]) if row[1] else {}
    inputs = request.get("inputs")

    try:
        text = generate_narrative(
            result,
            get_llm_client(),
            inputs=inputs,
            system_prompt=load_system_prompt(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        # The model failed, not this app: unreachable local server, an error
        # status, a provider outage or a bad key. 502 with the reason, so the
        # user can fix the LLM rather than chase a bare server error.
        raise HTTPException(
            status_code=502, detail=f"The LLM request failed: {exc}"
        ) from exc

    # Persist with the run so the PDF's Advisor Commentary section (and any
    # later re-download) reuses it instead of paying the LLM latency again.
    db.execute(
        "UPDATE runs SET llm_narrative = ? WHERE id = ?", [text, run_id]
    )
    return {"narrative": text}
