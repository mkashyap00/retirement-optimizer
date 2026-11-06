"""Server-side report storage.

Reports (CSV, PDF, XLSX) are written to the ``reports/`` directory at the
project root as soon as a run completes — no download click required.
Filenames carry the run's creation timestamp.

The directory can be overridden with the ``REPORTS_DIR`` environment
variable (used by tests to write to a temp dir).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.reports.csv_export import yearly_plan_csv
from src.reports.pdf_export import build_pdf
from src.reports.xlsx_export import build_xlsx

logger = logging.getLogger(__name__)

# <project-root>/reports  (this file is backend/src/reports/storage.py)
_DEFAULT_REPORTS_DIR = Path(__file__).parents[3] / "reports"


def reports_dir() -> Path:
    """Return the reports directory, creating it if necessary."""
    override = os.environ.get("REPORTS_DIR")
    path = Path(override) if override else _DEFAULT_REPORTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def ts_slug(ts_raw: object) -> str:
    """Convert a DuckDB timestamp column value to a compact filename slug.

    ``"2026-07-05 14:30:22.123456"`` → ``"20260705_143022"``.
    """
    ts_str = str(ts_raw)
    return ts_str[:19].replace("-", "").replace(" ", "_").replace(":", "")


def save_run_reports(
    created_at: object,
    result: dict,
    inputs: dict | None,
    sale_plans: dict | None = None,
    run_id: str | None = None,
    household_id: str | None = None,
) -> dict[str, Path]:
    """Write CSV, PDF, and XLSX report files for a completed run.

    Called from the optimize endpoint right after the run is persisted, so
    the files exist as soon as results are shown (no download click needed).

    Args:
        created_at: run creation timestamp (drives the filename slug).
        result: optimization result dict.
        inputs: input snapshot (household context for the PDF; may be None).
        sale_plans: sell list for the first taxable-withdrawal year, or None.
            Must be forwarded so the auto-saved files match the on-demand
            downloads (both carry the Sale Plan when a portfolio exists).
        run_id, household_id: identify the run and plan in every file, as the
            download endpoints do. Without them a saved file could not be
            traced back to the run that produced it.

    Returns:
        Mapping of format name → written path.
    """
    slug = ts_slug(created_at)
    # The timestamp is to the second; two runs saved in the same second would
    # overwrite each other's files. The run id's first block keeps them apart.
    if run_id:
        slug = f"{slug}_{run_id[:8]}"
    out = reports_dir()
    written: dict[str, Path] = {}

    csv_path = out / f"retirement-plan_{slug}.csv"
    csv_path.write_text(
        yearly_plan_csv(
            result,
            run_id=run_id,
            household_id=household_id,
            sale_plans=sale_plans,
        ),
        encoding="utf-8",
    )
    written["csv"] = csv_path

    hh = (inputs or {}).get("household", {})
    household_ctx = {
        "filing_status": hh.get("filing_status", "—"),
        "state": hh.get("state", "—"),
        "run_date": str(created_at)[:10],
        "run_id": run_id,
        "household_id": household_id,
    }
    pdf_path = out / f"retirement-report_{slug}.pdf"
    pdf_path.write_bytes(
        build_pdf(result, household_ctx, inputs=inputs, sale_plans=sale_plans)
    )
    written["pdf"] = pdf_path

    xlsx_path = out / f"retirement-plan_{slug}.xlsx"
    xlsx_path.write_bytes(
        build_xlsx(
            result,
            inputs=inputs,
            run_id=run_id,
            household_id=household_id,
            sale_plans=sale_plans,
        )
    )
    written["xlsx"] = xlsx_path

    logger.info("saved run reports: %s", ", ".join(p.name for p in written.values()))
    return written
