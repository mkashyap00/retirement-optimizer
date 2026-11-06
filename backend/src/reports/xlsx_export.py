"""Excel (.xlsx) export: Results, Inputs, Yearly Plan, Alternatives, Tax Audit,
Charts, and (with a portfolio) Sale Plan sheets.

Unlike plain CSV (which has no concept of tabs or images), the workbook
carries the run's input snapshot on its own sheet and embeds native Excel
charts built from the yearly plan data.
"""

from __future__ import annotations

import io

# Palette (mirrors the frontend theme, see frontend chartTheme.ts)
_EMERALD = "064E3B"
_GOLD = "C9A84C"
_TEAL = "0D9488"
_CLAY = "B4552D"
_CREAM = "F5F0E0"

# Yearly-plan column order — keep in sync with csv_export.py
_PLAN_COLUMNS = [
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
    # The bracket the year's ordinary income lands in and the room left in it
    # — see display.bracket_room. marginal_rate beside it is the NEXT dollar's
    # rate, so a year filled to a bracket's edge reads 10% here, 12% there.
    "bracket_rate",
    "bracket_room_left",
    "net_spendable",
    # required_spending is what the plan TRIED to fund — under guardrails the
    # reduced amount, not the goal. Shipping it alone let a spreadsheet imply
    # the household's target was lower than it is, so the goal and both gaps
    # travel with it. Blank on runs stored before these fields existed.
    "required_spending",
    "target_spending",
    "discretionary_cut",
    "shortfall",
    "balance_taxable",
    "balance_traditional",
    "balance_roth",
    "narrative",
]

_CURRENCY_COLUMNS = {
    "conversion", "withdrawal_taxable", "withdrawal_traditional",
    "withdrawal_roth", "rmd", "agi", "magi", "federal_tax", "state_tax",
    "irmaa", "total_tax", "net_spendable", "required_spending",
    "target_spending", "discretionary_cut", "shortfall",
    "balance_taxable", "balance_traditional", "balance_roth",
    "bracket_room_left",
}
_PERCENT_COLUMNS = {"effective_rate", "marginal_rate", "bracket_rate"}


