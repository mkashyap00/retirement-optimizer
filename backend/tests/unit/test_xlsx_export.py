"""Unit tests for the Excel (.xlsx) export.

Coverage:
  (1) build_xlsx returns valid xlsx bytes (zip magic + openpyxl round-trip)
  (2) Inputs sheet carries the snapshot values
  (3) Yearly Plan sheet has header + one row per year with correct values
  (4) Charts are embedded (balances / taxes / conversions)
  (5) No snapshot → Inputs sheet explains why, plan sheet still present
"""

from __future__ import annotations

import io

import openpyxl
from src.reports.xlsx_export import build_xlsx


def _make_year_row(year: int, age: int, conversion: float) -> dict:
    return {
        "year": year,
        "age_self": age,
        "age_spouse": age - 2,
        "conversion": conversion,
        "withdrawal_taxable": 40000.0,
        "withdrawal_traditional": 20000.0,
        "withdrawal_roth": 0.0,
        "rmd": 0.0,
        "agi": 110000.0,
        "magi": 112000.0,
        "federal_tax": 12000.0,
        "state_tax": 4000.0,
        "irmaa": 0.0,
        "total_tax": 16000.0,
        "effective_rate": 0.145,
        "marginal_rate": 0.22,
        "net_spendable": 90000.0,
        "required_spending": 90000.0,
        "balance_taxable": 250000.0,
        "balance_traditional": 750000.0,
        "balance_roth": 150000.0,
        "rationale": {"narrative": f"Year {year} narrative"},
        "audit": {
            "salary": 0.0,
            "pension": 20000.0,
            "rental": 0.0,
            "interest": 0.0,
            "ordinary_dividends": 0.0,
            "traditional_distributions": 20000.0 + conversion,
            "traditional_taxable_portion": 20000.0 + conversion,
            "gross_social_security": 52800.0,
            "taxable_social_security": 44880.0,
            "ordinary_income": 84880.0 + conversion,
            "qualified_dividends": 0.0,
            "realized_ltcg": 13333.33,
            "agi": 110000.0,
            "deduction_type": "standard",
            "deduction": 33200.0,
            "senior_deduction": 12000.0,
            "taxable_income": 76800.0,
            # max(0, ordinary_income - deduction). `deduction` already includes
            # the senior bonus, so senior_deduction is NOT subtracted again.
            "taxable_ordinary_income": max(0.0, 84880.0 + conversion - 33200.0),
            "ordinary_tax": 10000.0,
            "ltcg_tax": 2000.0,
            "niit": 0.0,
            "federal_tax": 12000.0,
            "state_tax": 4000.0,
            "irmaa_magi_lookback": 80000.0,
            "irmaa": 0.0,
            "total_tax": 16000.0,
        },
    }


def _fixture_result() -> dict:
    return {
        "status": "success",
        "winning_policy": {
            "policy_id": "fill_22",
            "lifetime_taxes_nominal": 480000.0,
            "lifetime_taxes_pv": 350000.0,
            "terminal_estate": 1900000.0,
            "success_probability": 0.9,
            "score": 0.88,
            "total_conversions": 300000.0,
            "projected_future_marginal_rate": 0.24,
        },
        "yearly_plan": [
            _make_year_row(2026 + i, 66 + i, 50000.0 if i < 3 else 0.0)
            for i in range(5)
        ],
        "alternative_policies": [
            {
                "policy_id": "none",
                "lifetime_taxes_delta": 246291.0,
                "terminal_estate_delta": 262671.0,
                "success_probability_delta": -0.06,
            },
        ],
        "warnings": [],
    }


def _fixture_inputs() -> dict:
    return {
        "household": {
            "filing_status": "joint",
            "self_birth_date": "1958-03-15",
            "spouse_birth_date": "1960-03-15",
            "state": "CA",
            "nickname": "Demo",
        },
        "accounts": [
            {"account_type": "traditional", "owner": "joint", "balance": 800000.0,
             "basis": None},
            {"account_type": "taxable", "owner": "joint", "balance": 300000.0,
             "basis": 200000.0},
        ],
        "income": [
            {"category": "pension", "owner": "self", "amount": 20000.0,
             "start_year": None, "end_year": None},
        ],
        "settings": {
            "required_spending": 90000.0,
            "inflation": 0.025,
            "nominal_return": 0.06,
            "ss_pia_self": 2400.0,
            "ss_claim_age_self": 67,
            "ss_pia_spouse": 2000.0,
            "ss_claim_age_spouse": 66,
        },
        "constraints": {
            "irmaa_policy": "soft",
            "conversion_window": "anytime",
            "preserve_taxable": False,
        },
    }


