"""PDF report generation for retirement optimization results.

Provides `build_pdf(result, household) -> bytes` using ReportLab.

Document structure:
  1. Title page — heading, household summary, run date.
  2. Strategy summary — winning policy stats (taxes, estate, probability).
  3. Most consequential years table — top 10 by conversion descending.
  4. Full-year plan table — all rows (portrait, 9 compact columns).
  5. Narratives appendix — per-year paragraphs for conversion years + first RMD year.
"""

from __future__ import annotations

import io
from datetime import date


def build_pdf(
    result: dict,
    household: dict,
    inputs: dict | None = None,
    advisor_text: str | None = None,
    sale_plans: dict | None = None,
) -> bytes:
    """Build a retirement optimization PDF report.

    Args:
        result: Optimization result dict with keys:
            - winning_policy: dict with policy_id, lifetime_taxes_nominal,
              lifetime_taxes_pv, terminal_estate, success_probability, score,
              total_conversions, projected_future_marginal_rate
            - yearly_plan: list of year dicts (see csv_export.py for schema)
            - warnings: list of warning strings
        household: dict with keys:
            - filing_status: str (e.g. "joint", "single")
            - state: str (e.g. "CA")
            - run_date: str (ISO date, e.g. "2026-07-05")
        inputs: optional input snapshot taken when the run was created
            (household / accounts / income / settings / constraints, the
            GET /households/{id} payload shape).  When present, an
            "Inputs Used for This Run" section is included.

    Returns:
        Raw PDF bytes (starts with b'%PDF').
    """
    # Defer import so the module is importable even if reportlab is missing
    # (though it is a listed dependency).
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cur(value: float) -> str:
        """Format as compact currency (e.g. $1,200,000)."""
        value = 0 if value is None else value
        return f"${value:,.0f}"

    def _pct(value: float) -> str:
        """Format as percentage (e.g. 92.0%)."""
        value = 0 if value is None else value
        return f"{value * 100:.1f}%"

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]
    style_h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=22,
        spaceAfter=12,
    )
    style_h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=14,
    )
    style_body = ParagraphStyle(
        "Body",
        parent=style_normal,
        fontSize=9,
        leading=13,
        spaceAfter=6,
    )
    style_table_header = ParagraphStyle(
        "TableHeader",
        parent=style_normal,
        fontSize=8,
        fontName="Helvetica-Bold",
    )
    style_narrative = ParagraphStyle(
        "Narrative",
        parent=style_normal,
        fontSize=8,
        leading=12,
        leftIndent=12,
        spaceAfter=4,
    )

    # ------------------------------------------------------------------
    # Table styling helpers
    # ------------------------------------------------------------------

    HEADER_BG = colors.HexColor("#2E4057")
    ALT_BG = colors.HexColor("#F5F7FA")

    def _base_table_style() -> list:
        """Return a base TableStyle list for tables."""
        ts = [
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT_BG]),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),  # first col centred
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        return ts

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    from src.reports.assumption_labels import objective_row, ss_cola_label, tax_tables_label
    from src.reports.display import blank_ages_after_death

    wp = result.get("winning_policy", {})
    yearly_plan = blank_ages_after_death(result.get("yearly_plan", []), inputs)
    warnings = result.get("warnings", [])

    filing_status = household.get("filing_status", "—").replace("_", " ").title()
    state = household.get("state", "—")
    run_date = household.get("run_date", str(date.today()))
    run_id = household.get("run_id")
    household_id = household.get("household_id")

    # ------------------------------------------------------------------
    # Document setup — portrait A4, with a landscape page template
    # ------------------------------------------------------------------

    buf = io.BytesIO()

    # We use BaseDocTemplate so we can define multiple page templates.
    PAGE_W, PAGE_H = A4  # 595 x 842 pts
    LAND_W, LAND_H = landscape(A4)  # 842 x 595 pts

    MARGIN = 2 * cm

    portrait_frame = Frame(
        MARGIN, MARGIN, PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN, id="portrait"
    )
    landscape_frame = Frame(
        MARGIN, MARGIN, LAND_W - 2 * MARGIN, LAND_H - 2 * MARGIN, id="landscape"
    )

    portrait_tpl = PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4)
    landscape_tpl = PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape(A4))

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        pageTemplates=[portrait_tpl, landscape_tpl],
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Retirement Optimization Report",
    )

    story: list = []

    # ------------------------------------------------------------------
    # Section 1: Title page
    # ------------------------------------------------------------------

    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("Retirement Optimization Report", style_h1))
    story.append(Spacer(1, 0.5 * cm))

    summary_data = [
        ("Filing status:", filing_status),
        ("State:", state),
        ("Run date:", run_date),
    ]
    if run_id:
        summary_data.append(("Run ID:", run_id))
    if household_id:
        summary_data.append(("Household ID:", household_id))
    for label, value in summary_data:
        story.append(
            Paragraph(f"<b>{label}</b> {value}", style_body)
        )

    if warnings:
        story.append(Spacer(1, 0.5 * cm))
        for w in warnings:
            story.append(Paragraph(f"<font color='red'>Warning: {w}</font>", style_body))

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # Section 1a: Advisor Commentary (LLM-generated, stored with the run;
    # present only after the user generates it from the results page)
    # ------------------------------------------------------------------

    if advisor_text:
        story.append(Paragraph("Advisor Commentary", style_h2))
        story.append(
            Paragraph(
                "AI-generated commentary based solely on the figures in this "
                "report. Not financial or tax advice.",
                style_body,
            )
        )
        story.append(Spacer(1, 0.3 * cm))
        escaped = (
            advisor_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        for para in escaped.split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para, style_body))
                story.append(Spacer(1, 0.15 * cm))
        story.append(PageBreak())

    # ------------------------------------------------------------------
    # Section 1b: Inputs snapshot (when the run carries one)
    # ------------------------------------------------------------------

    from src.reports import result_labels as L

    if inputs:
        story.append(Paragraph("Inputs Used for This Run", style_h2))

        hh_in = inputs.get("household", {})
        hh_items = [
            ("Filing status", hh_in.get("filing_status", "—")),
            ("Your birth date", hh_in.get("self_birth_date", "—")),
        ]
        if hh_in.get("spouse_birth_date"):
            hh_items.append(("Spouse birth date", hh_in["spouse_birth_date"]))
        hh_items.append(("State", hh_in.get("state", "—")))
        if hh_in.get("self_death_age") is not None:
            hh_items.append(("Plan to age", str(hh_in["self_death_age"])))
        for label, value in hh_items:
            story.append(Paragraph(f"<b>{label}:</b> {value}", style_body))

        accounts_in = inputs.get("accounts", [])
        if accounts_in:
            story.append(Paragraph("Accounts", style_h2))
            acc_rows = [["Type", "Owner", "Balance", "Basis"]] + [
                [
                    a.get("account_type", "—"),
                    a.get("owner", "—"),
                    _cur(a.get("balance", 0)),
                    _cur(a["basis"]) if a.get("basis") is not None else "—",
                ]
                for a in accounts_in
            ]
            t = Table(acc_rows, hAlign="LEFT")
            t.setStyle(TableStyle(_base_table_style()))
            story.append(t)

        income_in = inputs.get("income", [])
        settings_in = inputs.get("settings", {})
        story.append(Paragraph("Income &amp; Social Security", style_h2))
        if income_in:
            inc_rows = [["Category", "Owner", "Amount/yr", "Years"]] + [
                [
                    i.get("category", "—"),
                    i.get("owner", "—"),
                    _cur(i.get("amount", 0)),
                    f"{i.get('start_year') or '…'}–{i.get('end_year') or '…'}",
                ]
                for i in income_in
            ]
            t = Table(inc_rows, hAlign="LEFT")
            t.setStyle(TableStyle(_base_table_style()))
            story.append(t)
        else:
            story.append(Paragraph("No income sources.", style_body))
        if settings_in.get("ss_pia_self") is not None:
            claim_self = settings_in.get("ss_claim_age_self")
            story.append(
                Paragraph(
                    f"<b>Social Security (self):</b> {_cur(settings_in['ss_pia_self'])}/mo"
                    + (f", claim at {claim_self}" if claim_self is not None else ""),
                    style_body,
                )
            )
        if settings_in.get("ss_pia_spouse") is not None:
            claim_spouse = settings_in.get("ss_claim_age_spouse")
            story.append(
                Paragraph(
                    f"<b>Social Security (spouse):</b> {_cur(settings_in['ss_pia_spouse'])}/mo"
                    + (f", claim at {claim_spouse}" if claim_spouse is not None else ""),
                    style_body,
                )
            )

        constraints_in = inputs.get("constraints", {})
        story.append(Paragraph("Assumptions", style_h2))
        _rule = settings_in.get("spending_rule") or "fixed"
        assumption_items = [
            ("Annual spending", _cur(settings_in.get("required_spending", 0))),
            ("Inflation", _pct(settings_in.get("inflation", 0))),
            ("Social Security COLA", ss_cola_label(settings_in)),
            ("Tax tables", tax_tables_label(result)),
            ("Nominal return", _pct(settings_in.get("nominal_return", 0))),
            # What the run optimized: the objective id for new runs, the stored
            # priority for runs scored under the old taxes-vs-estate objective.
            objective_row(result, settings_in),
            # Dynamic spending. Always stated, including the default: a reader
            # holding this report needs to know whether the plan assumed
            # spending was rigid, because it changes what every figure means.
            (
                "If markets go badly",
                "Cut back, then recover (guardrails)"
                if _rule == "guardrails"
                else "Keep spending the same",
            ),
        ]
        if settings_in.get("spending_floor") is not None:
            assumption_items.append(
                ("Essential spending floor", _cur(settings_in["spending_floor"]))
            )
        if constraints_in.get("irmaa_policy"):
            assumption_items.append((L.IRMAA_HEADING, L.IRMAA_LABEL.get(
                constraints_in["irmaa_policy"], constraints_in["irmaa_policy"])))
        if constraints_in.get("conversion_window"):
            assumption_items.append(
                ("Conversion window", constraints_in["conversion_window"])
            )
        if constraints_in.get("preserve_taxable") is not None:
            assumption_items.append(
                ("Preserve taxable", "yes" if constraints_in["preserve_taxable"] else "no")
            )
        for label, value in assumption_items:
            story.append(Paragraph(f"<b>{label}:</b> {value}", style_body))

        story.append(PageBreak())

    # ------------------------------------------------------------------
    # Section 2: Strategy summary
    # ------------------------------------------------------------------

    story.append(Paragraph("Strategy Summary", style_h2))

    from src.reports import result_labels as L
    from src.reports.display import strategy_heading, success_interval_hint, years_reduced_note

    success = L.NO_SIMULATION
    if L.simulated(result):
        p = wp.get("success_probability", 0) or 0
        hint = success_interval_hint(p, wp.get("monte_carlo_paths", result.get("monte_carlo_runs")))
        note = years_reduced_note(wp.get("mean_years_reduced"))
        success = f"{p * 100:.0f}%" + (f" ({hint})" if hint else "") + (f". {note}" if note else "")
    summary_items = [
        # The strategy's name, as the Results page and Excel show it — this
        # read "Policy ID: fill_10_annual".
        (strategy_heading(result), L.strategy(result, wp.get("policy_id", "—"))),
        (L.TAXES, _cur(wp.get("lifetime_taxes_nominal", 0))),
        (L.TAXES_PV, _cur(wp.get("lifetime_taxes_pv", 0))),
        (L.ESTATE, _cur(wp.get("terminal_estate", 0)) + " (final-year dollars)"),
        (L.SUCCESS, success),
        (L.score_label(result), _cur(wp.get("score", 0))),
        ("Total Roth conversions", _cur(wp.get("total_conversions", 0))),
        ("Projected future marginal rate", _pct(wp.get("projected_future_marginal_rate", 0))),
    ]
    from src.reports import claim_search

    summary_items += claim_search.summary_rows(result)

    for label, value in summary_items:
        story.append(Paragraph(f"<b>{label}:</b> {value}", style_body))

    # How the market scenarios were drawn, from the run's own record.
    story.append(Paragraph(
        "<b>How we simulate market outcomes</b>" if L.simulated(result)
        else f"<b>{L.NO_SIMULATION}</b>", style_body))
    nominal = ((inputs or {}).get("settings") or {}).get("nominal_return")
    for sentence in L.market_explanation(result, nominal):
        story.append(Paragraph(sentence, style_body))

    story.append(Spacer(1, 0.5 * cm))

    # ------------------------------------------------------------------
    # Section 2a: Alternative policies (record of what the search rejected)
    # ------------------------------------------------------------------

    alternatives = result.get("alternative_policies", [])
    if alternatives:
        def _signed_cur(value: float) -> str:
            value = 0 if value is None else value
            sign = "+" if value > 0 else "-" if value < 0 else ""
            return f"{sign}${abs(value):,.0f}"

        from src.reports import result_labels as L

        sim = L.simulated(result)
        winner_p = wp.get("success_probability") or 0
        story.append(Paragraph("Close alternatives", style_h2))
        ranked = L.ranking_rows(result)
        nominal = ((inputs or {}).get("settings") or {}).get("nominal_return")

        def _alt_name(alt: dict) -> str:
            return (L.candidate(alt.get("policy_id", "—"), alt.get("claim_age_self"),
                                alt.get("claim_age_spouse"), L.start_traditional(result))
                    if alt.get("key") else L.strategy(result, alt.get("policy_id", "—")))

        def _y0(v) -> str:
            # Absolute first-year conversion; "—" on runs saved before it
            # was reported, rather than a $0 that would mean "converts nothing".
            return f"${v:,.0f}" if v is not None else "—"

        if ranked:
            # The measurement that ranked them leads; the steady-return
            # deltas follow, labelled, because alone they can make a
            # lower-ranked strategy look better.
            story.append(Paragraph(L.ranking_note(ranked), style_body))
            close = L.close_call_sentence(result)
            if close:
                story.append(Paragraph(f"<b>{close}</b>", style_body))
            show_y0 = any((r["year0"] or 0) > 0 for r in ranked)
            head = ["Strategy", L.SCORE_AVG, L.DIFF, L.FUNDED, L.COMPARISON]
            if show_y0:
                head.append(L.conversion_heading(result))
            rank_rows = [[Paragraph(h, style_table_header) for h in head]]
            for r in ranked:
                row = [
                    Paragraph(r["name"] + (" — Recommendation" if r["recommendation"] else ""),
                              style_body),
                    f"${r['score']:,.0f}" if r["score"] is not None else "—",
                    "—" if r["recommendation"] else _signed_cur(r["difference"]),
                    f"{r['funded']} of {r['scenarios']}",
                    Paragraph("—" if r["recommendation"] else L.verdict_label(r["verdict"]),
                              style_body),
                ]
                if show_y0:
                    row.append(_y0(r["year0"]))
                rank_rows.append(row)
            widths = ([5.4, 2.6, 2.6, 2.4, 2.6, 1.6] if show_y0 else [6.4, 2.8, 2.8, 2.4, 2.8])
            t = Table(rank_rows, colWidths=[w * cm for w in widths], hAlign="LEFT")
            t.setStyle(TableStyle(_base_table_style()))
            story.append(t)
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph(f"<b>{L.steady_title(result, nominal)}</b>", style_body))
            story.append(Paragraph(L.steady_note(result, nominal), style_body))
            steady_rows = [[Paragraph(h, style_table_header)
                            for h in ("Strategy", L.TAX_DIFF, L.ESTATE_DIFF)]]
            for alt in alternatives:
                steady_rows.append([
                    Paragraph(_alt_name(alt), style_body),
                    _signed_cur(alt.get("lifetime_taxes_delta", 0)),
                    _signed_cur(alt.get("terminal_estate_delta", 0)),
                ])
            t = Table(steady_rows, colWidths=[9.4 * cm, 3.8 * cm, 3.8 * cm], hAlign="LEFT")
            t.setStyle(TableStyle(_base_table_style()))
            story.append(t)
            if show_y0:
                story.append(Paragraph(L.conversion_note(result), style_body))
            story.append(Spacer(1, 0.5 * cm))
        else:
            alt_rows = [[
                Paragraph("Strategy", style_table_header),
                Paragraph(L.COMPARISON, style_table_header),
                Paragraph(L.TAX_DIFF, style_table_header),
                Paragraph(L.ESTATE_DIFF, style_table_header),
                Paragraph(L.FUNDED, style_table_header),
                Paragraph(L.conversion_heading(result), style_table_header),
            ]]
            for alt in alternatives:
                alt_rows.append([
                    Paragraph(_alt_name(alt), style_body),
                    Paragraph(L.comparison_label(result, alt), style_body),
                    _signed_cur(alt.get("lifetime_taxes_delta", 0)),
                    _signed_cur(alt.get("terminal_estate_delta", 0)),
                    (f"{(winner_p + (alt.get('success_probability_delta') or 0)) * 100:.0f}%"
                     if sim else "—"),
                    _y0(alt.get("year0_conversion")),
                ])
            t = Table(
                alt_rows,
                colWidths=[5.0 * cm, 3.0 * cm, 2.6 * cm, 2.4 * cm, 2.2 * cm, 2.0 * cm],
                hAlign="LEFT",
            )
            t.setStyle(TableStyle(_base_table_style()))
            story.append(t)
            story.append(
                Paragraph(
                    f"{L.ALTERNATIVES_NOTE} {L.conversion_note(result)} Tax and estate "
                    "differences come from the steady-return projection; scenarios with "
                    "spending funded is each strategy's own share of the market scenarios. "
                    "The recommendation is ranked on the modeled score, not on any one of "
                    "these columns.",
                    style_body,
                )
            )
            story.append(Spacer(1, 0.5 * cm))

    # ------------------------------------------------------------------
    # Section 2a': Claim-age search (joint runs only)
    # ------------------------------------------------------------------

    joint_tables = claim_search.tables(result)
    if joint_tables:
        story.append(Paragraph(claim_search.SECTION, style_h2))

        style_cell = ParagraphStyle("ClaimCell", parent=style_normal, fontSize=7, leading=9)

        def _cell(v: object) -> object:
            if isinstance(v, bool):
                return "yes" if v else "no"
            if isinstance(v, claim_search.Money):
                return f"${v:,.0f}" if v >= 0 else f"-${-v:,.0f}"
            if isinstance(v, claim_search.Share):
                return f"{v * 100:.0f}%"
            if isinstance(v, str) and len(v) > 10:
                # Strategy names and labels wrap inside their column.
                return Paragraph(v, style_cell)
            return "" if v is None else str(v)

        def _widths(header: list, rows: list) -> list:
            # Text columns (strategy names, labels) get more of the 17 cm.
            def texty(i: int) -> bool:
                return any(isinstance(r[i], str) and len(r[i]) > 10 for r in rows)
            # A number column is at least as wide as its longest header word.
            weights = [2.4 if texty(i) else max(1.5, max(map(len, h.split()), default=0) / 5)
                       for i, h in enumerate(header)]
            return [17 * cm * w / sum(weights) for w in weights]

        for title, header, rows, note in joint_tables:
            story.append(Paragraph(f"<b>{title}</b>", style_body))
            if note:
                story.append(Paragraph(note, style_body))
            data = [[Paragraph(h, style_table_header) for h in header]]
            data += [[_cell(v) for v in row] for row in rows]
            t = Table(data, hAlign="LEFT", repeatRows=1, colWidths=_widths(header, rows))
            t.setStyle(TableStyle(_base_table_style()))
            story.append(t)
            story.append(Spacer(1, 0.3 * cm))

    # ------------------------------------------------------------------
    # Section 2b: Charts (balances, taxes, conversions)
    # ------------------------------------------------------------------

    if yearly_plan:
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.legends import Legend
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.shapes import Drawing, String

        C_EMERALD = colors.HexColor("#064E3B")
        C_GOLD = colors.HexColor("#C9A84C")
        C_TEAL = colors.HexColor("#0D9488")
        C_CLAY = colors.HexColor("#B4552D")

        years = [r.get("year", 0) for r in yearly_plan]
        # Sparse x labels (every 5th year) so 30-year plans stay legible
        cat_names = [
            str(y) if i % 5 == 0 or i == len(years) - 1 else ""
            for i, y in enumerate(years)
        ]

        CHART_W, CHART_H = 15 * cm, 5.5 * cm

        def _chart_drawing(
            title: str,
            chart,
            series_labels: list[tuple[str, object]],
        ) -> Drawing:
            """Wrap a chart in a Drawing with a title and legend."""
            d = Drawing(CHART_W, CHART_H + 1.6 * cm)
            chart.x, chart.y = 1.2 * cm, 0.7 * cm
            chart.width, chart.height = CHART_W - 2 * cm, CHART_H - 0.4 * cm
            d.add(
                String(
                    0, CHART_H + 1.0 * cm, title,
                    fontName="Helvetica-Bold", fontSize=11, fillColor=C_EMERALD,
                )
            )
            d.add(chart)
            if len(series_labels) > 1:
                legend = Legend()
                legend.x, legend.y = CHART_W - 4.2 * cm, CHART_H + 0.9 * cm
                legend.alignment = "right"
                legend.fontSize = 7
                legend.columnMaximum = 1
                legend.colorNamePairs = [(c, n) for n, c in series_labels]
                d.add(legend)
            return d

        # Balances line chart
        lc = HorizontalLineChart()
        lc.data = [
            [r.get("balance_taxable", 0) for r in yearly_plan],
            [r.get("balance_traditional", 0) for r in yearly_plan],
            [r.get("balance_roth", 0) for r in yearly_plan],
        ]
        lc.categoryAxis.categoryNames = cat_names
        lc.categoryAxis.labels.fontSize = 6
        lc.valueAxis.labels.fontSize = 6
        lc.valueAxis.valueMin = 0
        lc.lines[0].strokeColor = C_GOLD
        lc.lines[1].strokeColor = C_EMERALD
        lc.lines[2].strokeColor = C_TEAL
        for i in range(3):
            lc.lines[i].strokeWidth = 1.5
        story.append(
            _chart_drawing(
                "Account balances by year (steady-return projection)", lc,
                [("Taxable", C_GOLD), ("Traditional", C_EMERALD), ("Roth", C_TEAL)],
            )
        )
        story.append(Spacer(1, 0.4 * cm))

        # Taxes stacked bar chart
        tax_bc = VerticalBarChart()
        tax_bc.data = [
            [r.get("federal_tax", 0) for r in yearly_plan],
            [r.get("state_tax", 0) for r in yearly_plan],
            [r.get("irmaa", 0) for r in yearly_plan],
        ]
        tax_bc.categoryAxis.style = "stacked"
        tax_bc.categoryAxis.categoryNames = cat_names
        tax_bc.categoryAxis.labels.fontSize = 6
        tax_bc.valueAxis.labels.fontSize = 6
        tax_bc.valueAxis.valueMin = 0
        tax_bc.bars[0].fillColor = C_EMERALD
        tax_bc.bars[1].fillColor = C_GOLD
        tax_bc.bars[2].fillColor = C_CLAY
        story.append(
            _chart_drawing(
                "Annual taxes by type (steady-return projection)", tax_bc,
                [("Federal", C_EMERALD), ("State", C_GOLD), ("IRMAA", C_CLAY)],
            )
        )
        story.append(PageBreak())

        # Conversions bar chart
        conv_bc = VerticalBarChart()
        conv_bc.data = [[r.get("conversion", 0) for r in yearly_plan]]
        conv_bc.categoryAxis.categoryNames = cat_names
        conv_bc.categoryAxis.labels.fontSize = 6
        conv_bc.valueAxis.labels.fontSize = 6
        conv_bc.valueAxis.valueMin = 0
        conv_bc.bars[0].fillColor = C_GOLD
        story.append(
            _chart_drawing("Roth conversions by year (steady-return projection)", conv_bc,
                           [("Conversion", C_GOLD)])
        )
        story.append(Spacer(1, 0.5 * cm))

    # ------------------------------------------------------------------
    # Section 3: Most consequential years (top 10 by conversion desc)
    # ------------------------------------------------------------------

    story.append(Paragraph("Most Consequential Years (Top 10 by Conversion)", style_h2))

    conversion_years = sorted(
        yearly_plan, key=lambda r: r.get("conversion", 0), reverse=True
    )[:10]

    if conversion_years:
        top10_header = [
            Paragraph("Year", style_table_header),
            Paragraph("Age", style_table_header),
            Paragraph("Conversion", style_table_header),
            Paragraph("Total Tax", style_table_header),
            Paragraph("Marginal %", style_table_header),
        ]
        top10_rows = [top10_header]
        for row in conversion_years:
            top10_rows.append([
                str(row.get("year", "")),
                str(row.get("age_self") if row.get("age_self") is not None else ""),
                _cur(row.get("conversion", 0)),
                _cur(row.get("total_tax", 0)),
                _pct(row.get("marginal_rate", 0)),
            ])

        col_widths = [2 * cm, 2 * cm, 4 * cm, 4 * cm, 3 * cm]
        t = Table(top10_rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle(_base_table_style()))
        story.append(t)
    else:
        story.append(Paragraph("No conversion years in this plan.", style_body))

    # ------------------------------------------------------------------
    # Section 4: Full-year plan table (landscape)
    # ------------------------------------------------------------------

    # NextPageTemplate + a SINGLE PageBreak both ends this section and switches
    # to the landscape template. A second PageBreak here (before the template
    # switch) would flush an empty portrait page first — the stray blank page
    # that used to appear between the Roth conversions chart and "Full N-Year
    # Plan".
    story.append(NextPageTemplate("landscape"))
    story.append(PageBreak())

    sim_years = len(yearly_plan)
    story.append(Paragraph(f"Full {sim_years}-Year Plan", style_h2))

    # Determine if any row has a spouse age
    has_spouse_age = any(row.get("age_spouse") is not None for row in yearly_plan)
    # "Below Target" earns its column only when some year actually came in
    # under the goal. Since Step 4 the table runs past depletion, so without it
    # a reader watches Net Spend collapse for ten years with no explanation on
    # the page. Guardrail cuts and hard shortfalls share the column: on paper,
    # one honest "you got less than you asked for" number beats two sparse
    # ones, and the Assumptions page already says which rule was in force.
    def _below_target(row: dict) -> float:
        target = row.get("target_spending")
        if target is None:
            return 0.0
        return max(0.0, float(target) - float(row.get("net_spendable", 0)))

    has_gap = any(_below_target(row) > 1 for row in yearly_plan)
    num_full_cols = (10 if has_spouse_age else 9) + (1 if has_gap else 0)

    full_header = [
        Paragraph("Year", style_table_header),
        Paragraph("Age", style_table_header),
    ]
    if has_spouse_age:
        full_header.append(Paragraph("Sp.Age", style_table_header))
    full_header += [
        Paragraph("Conversion", style_table_header),
        Paragraph("Total Tax", style_table_header),
        Paragraph("Eff %", style_table_header),
        Paragraph("Marg %", style_table_header),
        Paragraph("Net Spend", style_table_header),
    ]
    if has_gap:
        full_header.append(Paragraph("Below Target", style_table_header))
    full_header += [
        Paragraph("Trad Bal", style_table_header),
        Paragraph("Roth Bal", style_table_header),
    ]

    full_rows = [full_header]
    for row in yearly_plan:
        data_row = [
            str(row.get("year", "")),
            str(row.get("age_self") if row.get("age_self") is not None else ""),
        ]
        if has_spouse_age:
            sp_age = row.get("age_spouse")
            data_row.append(str(sp_age) if sp_age is not None else "")
        data_row += [
            _cur(row.get("conversion", 0)),
            _cur(row.get("total_tax", 0)),
            _pct(row.get("effective_rate", 0)),
            _pct(row.get("marginal_rate", 0)),
            _cur(row.get("net_spendable", 0)),
        ]
        if has_gap:
            gap = _below_target(row)
            data_row.append(_cur(gap) if gap > 1 else "")
        data_row += [
            _cur(row.get("balance_traditional", 0)),
            _cur(row.get("balance_roth", 0)),
        ]
        full_rows.append(data_row)

    # Landscape usable width: LAND_W - 2*MARGIN = 842 - 4*28.35 ~ 728 pts
    LAND_USABLE = LAND_W - 2 * MARGIN
    col_w = LAND_USABLE / num_full_cols
    full_col_widths = [col_w] * num_full_cols

    ft = Table(full_rows, colWidths=full_col_widths, repeatRows=1)
    ft.setStyle(TableStyle(_base_table_style()))
    story.append(ft)

    # ------------------------------------------------------------------
    # Section 5: Narratives appendix (portrait)
    # ------------------------------------------------------------------

    story.append(NextPageTemplate("portrait"))
    story.append(PageBreak())

    story.append(Paragraph("Narratives Appendix", style_h2))
    story.append(
        Paragraph(
            "Per-year rationale for conversion years and the first RMD year.",
            style_body,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    # Find conversion years and first RMD year
    first_rmd_year: int | None = None
    narrative_rows = []
    for row in yearly_plan:
        is_conversion = row.get("conversion", 0) > 0
        is_rmd = row.get("rmd", 0) > 0
        if is_rmd and first_rmd_year is None:
            first_rmd_year = row.get("year")
        if is_conversion or row.get("year") == first_rmd_year:
            narrative_rows.append(row)

    if narrative_rows:
        for row in narrative_rows:
            year = row.get("year", "")
            age = row.get("age_self") if row.get("age_self") is not None else "—"
            rationale = row.get("rationale", {}) or {}
            narrative = rationale.get("narrative", "") if isinstance(rationale, dict) else ""
            label = f"<b>{year} (age {age})</b>"
            if row.get("rmd", 0) > 0 and row.get("year") == first_rmd_year:
                label += " — first RMD year"
            story.append(Paragraph(label, style_body))
            if narrative:
                story.append(Paragraph(narrative, style_narrative))
            else:
                story.append(Paragraph("No narrative recorded.", style_narrative))
            story.append(Spacer(1, 0.2 * cm))
    else:
        story.append(Paragraph("No conversion or RMD years in this plan.", style_body))

    # ------------------------------------------------------------------
    # Section: Sale Plans (per-year sell lists from the stored portfolio)
    # ------------------------------------------------------------------

    if sale_plans and sale_plans.get("years"):
        story.append(PageBreak())
        story.append(Paragraph("Sale Plan", style_h2))
        story.append(
            Paragraph(
                f"Sell list for the first taxable-withdrawal year, priced as of "
                f"{sale_plans['as_of']} (generated "
                f"{sale_plans.get('generated_on', sale_plans['as_of'])}). This is an "
                "annual tool — re-run the plan next year with a fresh portfolio to "
                "plan later sales.",
                style_body,
            )
        )
        for yr in sale_plans["years"]:
            short = yr.get("cash_short", 0)
            story.append(
                Paragraph(
                    f"<b>{yr['year']}</b> — raise {_cur(yr['target_cash'])}"
                    + (
                        f"; the holdings raise only {_cur(yr['cash_raised'])}, "
                        f"<b>{_cur(short)} short</b>"
                        if short > 0
                        else ""
                    ),
                    style_body,
                )
            )
            for w in yr.get("warnings", []):
                story.append(Paragraph(f"<i>Warning: {w}</i>", style_body))
            data = [["Ticker", "Holding", "Shares", "Proceeds", "Realized gain"]]
            for s in yr["sold"]:
                data.append(
                    [
                        s["ticker"],
                        s["holding_period"].replace("_", "-"),
                        f"{s['shares_sold']:,.3f}",
                        _cur(s["proceeds"]),
                        _cur(s["realized_gain"]),
                    ]
                )
            if len(data) == 1:
                data.append(["—", "—", "—", "—", "—"])
            t = Table(data, repeatRows=1, hAlign="LEFT")
            t.setStyle(
                TableStyle(
                    [
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe9d8")),
                        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ded7c2")),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 0.3 * cm))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    doc.build(story)
    return buf.getvalue()
