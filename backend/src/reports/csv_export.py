"""CSV export functionality for yearly retirement plans.

Provides `yearly_plan_csv()` to convert a result dict to CSV format.
"""

from __future__ import annotations

import csv
import io

from src.reports import claim_search
from src.reports.display import bracket_room


def yearly_plan_csv(
    result: dict,
    run_id: str | None = None,
    household_id: str | None = None,
    sale_plans: dict | None = None,
) -> str:
    """Convert yearly_plan from result dict to CSV format.

    Args:
        result: Result dict containing 'yearly_plan' key with list of year dicts.
                Each year dict has: year, age_self, conversion, withdrawal_taxable,
                withdrawal_traditional, withdrawal_roth, rmd, agi, magi, federal_tax,
                state_tax, irmaa, total_tax, effective_rate, marginal_rate,
                net_spendable, required_spending, target_spending,
                discretionary_cut, shortfall, balance_taxable,
                balance_traditional, balance_roth,
                rationale (dict with 'narrative' key).
        run_id: optional run UUID, written as a leading ``# Run ID:`` comment.
        household_id: optional household (plan) UUID, written as a comment.

    Returns:
        CSV string with header row and one data row per year.
        Narrative field is properly quoted if it contains commas.
    """
    yearly_plan = result.get("yearly_plan", [])

    # Define column order (26 scalar fields + narrative)
    columns = [
        "year",
        "age_self",
        "age_spouse",
        "conversion",
        "withdrawal_taxable",
        "withdrawal_traditional",
        "withdrawal_roth",
        "rmd",
        "agi",
        "magi",
        "federal_tax",
        "state_tax",
        "irmaa",
        "total_tax",
        "effective_rate",
        "marginal_rate",
        "bracket_rate",
        "bracket_room_left",
        "net_spendable",
        # required_spending is what the plan TRIED to fund — under guardrails
        # the reduced amount, not the goal. The goal and both gaps travel with
        # it so the sheet cannot imply a lower target than the household set.
        "required_spending",
        "target_spending",
        "discretionary_cut",
        "shortfall",
        "balance_taxable",
        "balance_traditional",
        "balance_roth",
        "narrative",
    ]

    output = io.StringIO()

    # Identity comment lines (spreadsheets ignore leading # rows on import)
    if run_id:
        output.write(f"# Run ID: {run_id}\n")
    if household_id:
        output.write(f"# Household ID: {household_id}\n")

    writer = csv.DictWriter(output, fieldnames=columns)

    # Write header
    writer.writeheader()

    # Write data rows
    for year_row in yearly_plan:
        # Build row dict from year_row, extracting narrative from rationale
        row_data = {}
        for col in columns:
            if col == "narrative":
                # Extract narrative from rationale dict
                rationale = year_row.get("rationale", {})
                row_data[col] = rationale.get("narrative", "") if rationale else ""
            elif col in ("bracket_rate", "bracket_room_left"):
                rate, room = bracket_room(year_row)
                value = rate if col == "bracket_rate" else room
                row_data[col] = "" if value is None else value
            else:
                row_data[col] = year_row.get(col, "")

        writer.writerow(row_data)

    # Joint claim-age search: what was searched and how the pairs compared.
    joint_tables = claim_search.tables(result)
    if joint_tables:
        output.write(f"\n# {claim_search.SECTION}\n")
        sw = csv.writer(output)
        for label, value in claim_search.summary_rows(result):
            sw.writerow([label, value])
        for title, header, rows, note in joint_tables:
            output.write(f"\n# {title}\n")
            if note:
                output.write(f"# {note}\n")
            sw.writerow(header)
            sw.writerows(rows)

    # Optional sale-plan section: the sell list for the first (actionable)
    # taxable-withdrawal year, from the stored portfolio.
    if sale_plans and sale_plans.get("years"):
        output.write("\n")
        output.write(
            f"# Sale plan - prices as of {sale_plans['as_of']} (generated "
            f"{sale_plans.get('generated_on', sale_plans['as_of'])}); this is the "
            "first taxable-withdrawal year only. Re-run the plan next year "
            "with a fresh portfolio to plan later sales\n"
        )
        for yr in sale_plans["years"]:
            for w in yr.get("warnings", []):
                output.write(f"# Warning ({yr['year']}): {w}\n")
        sw = csv.writer(output)
        sw.writerow(
            [
                "year",
                "target_cash",
                "cash_raised",
                "cash_short",
                "ticker",
                "holding_period",
                "shares_to_sell",
                "proceeds",
                "realized_gain",
            ]
        )
        for yr in sale_plans["years"]:
            for s in yr["sold"]:
                sw.writerow(
                    [
                        yr["year"],
                        f"{yr['target_cash']:.2f}",
                        f"{yr.get('cash_raised', yr['target_cash']):.2f}",
                        f"{yr.get('cash_short', 0):.2f}",
                        s["ticker"],
                        s["holding_period"],
                        f"{s['shares_sold']:.3f}",
                        f"{s['proceeds']:.2f}",
                        f"{s['realized_gain']:.2f}",
                    ]
                )

    return output.getvalue()