def _load(xlsx_bytes: bytes) -> openpyxl.Workbook:
    return openpyxl.load_workbook(io.BytesIO(xlsx_bytes))


def test_ages_blank_after_plan_to_age():
    """Age columns must go blank once past each person's Plan-to age.

    The household simulates to the LONGER spouse's horizon, so the shorter-
    lived person's age column would otherwise keep counting past their own
    plan-to age (user report: 'I should only see 23 years for the primary').
    """
    inputs = _fixture_inputs()
    # Plan rows carry self 66..70 / spouse 64..68
    inputs["household"]["self_death_age"] = 68
    inputs["household"]["spouse_death_age"] = 67

    ws = _load(build_xlsx(_fixture_result(), inputs))["Yearly Plan"]

    # cols: 1=year, 2=age_self, 3=age_spouse; data rows start at 2
    assert ws.cell(row=4, column=2).value == 68  # last year self is in-plan
    assert ws.cell(row=5, column=2).value is None
    assert ws.cell(row=6, column=2).value is None
    assert ws.cell(row=5, column=3).value == 67  # last year spouse is in-plan
    assert ws.cell(row=6, column=3).value is None


def test_chart_axes_visible_with_dollar_format():
    """Chart y-axes must be explicitly visible and formatted as dollars.

    openpyxl leaves the axis ``delete`` flag unset, which some Excel builds
    interpret as hidden — the user saw charts with no y-axis amounts.
    """
    import zipfile

    data = build_xlsx(_fixture_result(), _fixture_inputs())
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        chart_xmls = [
            z.read(n).decode() for n in z.namelist() if "charts/chart" in n
        ]

    assert len(chart_xmls) == 3, "balances, taxes, conversions charts expected"
    for xml in chart_xmls:
        assert '<delete val="0"' in xml, "axes must be explicitly visible"
        assert 'formatCode="$#,##0' in xml, "y-axis must carry a dollar format"


def test_xlsx_bytes_are_valid_workbook():
    """Output starts with zip magic and openpyxl can load it."""
    data = build_xlsx(_fixture_result(), _fixture_inputs())
    assert data[:2] == b"PK"
    wb = _load(data)
    assert "Inputs" in wb.sheetnames
    assert "Yearly Plan" in wb.sheetnames


def test_inputs_sheet_carries_snapshot_values():
    """Inputs sheet contains spending, filing status, and account balances."""
    wb = _load(build_xlsx(_fixture_result(), _fixture_inputs()))
    ws = wb["Inputs"]
    cells = [
        str(c.value)
        for row in ws.iter_rows()
        for c in row
        if c.value is not None
    ]
    joined = "\n".join(cells)
    assert "joint" in joined
    assert "90000" in joined  # required_spending
    assert "800000" in joined  # traditional balance
    assert "pension" in joined