def build_xlsx(
    result: dict,
    inputs: dict | None = None,
    run_id: str | None = None,
    household_id: str | None = None,
    sale_plans: dict | None = None,
) -> bytes:
    """Build an Excel workbook for a stored run.

    Args:
        result: optimization result dict (yearly_plan, winning_policy, ...).
        inputs: input snapshot taken at run time, or None for old runs.
        run_id: optional run UUID, shown at the top of the Inputs sheet.
        household_id: optional household (plan) UUID, shown on the Inputs sheet.

    Returns:
        Raw .xlsx bytes (a zip archive, starts with b'PK').
    """
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=_EMERALD)
    section_font = Font(bold=True, color=_EMERALD, size=12)

    # ------------------------------------------------------------------
    # Sheet 1: Results — what the Results page shows above the fold: the
    # winner, the four summary cards with their hint lines, and the
    # advisories. The workbook opens here.
    # ------------------------------------------------------------------

    from src.reports import result_labels as L
    from src.reports.assumption_labels import objective_row, ss_cola_label, tax_tables_label
    from src.reports.display import (
        lifetime_taxes_pv_hint,
        strategy_heading,
        success_interval_hint,
        years_reduced_note,
    )

    ws_res = wb.active
    ws_res.title = "Results"
    ws_res.column_dimensions["A"].width = 32
    ws_res.column_dimensions["B"].width = 34
    ws_res.column_dimensions["C"].width = 42
    ws_res.column_dimensions["D"].width = 44

    wp = result.get("winning_policy") or {}
    ws_res.cell(row=1, column=1, value="Results").font = Font(
        bold=True, color=_EMERALD, size=14
    )
    res_row = 3

    def _res(label: str, *values: object, number_format: str | None = None) -> None:
        nonlocal res_row
        ws_res.cell(row=res_row, column=1, value=label).font = Font(bold=True)
        for col_i, value in enumerate(values, start=2):
            if value is None:
                continue
            cell = ws_res.cell(row=res_row, column=col_i, value=value)
            if col_i == 2 and number_format:
                cell.number_format = number_format
            if col_i > 2:
                cell.font = Font(italic=True, color="6B7280")
        res_row += 1

    if run_id:
        _res("Run ID", run_id)
    if household_id:
        _res("Household ID", household_id)
    if run_id or household_id:
        res_row += 1

    _res(strategy_heading(result), L.strategy(result, wp.get("policy_id", "—")))
    _res(
        "Projected future marginal rate",
        wp.get("projected_future_marginal_rate"),
        number_format="0.0%",
    )
    res_row += 1

    ws_res.cell(row=res_row, column=1, value="Summary").font = section_font
    res_row += 1
    from src.reports import result_labels as L

    _res(
        L.TAXES,
        wp.get("lifetime_taxes_nominal"),
        lifetime_taxes_pv_hint(wp),
        number_format="$#,##0",
    )
    _res(L.TAXES_PV, wp.get("lifetime_taxes_pv"), number_format="$#,##0")
    _res(L.ESTATE, wp.get("terminal_estate"), "final-year dollars", number_format="$#,##0")
    probability = wp.get("success_probability") or 0
    if L.simulated(result):
        _res(
            L.SUCCESS,
            probability,
            # The policy's own path count; runs saved before it was reported
            # fall back to the requested count.
            success_interval_hint(
                probability, wp.get("monte_carlo_paths", result.get("monte_carlo_runs"))
            ),
            years_reduced_note(wp.get("mean_years_reduced")),
            number_format="0%",
        )
    else:
        # One stored path reads 100% or 0%: not a share of anything.
        _res(L.SUCCESS, L.NO_SIMULATION)
    _res(L.score_label(result), wp.get("score"), number_format="$#,##0")
    _res("Total Roth conversions", wp.get("total_conversions"), number_format="$#,##0")
    from src.reports import claim_search

    for label, value in claim_search.summary_rows(result):
        _res(label, value)

    # How the market scenarios were drawn, from the run's own record.
    res_row += 1
    ws_res.cell(row=res_row, column=1, value=(
        "How we simulate market outcomes" if L.simulated(result) else L.NO_SIMULATION
    )).font = section_font
    res_row += 1
    nominal = ((inputs or {}).get("settings") or {}).get("nominal_return")
    for sentence in L.market_explanation(result, nominal):
        ws_res.merge_cells(start_row=res_row, start_column=1, end_row=res_row, end_column=4)
        cell = ws_res.cell(row=res_row, column=1, value=sentence)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws_res.row_dimensions[res_row].height = 15 * (1 + len(sentence) // 140)
        res_row += 1

    warnings = result.get("warnings") or []
    if warnings:
        res_row += 1
        ws_res.cell(row=res_row, column=1, value="Advisories").font = section_font
        res_row += 1
        for warning in warnings:
            ws_res.merge_cells(
                start_row=res_row, start_column=1, end_row=res_row, end_column=4
            )
            cell = ws_res.cell(row=res_row, column=1, value=warning)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            # Merged cells do not auto-fit; size the row to the wrapped text.
            ws_res.row_dimensions[res_row].height = 15 * (1 + len(warning) // 140)
            res_row += 1

    # ------------------------------------------------------------------
    # Joint runs: "Claim-age search" -- the pairs (stage labeled), finalists,
    # baselines, sensitivity, exclusions and assumptions.
    # ------------------------------------------------------------------

    joint_tables = claim_search.tables(result)
    if joint_tables:
        ws_cs = wb.create_sheet("Claim-age search")
        ws_cs.column_dimensions["A"].width = 30
        for col in "BCDEFGH":
            ws_cs.column_dimensions[col].width = 22
        r = 1
        ws_cs.cell(row=r, column=1, value=claim_search.SECTION).font = Font(
            bold=True, color=_EMERALD, size=14
        )
        r += 2
        for title, header, rows, note in joint_tables:
            ws_cs.cell(row=r, column=1, value=title).font = section_font
            r += 1
            if note:
                ws_cs.cell(row=r, column=1, value=note).font = Font(italic=True, color="6B7280")
                r += 1
            for c_i, h in enumerate(header, start=1):
                cell = ws_cs.cell(row=r, column=c_i, value=h)
                cell.font = header_font
                cell.fill = header_fill
            r += 1
            for row in rows:
                for c_i, v in enumerate(row, start=1):
                    cell = ws_cs.cell(row=r, column=c_i, value=v)
                    if isinstance(v, claim_search.Money):
                        cell.value = int(v)
                        cell.number_format = "$#,##0"
                    elif isinstance(v, claim_search.Share):
                        cell.value = float(v)
                        cell.number_format = "0%"
                r += 1
            r += 1

    # ------------------------------------------------------------------
    # Sheet 2: Inputs
    # ------------------------------------------------------------------

    ws_in = wb.create_sheet("Inputs")
    ws_in.column_dimensions["A"].width = 34
    ws_in.column_dimensions["B"].width = 22
    ws_in.column_dimensions["C"].width = 16
    ws_in.column_dimensions["D"].width = 16
    ws_in.column_dimensions["E"].width = 14

    # Identity block at the very top (run + plan UUIDs)
    id_row = 1
    if run_id:
        ws_in.cell(row=id_row, column=1, value="Run ID").font = Font(bold=True)
        ws_in.cell(row=id_row, column=2, value=run_id)
        id_row += 1
    if household_id:
        ws_in.cell(row=id_row, column=1, value="Household ID").font = Font(bold=True)
        ws_in.cell(row=id_row, column=2, value=household_id)
        id_row += 1
    start_row = id_row + 1 if id_row > 1 else 1  # blank spacer after IDs

    if inputs is None:
        ws_in.cell(
            row=start_row, column=1,
            value="Input snapshot not available — this run predates input snapshots.",
        )
    else:
        row = start_row

        def _section(title: str) -> None:
            nonlocal row
            c = ws_in.cell(row=row, column=1, value=title)
            c.font = section_font
            row += 1

        def _item(label: str, value: object) -> None:
            nonlocal row
            ws_in.cell(row=row, column=1, value=label).font = Font(bold=True)
            ws_in.cell(row=row, column=2, value=value)
            row += 1

        hh = inputs.get("household", {})
        _section("Household")
        _item("Filing status", hh.get("filing_status"))
        _item("Your birth date", hh.get("self_birth_date"))
        if hh.get("spouse_birth_date"):
            _item("Spouse birth date", hh["spouse_birth_date"])
        _item("State", hh.get("state"))
        if hh.get("nickname"):
            _item("Plan nickname", hh["nickname"])
        if hh.get("self_death_age") is not None:
            _item("Plan to age", hh["self_death_age"])
        row += 1

        _section("Accounts")
        any_roth_year = any(
            a.get("roth_opened_year") is not None for a in inputs.get("accounts", [])
        )
        acct_headers = ["Type", "Owner", "Balance", "Basis"]
        if any_roth_year:
            acct_headers.append("Roth Opened")
        for col_i, h in enumerate(acct_headers, start=1):
            c = ws_in.cell(row=row, column=col_i, value=h)
            c.font = header_font
            c.fill = header_fill
        row += 1
        for a in inputs.get("accounts", []):
            ws_in.cell(row=row, column=1, value=a.get("account_type"))
            ws_in.cell(row=row, column=2, value=a.get("owner"))
            ws_in.cell(row=row, column=3, value=a.get("balance")).number_format = "#,##0"
            if a.get("basis") is not None and a.get("account_type") != "roth":
                ws_in.cell(row=row, column=4, value=a["basis"]).number_format = "#,##0"
            if any_roth_year and a.get("roth_opened_year") is not None:
                ws_in.cell(row=row, column=5, value=a["roth_opened_year"])
            row += 1
        row += 1

        _section("Income")
        income = inputs.get("income", [])
        if income:
            for col_i, h in enumerate(
                ["Category", "Owner", "Amount/yr", "Start", "End"], start=1
            ):
                c = ws_in.cell(row=row, column=col_i, value=h)
                c.font = header_font
                c.fill = header_fill
            row += 1
            for inc in income:
                ws_in.cell(row=row, column=1, value=inc.get("category"))
                ws_in.cell(row=row, column=2, value=inc.get("owner"))
                ws_in.cell(row=row, column=3, value=inc.get("amount")).number_format = "#,##0"
                ws_in.cell(row=row, column=4, value=inc.get("start_year"))
                ws_in.cell(row=row, column=5, value=inc.get("end_year"))
                row += 1
        else:
            _item("Income sources", "none")
        settings = inputs.get("settings", {})

        def _ss_label(who: str, claim_age: object) -> str:
            base = f"Social Security {who} ($/mo"
            return f"{base}, claim {claim_age})" if claim_age is not None else f"{base})"

        if settings.get("ss_pia_self") is not None:
            _item(
                _ss_label("self", settings.get("ss_claim_age_self")),
                settings["ss_pia_self"],
            )
        if settings.get("ss_pia_spouse") is not None:
            _item(
                _ss_label("spouse", settings.get("ss_claim_age_spouse")),
                settings["ss_pia_spouse"],
            )
        row += 1

        _section("Assumptions")
        _item("Annual spending", settings.get("required_spending"))
        _item("Inflation", settings.get("inflation"))
        _item("Social Security COLA", ss_cola_label(settings))
        _item("Tax tables", tax_tables_label(result))
        _item("Nominal return", settings.get("nominal_return"))
        _item(*objective_row(result, settings))
        # Dynamic spending. Always stated, including the default: a reader
        # holding this spreadsheet needs to know whether the plan assumed
        # spending was rigid, because it changes what every other figure means.
        _rule = settings.get("spending_rule") or "fixed"
        _item(
            "If markets go badly",
            "Cut back, then recover (guardrails)"
            if _rule == "guardrails"
            else "Keep spending the same",
        )
        _floor = settings.get("spending_floor")
        if _floor is not None:
            _item("Essential spending floor", _floor)
        constraints = inputs.get("constraints", {})
        if constraints.get("irmaa_policy"):
            _item(L.IRMAA_HEADING, L.IRMAA_LABEL.get(constraints["irmaa_policy"],
                                                     constraints["irmaa_policy"]))
        if constraints.get("conversion_window"):
            _item("Conversion window", constraints["conversion_window"])
        _mrl = constraints.get("marginal_rate_limit")
        _item(
            "Max ordinary-income bracket",
            f"{round(float(_mrl) * 100)}% bracket" if _mrl is not None else "no limit",
        )
        _mcy = constraints.get("max_conversion_per_year")
        _item(
            "Max conversion / yr",
            float(_mcy) if _mcy is not None else "no limit",
        )
        if constraints.get("preserve_taxable") is not None:
            _item("Preserve taxable", "yes" if constraints["preserve_taxable"] else "no")

    # ------------------------------------------------------------------
    # Sheet 3: Yearly Plan
    # ------------------------------------------------------------------

    from src.reports.display import blank_ages_after_death, bracket_room

    ws_plan = wb.create_sheet("Yearly Plan")
    yearly_plan = blank_ages_after_death(result.get("yearly_plan", []), inputs)

    for col_i, name in enumerate(_PLAN_COLUMNS, start=1):
        c = ws_plan.cell(row=1, column=col_i, value=name)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")
        ws_plan.column_dimensions[get_column_letter(col_i)].width = (
            50 if name == "narrative" else 13
        )
    ws_plan.freeze_panes = "A2"

    for row_i, year_row in enumerate(yearly_plan, start=2):
        for col_i, name in enumerate(_PLAN_COLUMNS, start=1):
            if name == "narrative":
                rationale = year_row.get("rationale") or {}
                value = rationale.get("narrative", "")
            elif name == "bracket_rate":
                value = bracket_room(year_row)[0]
            elif name == "bracket_room_left":
                value = bracket_room(year_row)[1]
            else:
                value = year_row.get(name)
            cell = ws_plan.cell(row=row_i, column=col_i, value=value)
            if name in _CURRENCY_COLUMNS:
                cell.number_format = "#,##0"
            elif name in _PERCENT_COLUMNS:
                cell.number_format = "0.0%"

    # ------------------------------------------------------------------
    # Sheet 4: Alternatives — the policies the search rejected, as deltas
    # vs the winner (part of the run's record)
    # ------------------------------------------------------------------

    alternatives = result.get("alternative_policies", [])
    ws_alt = wb.create_sheet("Alternatives")
    ws_alt.column_dimensions["A"].width = 34
    for col_letter in ("B", "C", "D", "E", "F", "G"):
        ws_alt.column_dimensions[col_letter].width = 22

    from src.reports import result_labels as L_alt

    wp_alt = result.get("winning_policy") or {}
    winner_id = wp_alt.get("policy_id", "—")
    winner_title = f"Compared with the recommendation: {L.strategy(result, winner_id)}"
    if wp_alt.get("year0_conversion") is not None:
        y0 = L_alt.first_year(result)
        winner_title += (f" — converts ${wp_alt['year0_conversion']:,.0f} "
                         f"{'in ' + str(y0) if y0 is not None else 'this year'}")
    ws_alt.cell(row=1, column=1, value=winner_title).font = Font(
        bold=True, color=_EMERALD, size=12
    )
    ws_alt.cell(
        row=2, column=1,
        value=(
            f"Close alternatives. {L_alt.ALTERNATIVES_NOTE} {L_alt.conversion_note(result)} "
            "Tax and estate differences come from the steady-return projection; scenarios "
            "with spending funded is each strategy's own share of the market scenarios."
        ),
    )

    ranked = L_alt.ranking_rows(result) if alternatives else None
    if ranked:
        # The measurement that ranked them leads; the steady-return deltas
        # sit to the right, labelled with the return they assume.
        ws_alt.cell(row=2, column=1, value=L_alt.ranking_note(ranked))
        close = L_alt.close_call_sentence(result)
        if close:
            ws_alt.cell(row=3, column=1, value=close).font = Font(bold=True)
        steady = L_alt.steady_title(result, nominal).removeprefix("Compare taxes and estate ")
        ws_alt.column_dimensions["H"].width = 30
        ws_alt.column_dimensions["I"].width = 30
        for col_i, h in enumerate(
            ["Strategy", "Claim ages", L_alt.SCORE_AVG, L_alt.DIFF, L_alt.FUNDED,
             L_alt.COMPARISON, L_alt.conversion_heading(result),
             f"{L_alt.TAX_DIFF} — {steady}", f"{L_alt.ESTATE_DIFF} — {steady}"],
            start=1,
        ):
            c = ws_alt.cell(row=4, column=col_i, value=h)
            c.font = header_font
            c.fill = header_fill
        for row_i, r in enumerate(ranked, start=5):
            src = r.get("alternative") or wp_alt
            ws_alt.cell(row=row_i, column=1, value=L.strategy(result, src.get("policy_id", "—"))
                        + (" (recommendation)" if r["recommendation"] else ""))
            if src.get("key"):
                ws_alt.cell(row=row_i, column=2, value=L_alt.claim_ages(
                    src.get("claim_age_self"), src.get("claim_age_spouse")))
            if r["score"] is not None:
                ws_alt.cell(row=row_i, column=3, value=r["score"]).number_format = "#,##0"
            if not r["recommendation"]:
                ws_alt.cell(row=row_i, column=4,
                            value=r["difference"]).number_format = "+#,##0;-#,##0"
                ws_alt.cell(row=row_i, column=6, value=L_alt.verdict_label(r["verdict"]))
            ws_alt.cell(row=row_i, column=5, value=f"{r['funded']} of {r['scenarios']}")
            ws_alt.cell(row=row_i, column=7, value=r["year0"]).number_format = "#,##0"
            if not r["recommendation"]:
                for col, k in ((8, "lifetime_taxes_delta"), (9, "terminal_estate_delta")):
                    ws_alt.cell(row=row_i, column=col,
                                value=src.get(k)).number_format = "+#,##0;-#,##0"
        ws_alt.cell(row=len(ranked) + 6, column=1, value=L_alt.steady_note(result, nominal))
    elif alternatives:
        from src.reports import result_labels as L

        sim = L.simulated(result)
        winner_p = wp_alt.get("success_probability") or 0
        for col_i, h in enumerate(
            [
                "Strategy",
                "Claim ages",
                L.COMPARISON,
                L.TAX_DIFF,
                L.ESTATE_DIFF,
                L.FUNDED,
                L.conversion_heading(result),
            ],
            start=1,
        ):
            c = ws_alt.cell(row=4, column=col_i, value=h)
            c.font = header_font
            c.fill = header_fill
        for row_i, alt in enumerate(alternatives, start=5):
            ws_alt.cell(row=row_i, column=1, value=L.strategy(result, alt.get("policy_id", "—")))
            if alt.get("key"):
                ws_alt.cell(row=row_i, column=2, value=L.claim_ages(
                    alt.get("claim_age_self"), alt.get("claim_age_spouse")))
            ws_alt.cell(row=row_i, column=3,
                        value=L.comparison_label(result, alt))
            c_tax = ws_alt.cell(row=row_i, column=4, value=alt.get("lifetime_taxes_delta"))
            c_tax.number_format = "+#,##0;-#,##0"
            c_est = ws_alt.cell(row=row_i, column=5, value=alt.get("terminal_estate_delta"))
            c_est.number_format = "+#,##0;-#,##0"
            # Each strategy's own share, as the page shows it; blank without
            # a simulation.
            if sim:
                c_suc = ws_alt.cell(
                    row=row_i, column=6,
                    value=winner_p + (alt.get("success_probability_delta") or 0),
                )
                c_suc.number_format = "0%"
            # Absolute, not a delta. Blank on runs saved before it was
            # reported, rather than a 0 that would read as "converts nothing".
            c_y0 = ws_alt.cell(row=row_i, column=7, value=alt.get("year0_conversion"))
            c_y0.number_format = "#,##0"
    else:
        ws_alt.cell(row=4, column=1, value="No alternative policies recorded for this run.")

    # ------------------------------------------------------------------
    # Sheet 5: Tax Audit — per-year worksheet-line derivation so any year
    # can be checked against the 1040 worksheets by hand
    # ------------------------------------------------------------------

    ws_audit = wb.create_sheet("Tax Audit")
    audits = [row.get("audit") for row in yearly_plan]

    if not yearly_plan or all(a is None for a in audits):
        ws_audit.cell(
            row=1, column=1,
            value="Tax audit data not available — this run predates audit mode.",
        )
    else:
        ws_audit.column_dimensions["A"].width = 44
        for i in range(len(yearly_plan)):
            ws_audit.column_dimensions[get_column_letter(2 + i)].width = 13

        title = ws_audit.cell(row=1, column=1, value="Tax Audit — how each year's tax was derived")
        title.font = Font(bold=True, color=_EMERALD, size=12)
        ws_audit.cell(
            row=2, column=1,
            value=(
                "Every line ties to the IRS worksheets: verify any year by hand "
                "against the 1040 instructions (see User Guide → Verifying the numbers)."
            ),
        )

        sections: list[tuple[str, list[tuple[str, str]]]] = [
            ("Ordinary income", [
                ("Salary", "salary"),
                ("Pension", "pension"),
                ("Rental", "rental"),
                ("Interest", "interest"),
                ("Ordinary dividends", "ordinary_dividends"),
                ("Traditional distributions (RMD + conversion + withdrawal)",
                 "traditional_distributions"),
                ("— of which taxable", "traditional_taxable_portion"),
                ("Net short-term capital gain", "short_term_gain"),
                ("Capital loss deduction (up to $3,000)", "capital_loss_deduction"),
                ("Social Security (gross)", "gross_social_security"),
                ("Social Security (taxable)", "taxable_social_security"),
                ("Ordinary income total", "ordinary_income"),
            ]),
            ("Preferential income", [
                ("Qualified dividends", "qualified_dividends"),
                ("Net long-term capital gain", "realized_ltcg"),
            ]),
            # Schedule D: what was netted into the two capital-gain lines
            # above. Losses are shown as positive amounts.
            ("Capital gains and losses (Schedule D)", [
                ("Short-term gain already realized (entered; − = loss)",
                 "st_gain_already_realized"),
                ("Long-term gain already realized (entered; − = loss)",
                 "lt_gain_already_realized"),
                ("Long-term gain from the plan's sales", "lt_gain_from_planned_sales"),
                ("Short-term loss carried in", "loss_carryover_in_st"),
                ("Long-term loss carried in", "loss_carryover_in_lt"),
                ("Short-term loss carried to next year", "loss_carryover_out_st"),
                ("Long-term loss carried to next year", "loss_carryover_out_lt"),
            ]),
            ("Federal (Form 1040)", [
                ("AGI", "agi"),
                ("Deduction", "deduction"),
                ("— of which senior bonus deduction", "senior_deduction"),
                ("Deduction type", "deduction_type"),
                ("Taxable income", "taxable_income"),
                # The part of taxable income sitting in the ORDINARY brackets.
                # This is the line a bracket-fill recommendation is verified
                # against: qualified dividends and long-term gains are inside
                # "Taxable income" but stack above ordinary income on their own
                # rate schedule, so only this figure can be compared to a
                # bracket's upper edge.
                ("— of which taxable ordinary income", "taxable_ordinary_income"),
                ("Tax on ordinary income", "ordinary_tax"),
                ("Tax on LTCG + qualified dividends", "ltcg_tax"),
                ("Net Investment Income Tax (NIIT)", "niit"),
                ("Federal tax", "federal_tax"),
            ]),
            ("State", [
                ("Capital loss deduction (state rules)", "state_capital_loss_deduction"),
                ("Capital loss carried to next year (state)", "state_loss_carryover_out"),
                ("State tax", "state_tax"),
            ]),
            ("Medicare", [
                ("MAGI (two years prior)", "irmaa_magi_lookback"),
                ("IRMAA surcharge", "irmaa"),
            ]),
            ("Total", [("Total tax", "total_tax")]),
        ]

        r = 4
        c = ws_audit.cell(row=r, column=1, value="Year")
        c.font = header_font
        c.fill = header_fill
        for i, year_row in enumerate(yearly_plan):
            yc = ws_audit.cell(row=r, column=2 + i, value=year_row.get("year"))
            yc.font = header_font
            yc.fill = header_fill
        r += 1

        for section_title, lines in sections:
            sc = ws_audit.cell(row=r, column=1, value=section_title)
            sc.font = section_font
            r += 1
            for label, key in lines:
                ws_audit.cell(row=r, column=1, value=label).font = Font(bold=False)
                for i, audit in enumerate(audits):
                    if audit is None:
                        continue
                    cell = ws_audit.cell(row=r, column=2 + i, value=audit.get(key))
                    if key != "deduction_type":
                        cell.number_format = "#,##0"
                r += 1

        ws_audit.freeze_panes = "B5"

    # ------------------------------------------------------------------
    # Sheet 6: Charts (native Excel charts referencing the plan sheet)
    # ------------------------------------------------------------------

    ws_charts = wb.create_sheet("Charts")
    n = len(yearly_plan)

    if n > 0:
        def _col(name: str) -> int:
            return _PLAN_COLUMNS.index(name) + 1

        def _dollar_axes(chart) -> None:
            # openpyxl leaves the axis `delete` flag unset, which some Excel
            # builds treat as hidden — axes must be explicitly visible.
            chart.x_axis.delete = False
            chart.y_axis.delete = False
            chart.y_axis.number_format = "$#,##0"

        years_ref = Reference(ws_plan, min_col=_col("year"), min_row=2, max_row=1 + n)

        def _series_ref(name: str) -> Reference:
            # min_row=1 so the header cell becomes the series title
            return Reference(
                ws_plan, min_col=_col(name), min_row=1, max_row=1 + n
            )

        # Balances line chart
        balances = LineChart()
        balances.title = "Account balances by year (steady-return projection)"
        balances.height, balances.width = 9, 18
        for series_name, color in [
            ("balance_taxable", _GOLD),
            ("balance_traditional", _EMERALD),
            ("balance_roth", _TEAL),
        ]:
            balances.add_data(_series_ref(series_name), titles_from_data=True)
            s = balances.series[-1]
            s.graphicalProperties.line.solidFill = color
            s.graphicalProperties.line.width = 22000  # ~1.75pt in EMU
        balances.set_categories(years_ref)
        _dollar_axes(balances)
        ws_charts.add_chart(balances, "A1")

        # Taxes stacked bar chart
        taxes = BarChart()
        taxes.type = "col"
        taxes.grouping = "stacked"
        taxes.overlap = 100
        taxes.title = "Annual taxes by type (steady-return projection)"
        taxes.height, taxes.width = 9, 18
        for series_name, color in [
            ("federal_tax", _EMERALD),
            ("state_tax", _GOLD),
            ("irmaa", _CLAY),
        ]:
            taxes.add_data(_series_ref(series_name), titles_from_data=True)
            taxes.series[-1].graphicalProperties.solidFill = color
        taxes.set_categories(years_ref)
        _dollar_axes(taxes)
        ws_charts.add_chart(taxes, "A20")

        # Conversions bar chart
        conversions = BarChart()
        conversions.type = "col"
        conversions.title = "Roth conversions by year (steady-return projection)"
        conversions.height, conversions.width = 9, 18
        conversions.add_data(_series_ref("conversion"), titles_from_data=True)
        conversions.series[-1].graphicalProperties.solidFill = _GOLD
        conversions.set_categories(years_ref)
        _dollar_axes(conversions)
        ws_charts.add_chart(conversions, "A39")

    # ------------------------------------------------------------------
    # Sheet: Sale Plans (per-year sell lists from the stored portfolio)
    # ------------------------------------------------------------------

    if sale_plans and sale_plans.get("years"):
        # Place right after "Yearly Plan" (index 2) so it isn't buried behind
        # the Alternatives/Tax Audit/Charts sheets and easy to miss.
        ws_sale = wb.create_sheet(
            "Sale Plan", wb.sheetnames.index("Yearly Plan") + 1
        )
        ws_sale.column_dimensions["A"].width = 8
        ws_sale.column_dimensions["B"].width = 14
        ws_sale.column_dimensions["C"].width = 10
        ws_sale.column_dimensions["D"].width = 14
        ws_sale.column_dimensions["E"].width = 14
        ws_sale.column_dimensions["F"].width = 14
        ws_sale.column_dimensions["G"].width = 14

        cap = ws_sale.cell(
            row=1,
            column=1,
            value=(
                f"Sale plan — prices as of {sale_plans['as_of']} (generated "
                f"{sale_plans.get('generated_on', sale_plans['as_of'])}). The first "
                "taxable-withdrawal year only; re-run the plan next year with "
                "a fresh portfolio to plan later sales."
            ),
        )
        cap.font = Font(italic=True, color="808080")
        ws_sale.column_dimensions["H"].width = 14
        ws_sale.column_dimensions["I"].width = 14

        headers = [
            "Year",
            "Target cash",
            "Ticker",
            "Holding",
            "Shares to sell",
            "Proceeds",
            "Realized gain",
            "Cash raised",
            "Cash short",
        ]
        for col, h in enumerate(headers, start=1):
            c = ws_sale.cell(row=3, column=col, value=h)
            c.font = header_font
            c.fill = header_fill
        r = 4
        for yr in sale_plans["years"]:
            for s in yr["sold"]:
                ws_sale.cell(row=r, column=1, value=yr["year"])
                ws_sale.cell(row=r, column=2, value=yr["target_cash"]).number_format = "$#,##0"
                ws_sale.cell(row=r, column=3, value=s["ticker"])
                ws_sale.cell(row=r, column=4, value=s["holding_period"])
                ws_sale.cell(row=r, column=5, value=round(s["shares_sold"], 3))
                ws_sale.cell(row=r, column=6, value=s["proceeds"]).number_format = "$#,##0"
                ws_sale.cell(row=r, column=7, value=s["realized_gain"]).number_format = "$#,##0"
                ws_sale.cell(
                    row=r, column=8, value=yr.get("cash_raised", yr["target_cash"])
                ).number_format = "$#,##0"
                ws_sale.cell(
                    row=r, column=9, value=yr.get("cash_short", 0)
                ).number_format = "$#,##0"
                r += 1
        # What the selector flagged: holdings that fall short, short-term
        # sales, lots treated as long-term for want of a date.
        for yr in sale_plans["years"]:
            for w in yr.get("warnings", []):
                r += 1
                ws_sale.cell(row=r, column=1, value=f"Warning ({yr['year']}): {w}").font = Font(
                    color="9C5700"
                )

    # ------------------------------------------------------------------
    # Serialize
    # ------------------------------------------------------------------

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
