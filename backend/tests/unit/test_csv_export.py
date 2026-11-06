"""Unit tests for CSV export functionality.

TDD RED phase — tests written BEFORE implementation.

Test cases:
  (1) 3-year fixture → CSV has 4 lines (header + 3 data rows)
  (2) Header contains 'conversion' and 'federal_tax'
  (3) A numeric value from fixture matches in CSV
  (4) Narrative containing comma is quoted properly
"""

from __future__ import annotations

import csv
import io

from src.reports.csv_export import yearly_plan_csv


def _fixture_3year_result() -> dict:
    """Return a result dict with a 3-year yearly_plan for testing."""
    return {
        "yearly_plan": [
            {
                "year": 2025,
                "age_self": 62,
                "conversion": 50000.00,
                "withdrawal_taxable": 20000.00,
                "withdrawal_traditional": 30000.00,
                "withdrawal_roth": 10000.00,
                "rmd": 0.00,
                "agi": 80000.00,
                "magi": 82000.00,
                "federal_tax": 8500.00,
                "state_tax": 2000.00,
                "irmaa": 100.00,
                "total_tax": 10600.00,
                "effective_rate": 0.1325,
                "marginal_rate": 0.24,
                "net_spendable": 89400.00,
                "required_spending": 90000.00,
                "balance_taxable": 280000.00,
                "balance_traditional": 770000.00,
                "balance_roth": 140000.00,
                "rationale": {
                    "narrative": "Year 1: Conservative withdrawal, some conversion"
                },
            },
            {
                "year": 2026,
                "age_self": 63,
                "conversion": 60000.00,
                "withdrawal_taxable": 25000.00,
                "withdrawal_traditional": 35000.00,
                "withdrawal_roth": 15000.00,
                "rmd": 0.00,
                "agi": 85000.00,
                "magi": 87000.00,
                "federal_tax": 9200.00,
                "state_tax": 2200.00,
                "irmaa": 150.00,
                "total_tax": 11550.00,
                "effective_rate": 0.1359,
                "marginal_rate": 0.24,
                "net_spendable": 88450.00,
                "required_spending": 90000.00,
                "balance_taxable": 255000.00,
                "balance_traditional": 735000.00,
                "balance_roth": 155000.00,
                "rationale": {
                    "narrative": "Year 2: Moderate conversion, includes dividend income"
                },
            },
            {
                "year": 2027,
                "age_self": 64,
                "conversion": 70000.00,
                "withdrawal_taxable": 30000.00,
                "withdrawal_traditional": 40000.00,
                "withdrawal_roth": 20000.00,
                "rmd": 0.00,
                "agi": 90000.00,
                "magi": 92000.00,
                "federal_tax": 10100.00,
                "state_tax": 2400.00,
                "irmaa": 200.00,
                "total_tax": 12700.00,
                "effective_rate": 0.1411,
                "marginal_rate": 0.24,
                "net_spendable": 87300.00,
                "required_spending": 90000.00,
                "balance_taxable": 225000.00,
                "balance_traditional": 695000.00,
                "balance_roth": 175000.00,
                "rationale": {
                    "narrative": "Year 3: Strategic conversion, high MAGI years approaching"
                },
            },
        ]
    }


def test_csv_has_4_lines_for_3year_fixture():
    """3-year fixture → CSV has header + 3 data rows = 4 lines total."""
    result = _fixture_3year_result()
    csv_str = yearly_plan_csv(result)
    lines = csv_str.strip().split("\n")
    assert len(lines) == 4, f"Expected 4 lines (1 header + 3 data), got {len(lines)}"


def test_ids_written_as_leading_comments():
    """run_id / household_id appear as leading # comment lines, and the
    column header and data rows are otherwise unchanged."""
    result = _fixture_3year_result()
    csv_str = yearly_plan_csv(result, run_id="run-abc", household_id="hh-xyz")
    lines = csv_str.strip().split("\n")
    assert lines[0] == "# Run ID: run-abc"
    assert lines[1] == "# Household ID: hh-xyz"
    # Table still parses (comment lines skipped)
    data_lines = [ln for ln in lines if not ln.startswith("#")]
    assert len(data_lines) == 4  # header + 3 data rows
    assert data_lines[0].startswith("year,")


def test_no_id_comments_when_ids_omitted():
    """Backward compatible: no comment lines when IDs are not supplied."""
    result = _fixture_3year_result()
    csv_str = yearly_plan_csv(result)
    assert not csv_str.startswith("#")


_SALE_PLANS = {
    "as_of": "2026-07-22",
    "years": [
        {
            "year": 2029,
            "target_cash": 40000.0,
            "sold": [
                {
                    "ticker": "VTI",
                    "holding_period": "long_term",
                    "shares_sold": 120.5,
                    "proceeds": 34000.0,
                    "realized_gain": 9000.0,
                }
            ],
        }
    ],
}