def test_sale_plans_sheet_present_when_supplied():
    sale_plans = {
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
    wb = _load(build_xlsx(_fixture_result(), _fixture_inputs(), sale_plans=sale_plans))
    assert "Sale Plan" in wb.sheetnames
    # Placed right after "Yearly Plan" so it isn't buried behind later sheets.
    assert wb.sheetnames.index("Sale Plan") == wb.sheetnames.index("Yearly Plan") + 1, (
        f"Sale Plan should follow Yearly Plan, got {wb.sheetnames}"
    )
    cells = [
        str(c.value)
        for row in wb["Sale Plan"].iter_rows()
        for c in row
        if c.value is not None
    ]
    joined = "\n".join(cells)
    assert "VTI" in joined and "2029" in joined and "2026-07-22" in joined


def test_no_sale_plans_sheet_when_absent():
    wb = _load(build_xlsx(_fixture_result(), _fixture_inputs()))
    assert "Sale Plan" not in wb.sheetnames


def test_inputs_sheet_carries_run_and_household_ids():
    """The Inputs sheet stamps the run and plan UUIDs at the top."""
    wb = _load(
        build_xlsx(
            _fixture_result(),
            _fixture_inputs(),
            run_id="run-abc",
            household_id="hh-xyz",
        )
    )
    cells = [
        str(c.value)
        for row in wb["Inputs"].iter_rows()
        for c in row
        if c.value is not None
    ]
    joined = "\n".join(cells)
    assert "Run ID" in joined and "run-abc" in joined
    assert "Household ID" in joined and "hh-xyz" in joined
    # Snapshot values still present below the ID block
    assert "90000" in joined


def test_yearly_plan_sheet_rows_and_values():
    """Plan sheet: header row + one row per year; spot-check values."""
    result = _fixture_result()
    wb = _load(build_xlsx(result, _fixture_inputs()))
    ws = wb["Yearly Plan"]
    assert ws.max_row == 1 + len(result["yearly_plan"])
    header = [c.value for c in ws[1]]
    assert "year" in header
    assert "conversion" in header
    assert "narrative" in header
    # First data row: year and conversion
    year_col = header.index("year") + 1
    conv_col = header.index("conversion") + 1
    assert ws.cell(row=2, column=year_col).value == 2026
    assert ws.cell(row=2, column=conv_col).value == 50000.0


def test_charts_are_embedded():
    """Workbook embeds the three charts (balances, taxes, conversions)."""
    wb = _load(build_xlsx(_fixture_result(), _fixture_inputs()))
    ws = wb["Charts"]
    assert len(ws._charts) == 3


def test_no_snapshot_still_produces_plan_sheet():
    """Runs predating snapshots export with an explanatory Inputs sheet."""
    wb = _load(build_xlsx(_fixture_result(), None))
    assert "Yearly Plan" in wb.sheetnames
    ws = wb["Inputs"]
    first_cell = ws.cell(row=1, column=1).value
    assert first_cell is not None and "not available" in str(first_cell)


def test_alternatives_sheet_records_runners_up():
    """The Alternatives sheet lists the rejected policies as deltas."""
    wb = _load(build_xlsx(_fixture_result(), _fixture_inputs()))
    assert "Alternatives" in wb.sheetnames
    ws = wb["Alternatives"]
    cells = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    joined = "\n".join(cells)
    assert "Compared with the recommendation: Fill the 22% bracket" in joined  # humanized
    assert "No conversions" in joined  # alternative humanized
    assert "246291" in joined  # taxes delta value present


# ---------------------------------------------------------------------------
# Tax Audit sheet — per-year derivation for independent verification
# ---------------------------------------------------------------------------


def test_tax_audit_sheet_renders_worksheet_lines():
    wb = _load(build_xlsx(_fixture_result(), _fixture_inputs()))
    assert "Tax Audit" in wb.sheetnames
    ws = wb["Tax Audit"]

    labels = [c.value for c in ws["A"] if c.value]
    for expected in (
        "Social Security (taxable)",
        "Taxable income",
        "Federal tax",
        "IRMAA surcharge",
        "Total tax",
    ):
        assert expected in labels, f"missing audit line {expected!r}: {labels}"


def test_tax_audit_sheet_shows_taxable_ordinary_income():
    """The sheet must show taxable ORDINARY income, not just taxable income.

    A bracket-fill recommendation is only verifiable against this line: the 12%
    bracket bounds ordinary income, while `taxable_income` also contains
    qualified dividends and long-term gains, which stack above it on their own
    rate schedule. Without this row the sheet cannot answer "did the conversion
    actually fill the bracket?".
    """
    result = _fixture_result()
    ws = _load(build_xlsx(result, _fixture_inputs()))["Tax Audit"]

    labels = [c.value for c in ws["A"] if c.value]
    label = "— of which taxable ordinary income"
    assert label in labels, f"missing audit line {label!r}: {labels}"

    row = next(c.row for c in ws["A"] if c.value == label)
    first_year_audit = result["yearly_plan"][0]["audit"]
    assert ws.cell(row=row, column=2).value == first_year_audit["taxable_ordinary_income"]

    # Years run across the columns; the first year's federal tax ties to the
    # fixture's audit value
    label_rows = {c.value: c.row for c in ws["A"] if c.value}
    year_row = label_rows["Year"]
    assert ws.cell(row=year_row, column=2).value == 2026
    fed_row = label_rows["Federal tax"]
    assert ws.cell(row=fed_row, column=2).value == 12000.0


def test_tax_audit_sheet_message_when_absent():
    """Runs created before audit mode get a message, not a crash."""
    result = _fixture_result()
    for row in result["yearly_plan"]:
        row.pop("audit", None)
    ws = _load(build_xlsx(result, _fixture_inputs()))["Tax Audit"]
    assert "audit" in str(ws.cell(row=1, column=1).value).lower()


# ---------------------------------------------------------------------------
# Dynamic spending reaches the workbook
# ---------------------------------------------------------------------------
#
# These two settings shipped to the wizard and the results page but not to the
# exports, so a spreadsheet described a plan without saying whether spending
# was allowed to flex — which changes what every other figure in it means.


def _inputs_with_spending(rule, floor=None):
    s = {
        "required_spending": 130000,
        "inflation": 0.03,
        "nominal_return": 0.06,
        "ss_pia_self": 3000,
        "ss_claim_age_self": 67,
        "spending_rule": rule,
    }
    if floor is not None:
        s["spending_floor"] = floor
    return {
        "household": {"filing_status": "joint", "self_birth_date": "1961-04-02",
                       "state": "CA"},
        "accounts": [], "income": [], "settings": s,
        "constraints": {"irmaa_policy": "soft"},
    }


def _inputs_sheet_text(inputs):
    ws = _load(build_xlsx(_fixture_result(), inputs=inputs))["Inputs"]
    return "\n".join(
        " | ".join("" if c is None else str(c) for c in row)
        for row in ws.iter_rows(values_only=True)
    )


def test_inputs_sheet_states_the_spending_rule_when_guardrails_on():
    text = _inputs_sheet_text(_inputs_with_spending("guardrails", floor=95000))
    assert "If markets go badly" in text
    assert "Cut back, then recover" in text
    assert "Essential spending floor" in text
    assert "95000" in text


def test_inputs_sheet_states_the_spending_rule_even_on_the_default():
    """Silence would read as 'not modelled', not as 'spending stayed fixed'."""
    text = _inputs_sheet_text(_inputs_with_spending("fixed"))
    assert "If markets go badly" in text
    assert "Keep spending the same" in text
    # No floor was set, so the row is omitted rather than shown as blank.
    assert "Essential spending floor" not in text


def test_inputs_sheet_treats_a_missing_rule_as_fixed():
    """Runs stored before dynamic spending existed have no rule at all."""
    inputs = _inputs_with_spending("fixed")
    del inputs["settings"]["spending_rule"]
    assert "Keep spending the same" in _inputs_sheet_text(inputs)


def test_plan_sheet_carries_target_alongside_reduced_spending():
    """required_spending is what the plan TRIED to fund.

    Under guardrails that is the REDUCED figure, so shipping it alone let the
    sheet imply the household's target was lower than it really was.
    """
    result = _fixture_result()
    for row in result["yearly_plan"]:
        row["required_spending"] = 108000.0
        row["target_spending"] = 130000.0
        row["discretionary_cut"] = 22000.0
        row["shortfall"] = 0.0

    ws = _load(build_xlsx(result))["Yearly Plan"]
    header = [c.value for c in ws[1]]
    for name in ("required_spending", "target_spending", "discretionary_cut",
                 "shortfall"):
        assert name in header, f"{name} missing from the Yearly Plan sheet"

    values = {name: ws.cell(row=2, column=header.index(name) + 1).value
              for name in ("required_spending", "target_spending",
                           "discretionary_cut")}
    assert values["target_spending"] == 130000.0
    assert values["required_spending"] == 108000.0
    assert values["discretionary_cut"] == 22000.0


def test_plan_sheet_leaves_new_columns_blank_for_old_runs():
    """Runs stored before these fields existed must still export."""
    result = _fixture_result()
    for row in result["yearly_plan"]:
        row.pop("target_spending", None)
        row.pop("discretionary_cut", None)
        row.pop("shortfall", None)

    ws = _load(build_xlsx(result))["Yearly Plan"]
    header = [c.value for c in ws[1]]
    assert ws.cell(row=2, column=header.index("target_spending") + 1).value is None


def test_yearly_plan_sheet_shows_bracket_room_left():
    """The bracket the year's ordinary income lands in and the room left in it.

    Headroom used to surface only inside a conversion year's narrative, so a
    year like 2028 — $33,000 of the 12% bracket unused, no conversion — showed
    it nowhere.
    """
    result = _fixture_result()
    plan = result["yearly_plan"]
    plan[0]["rationale"]["bracket"] = {
        "bracket_rate": 0.12, "bracket_top": 100800.0,
        "headroom_used": 0.0, "headroom_remaining": 33000.0,
    }
    # Top bracket: no ceiling, so no room figure.
    plan[1]["rationale"]["bracket"] = {
        "bracket_rate": 0.37, "bracket_top": None,
        "headroom_used": 0.0, "headroom_remaining": 0.0,
    }
    # plan[2] carries no bracket facts at all (older stored runs).

    ws = _load(build_xlsx(result, _fixture_inputs()))["Yearly Plan"]
    header = [c.value for c in ws[1]]
    rate_col = header.index("bracket_rate") + 1
    room_col = header.index("bracket_room_left") + 1
    assert rate_col == header.index("marginal_rate") + 2  # sits beside it

    assert ws.cell(row=2, column=rate_col).value == 0.12
    assert ws.cell(row=2, column=rate_col).number_format == "0.0%"
    assert ws.cell(row=2, column=room_col).value == 33000.0
    assert ws.cell(row=2, column=room_col).number_format == "#,##0"

    assert ws.cell(row=3, column=rate_col).value == 0.37
    assert ws.cell(row=3, column=room_col).value is None

    assert ws.cell(row=4, column=rate_col).value is None
    assert ws.cell(row=4, column=room_col).value is None


# ---------------------------------------------------------------------------
# Results sheet — what the Results page shows above the fold
# ---------------------------------------------------------------------------


def _results_cells(result: dict, **kwargs) -> dict[str, list]:
    """Map each column-A label on the Results sheet to the rest of its row."""
    ws = _load(build_xlsx(result, _fixture_inputs(), **kwargs))["Results"]
    rows: dict[str, list] = {}
    for row in ws.iter_rows(values_only=True):
        if row and row[0] is not None:
            rows[str(row[0])] = [v for v in row[1:] if v is not None]
    return rows


def test_results_sheet_opens_the_workbook():
    wb = _load(build_xlsx(_fixture_result(), _fixture_inputs()))
    assert wb.sheetnames[0] == "Results"
    assert wb.active.title == "Results"


def test_results_sheet_carries_the_summary_cards_and_winner():
    result = _fixture_result()
    result["monte_carlo_runs"] = 300
    result["winning_policy"].update(
        policy_id="fill_10_annual",
        success_probability=0.6467,
        mean_years_reduced=1.9,
        discount_rate=0.02,
    )
    rows = _results_cells(result, run_id="run-abc", household_id="hh-xyz")

    assert rows["Run ID"] == ["run-abc"]
    assert rows["Household ID"] == ["hh-xyz"]
    # The label the Results page shows, not the raw id.
    assert rows["Recommended strategy"] == ["Fill the 10% bracket every year"]
    assert rows["Projected future marginal rate"] == [0.24]

    # The Results page's labels, each naming its basis.
    assert rows["Lifetime taxes — steady-return projection"] == [
        480000.0, "$350,000 in today's dollars (2% discount)"
    ]
    assert rows["Lifetime taxes — steady-return projection, today's dollars"] == [350000.0]
    assert rows["Projected estate — steady-return projection"] == [1900000.0, "final-year dollars"]
    # p=0.6467, n=300 -> 1.96*sqrt(p(1-p)/300) = 5.4pp -> "5 pts"
    assert rows["Spending funded in market scenarios"] == [
        0.6467,
        "± 5 pts (300 scenarios)",
        "Spending below target in approximately 2 years per market scenario.",
    ]
    assert any(k.startswith("Modeled score — average across") for k in rows)
    assert rows["Total Roth conversions"] == [300000.0]


def test_the_interval_uses_the_policys_own_scenario_count():
    result = _fixture_result()
    result["monte_carlo_runs"] = 300
    result["winning_policy"].update(success_probability=0.6467, monte_carlo_paths=100)
    rows = _results_cells(result)
    # p=0.6467, n=100 -> 1.96*sqrt(p(1-p)/100) = 9.4pp -> "9 pts"
    assert rows["Spending funded in market scenarios"][1] == "± 9 pts (100 scenarios)"


def test_results_sheet_lists_every_advisory():
    result = _fixture_result()
    result["warnings"] = ["First advisory.", "Second advisory."]
    ws = _load(build_xlsx(result, _fixture_inputs()))["Results"]
    values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    assert "Advisories" in values
    assert "First advisory." in values and "Second advisory." in values


def test_results_sheet_without_simulation_omits_the_interval():
    result = _fixture_result()
    result["monte_carlo_runs"] = 0
    rows = _results_cells(result)
    # One stored path is not a share of simulated paths.
    assert rows["Spending funded in market scenarios"] == ["No market simulation"]
    assert "Modeled score — steady-return projection, today's dollars" in rows


def test_results_sheet_does_not_call_a_forced_policy_the_winner():
    result = _fixture_result()
    result["forced_policy"] = "fill_22"
    rows = _results_cells(result)
    assert rows["Strategy you chose to run"] == ["Fill the 22% bracket (greedy)"]
    assert "Recommended strategy" not in rows


def test_alternatives_sheet_shows_each_strategys_conversion_this_year():
    """Close strategies can disagree by hundreds of thousands on year 0 alone.

    The deltas cannot show that, so each row carries its own first-year
    conversion, and the winner's sits beside the heading for comparison.
    """
    result = _fixture_result()
    result["winning_policy"]["year0_conversion"] = 50000.0
    result["alternative_policies"][0]["year0_conversion"] = 98000.0
    ws = _load(build_xlsx(result, _fixture_inputs()))["Alternatives"]
    headers = [ws.cell(row=4, column=c).value for c in range(1, 9)]
    # Named by the saved projection's own first year.
    assert "Roth conversion in 2026" in headers
    col = headers.index("Roth conversion in 2026") + 1
    assert ws.cell(row=5, column=col).value == 98000.0
    cells = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert "$50,000 in 2026" in cells


def test_alternatives_sheet_leaves_conversion_blank_on_older_runs():
    """Runs saved before year0_conversion existed export without inventing one."""
    ws = _load(build_xlsx(_fixture_result(), _fixture_inputs()))["Alternatives"]
    headers = [ws.cell(row=4, column=c).value for c in range(1, 9)]
    col = headers.index("Roth conversion in 2026") + 1
    assert ws.cell(row=5, column=col).value is None


def test_alternatives_sheet_labels_comparisons_only_when_markets_were_simulated():
    """A deterministic run's paired comparison rests on one path: no label."""
    result = _fixture_result()
    result["monte_carlo_runs"] = 300
    result["alternative_policies"][0]["paired"] = {"verdict": "equivalent"}

    def comparison(r):
        ws = _load(build_xlsx(r, _fixture_inputs()))["Alternatives"]
        headers = [ws.cell(row=4, column=c).value for c in range(1, 9)]
        return ws.cell(row=5, column=headers.index("Comparison result") + 1).value

    assert comparison(result) == "Practically equivalent"
    result["monte_carlo_runs"] = 0
    assert comparison(result) == "—"


def test_market_explanation_reads_the_runs_recorded_model():
    """The assumptions come from the run, never from a hard-coded 6% / 12%."""
    from src.reports.result_labels import market_explanation

    result = _fixture_result()
    result["monte_carlo_runs"] = 300
    result["market_model"] = {"scenarios": 300, "mean_return": 0.055, "volatility": 0.1,
                              "distribution": "normal", "independent_years": True}
    text = " ".join(market_explanation(result))
    assert "300 possible investment-return scenarios" in text
    assert "average annual return of 5.5%" in text
    assert "Annual volatility is 10 percentage points" in text
    assert "steady 5.5% annual return" in text
    # An older run: return from its inputs, volatility left unstated.
    del result["market_model"]
    older = " ".join(market_explanation(result, 0.07))
    assert "average annual return of 7%" in older and "volatility" not in older
    # No simulation: says so, with no scenario language.
    result["monte_carlo_runs"] = 0
    assert market_explanation(result, 0.06) == [
        "This run did not simulate market outcomes. Every figure comes from a projection "
        "assuming a steady 6% annual return."]


def _ranked_joint_result() -> dict:
    """A claim-age search whose close alternatives look better on the
    steady-return projection but score lower across the scenarios."""
    result = _fixture_result()
    result.update({
        "monte_carlo_runs": 300,
        "market_model": {"scenarios": 300, "mean_return": 0.06, "volatility": 0.12},
    })
    result["winning_policy"].update({
        "policy_id": "none", "key": "none@69-68", "claim_age_self": 69, "claim_age_spouse": 68,
        "score": 3_000_820.0, "success_probability": 0.98, "monte_carlo_paths": 300,
        "year0_conversion": 0.0,
    })

    def alt(s, p, mean, verdict, policy="none"):
        return {"policy_id": policy, "key": f"{policy}@{s}-{p}", "claim_age_self": s,
                "claim_age_spouse": p, "lifetime_taxes_delta": -16_710.0,
                "terminal_estate_delta": 34_568.0, "success_probability_delta": -0.0033,
                "monte_carlo_paths": 300, "score": 3_000_820.0 - mean, "year0_conversion": 0.0,
                "paired": {"verdict": verdict, "mean_difference": mean}}

    result["alternative_policies"] = [
        alt(68, 66, 2_326.0, "unresolved"), alt(68, 67, 2_206.0, "unresolved"),
        alt(68, 66, 13_660.0, "winner", "level_5pct_thru_2029")]
    return result


def test_ranking_rows_follow_the_score_that_ranked_them():
    from src.reports.result_labels import close_call_sentence, ranking_rows

    result = _ranked_joint_result()
    rows = ranking_rows(result)
    assert [r["name"] for r in rows] == [
        "No conversions · You 69 · Spouse 68", "No conversions · You 68 · Spouse 67",
        "No conversions · You 68 · Spouse 66",
        "Convert up to 5% of the starting IRA each year through 2029 · You 68 · Spouse 66"]
    assert rows[0]["recommendation"] and rows[0]["funded"] == 294
    assert rows[1]["difference"] == -2_206.0 and rows[1]["funded"] == 293
    assert close_call_sentence(result) == (
        "Ages 69 / 68 have the highest average modeled score. However, this simulation cannot "
        "clearly separate them from ages 68 / 66 or 68 / 67.")
    # No simulation, or nothing to rank an alternative by: the older table.
    assert ranking_rows({**result, "monte_carlo_runs": 0}) is None
    assert ranking_rows(_fixture_result()) is None


def test_alternatives_sheet_leads_with_scores_and_labels_the_steady_columns():
    ws = _load(build_xlsx(_ranked_joint_result(), _fixture_inputs()))["Alternatives"]
    headers = [ws.cell(row=4, column=c).value for c in range(1, 10)]
    assert headers[2:6] == ["Average modeled score", "Difference from recommendation",
                            "Scenarios with spending funded", "Comparison result"]
    assert headers[7] == "Tax difference · today's dollars — assuming a steady 6% return"
    assert ws.cell(row=5, column=1).value == "No conversions (recommendation)"
    assert ws.cell(row=5, column=5).value == "294 of 300"
    assert ws.cell(row=6, column=4).value == -2_206.0
    assert ws.cell(row=6, column=6).value == "Too close to distinguish"
    assert ws.cell(row=6, column=8).value == -16_710.0
    assert ws.cell(row=3, column=1).value.startswith("Ages 69 / 68 have the highest")