def test_sale_plans_section_appended():
    csv_str = yearly_plan_csv(_fixture_3year_result(), sale_plans=_SALE_PLANS)
    assert "Sale plan" in csv_str
    assert "2026-07-22" in csv_str
    assert "VTI" in csv_str
    assert "2029" in csv_str


def test_no_sale_section_when_absent():
    assert "Sale plan" not in yearly_plan_csv(_fixture_3year_result())


def test_header_contains_conversion_and_federal_tax():
    """Header row contains both 'conversion' and 'federal_tax' columns."""
    result = _fixture_3year_result()
    csv_str = yearly_plan_csv(result)
    lines = csv_str.strip().split("\n")
    header = lines[0]

    assert "conversion" in header, f"Header missing 'conversion': {header}"
    assert "federal_tax" in header, f"Header missing 'federal_tax': {header}"


def test_numeric_value_matches_fixture():
    """A value from fixture matches in the CSV output."""
    result = _fixture_3year_result()
    csv_str = yearly_plan_csv(result)

    reader = csv.DictReader(io.StringIO(csv_str))
    rows = list(reader)

    assert len(rows) == 3, f"Expected 3 data rows, got {len(rows)}"
    # First row should have conversion=50000.0 (as float)
    first_row = rows[0]
    assert float(first_row["conversion"]) == 50000.0, (
        f"Expected conversion=50000.0, got {first_row['conversion']}"
    )


def test_narrative_with_comma_is_quoted():
    """Narrative containing comma is properly quoted in CSV."""
    result = {
        "yearly_plan": [
            {
                "year": 2025,
                "age_self": 62,
                "conversion": 50000.00,
                "withdrawal_taxable": 20000.00,
                "withdrawal_traditional": 30000.00,
                "withdrawal_roth": 10000.00,
                "rmd": 0.00,
                "agi": 80000.00,
                "magi": 82000.00,
                "federal_tax": 8500.00,
                "state_tax": 2000.00,
                "irmaa": 100.00,
                "total_tax": 10600.00,
                "effective_rate": 0.1325,
                "marginal_rate": 0.24,
                "net_spendable": 89400.00,
                "required_spending": 90000.00,
                "balance_taxable": 280000.00,
                "balance_traditional": 770000.00,
                "balance_roth": 140000.00,
                "rationale": {
                    "narrative": "Withdrawal: taxable 20k, traditional 30k, roth 10k"
                },
            },
        ]
    }

    csv_str = yearly_plan_csv(result)
    reader = csv.DictReader(io.StringIO(csv_str))
    rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    # The narrative should be parsed correctly despite containing commas
    assert "taxable" in row["narrative"], (
        f"Narrative not parsed correctly: {row['narrative']}"
    )


# ---------------------------------------------------------------------------
# Dynamic spending reaches the CSV
# ---------------------------------------------------------------------------


def test_csv_carries_the_target_alongside_reduced_spending():
    """required_spending is what the plan TRIED to fund.

    Under guardrails that is the REDUCED figure, so shipping it alone let the
    sheet imply the household's target was lower than it really was.
    """
    result = _fixture_3year_result()
    for row in result["yearly_plan"]:
        row["required_spending"] = 108000.0
        row["target_spending"] = 130000.0
        row["discretionary_cut"] = 22000.0
        row["shortfall"] = 0.0

    # Parse with the csv module, not str.split: the narrative column contains
    # commas and is quoted, so splitting naively overruns the header.
    rows = list(csv.DictReader(io.StringIO(yearly_plan_csv(result))))
    for name in ("required_spending", "target_spending", "discretionary_cut",
                 "shortfall"):
        assert name in rows[0], f"{name} missing from the CSV header"

    first = rows[0]
    assert first["target_spending"] == "130000.0"
    assert first["required_spending"] == "108000.0"
    assert first["discretionary_cut"] == "22000.0"


def test_csv_leaves_the_new_columns_blank_for_old_runs():
    """Runs stored before these fields existed must still export."""
    result = _fixture_3year_result()
    for row in result["yearly_plan"]:
        for k in ("target_spending", "discretionary_cut", "shortfall"):
            row.pop(k, None)

    first = list(csv.DictReader(io.StringIO(yearly_plan_csv(result))))[0]
    assert first["target_spending"] == ""
    assert first["shortfall"] == ""


def test_bracket_room_left_columns():
    """CSV carries the same bracket columns as the xlsx Yearly Plan sheet."""
    result = _fixture_3year_result()
    result["yearly_plan"][0]["rationale"]["bracket"] = {
        "bracket_rate": 0.12, "bracket_top": 100800.0,
        "headroom_used": 0.0, "headroom_remaining": 33000.0,
    }
    rows = list(csv.DictReader(io.StringIO(yearly_plan_csv(result))))
    assert rows[0]["bracket_rate"] == "0.12"
    assert rows[0]["bracket_room_left"] == "33000.0"
    assert rows[1]["bracket_rate"] == ""
    assert rows[1]["bracket_room_left"] == ""
