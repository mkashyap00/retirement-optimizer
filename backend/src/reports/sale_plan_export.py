"""Dated Sale Plan exports (CSV and PDF).

The sale plan is a **point-in-time execution aid**: it translates one plan
year's taxable withdrawal into a specific sell list at *today's* prices. It
is deliberately separate from the permanent run reports (which record the
multi-year strategy in durable dollar terms) because a sell list is only
meaningful at the prices and holdings that exist right now — hence every
export is stamped with an "as of" date.

Both builders take the plan dict produced by
``src.api.endpoints.portfolio._compute_sale_plan`` and optional context
(spending / conversion-tax split, plan year).
"""

from __future__ import annotations

import csv
import io
from datetime import date

_SNAPSHOT_NOTE = (
    "A point-in-time snapshot at today's prices — not part of the permanent "
    "plan. Re-generate if prices have moved or your holdings changed."
)


def build_sale_plan_csv(
    plan: dict,
    *,
    as_of: date,
    spend: float | None = None,
    convtax: float | None = None,
    year: int | None = None,
) -> bytes:
    """Render the sell list as a dated CSV (UTF-8 bytes)."""
    buf = io.StringIO()
    w = csv.writer(buf)

    w.writerow(["Sale Plan"])
    w.writerow(["Prices as of", as_of.isoformat()])
    w.writerow(["Note", _SNAPSHOT_NOTE])
    w.writerow(["Profile ID", plan["profile_id"]])
    if year is not None:
        w.writerow(["Plan year", year])
    w.writerow([])

    w.writerow(["Target cash", f"{plan['target_cash']:.2f}"])
    if spend is not None:
        w.writerow(["  Funding spending", f"{spend:.2f}"])
    if convtax is not None:
        w.writerow(["  Funding Roth conversion tax", f"{convtax:.2f}"])
    w.writerow(["Cash raised", f"{plan['cash_raised']:.2f}"])
    w.writerow(["Realized long-term gain", f"{plan['realized_lt_gain']:.2f}"])
    w.writerow(["Realized short-term gain", f"{plan['realized_st_gain']:.2f}"])
    w.writerow([])

    w.writerow(
        ["Ticker", "Account", "Holding period", "Shares to sell", "Proceeds", "Realized gain"]
    )
    for s in plan["sold"]:
        w.writerow(
            [
                s["ticker"],
                s["account_type"],
                s["holding_period"],
                f"{s['shares_sold']:.3f}",
                f"{s['proceeds']:.2f}",
                f"{s['realized_gain']:.2f}",
            ]
        )

    if plan["warnings"]:
        w.writerow([])
        w.writerow(["Warnings"])
        for wn in plan["warnings"]:
            w.writerow([wn])

    return buf.getvalue().encode("utf-8")


def build_sale_plan_pdf(
    plan: dict,
    *,
    as_of: date,
    spend: float | None = None,
    convtax: float | None = None,
    year: int | None = None,
) -> bytes:
    """Render the sell list as a dated one-page PDF (raw bytes)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    def _cur(value: float) -> str:
        return f"${(value or 0):,.0f}"

    styles = getSampleStyleSheet()
    style_h1 = ParagraphStyle("SP_H1", parent=styles["Heading1"], fontSize=18, spaceAfter=4)
    style_sub = ParagraphStyle(
        "SP_sub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.grey,
        spaceAfter=10,
    )
    style_body = ParagraphStyle(
        "SP_body", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=3
    )
    style_warn = ParagraphStyle(
        "SP_warn",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#8a5a00"),
        spaceAfter=3,
    )

    story: list = []
    story.append(Paragraph("Sale Plan", style_h1))
    story.append(Paragraph(f"Prices as of {as_of.isoformat()} — {_SNAPSHOT_NOTE}", style_sub))

    if year is not None:
        story.append(Paragraph(f"<b>Funds plan year:</b> {year}", style_body))
    story.append(Paragraph(f"<b>Target cash:</b> {_cur(plan['target_cash'])}", style_body))
    if spend is not None:
        story.append(Paragraph(f"&nbsp;&nbsp;Funding spending: {_cur(spend)}", style_body))
    if convtax is not None:
        story.append(
            Paragraph(f"&nbsp;&nbsp;Funding Roth conversion tax: {_cur(convtax)}", style_body)
        )
    story.append(Paragraph(f"<b>Cash raised:</b> {_cur(plan['cash_raised'])}", style_body))
    story.append(
        Paragraph(
            f"<b>Realized gains:</b> {_cur(plan['realized_lt_gain'])} long-term, "
            f"{_cur(plan['realized_st_gain'])} short-term",
            style_body,
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    header = ["Ticker", "Account", "Holding", "Shares", "Proceeds", "Realized gain"]
    data = [header]
    for s in plan["sold"]:
        data.append(
            [
                s["ticker"],
                s["account_type"],
                s["holding_period"].replace("_", "-"),
                f"{s['shares_sold']:,.3f}",
                _cur(s["proceeds"]),
                _cur(s["realized_gain"]),
            ]
        )
    if len(data) == 1:
        data.append(["—", "—", "—", "—", "—", "—"])

    table = Table(data, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe9d8")),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ded7c2")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)

    if plan["warnings"]:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("<b>Warnings</b>", style_body))
        for wn in plan["warnings"]:
            safe = wn.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(f"• {safe}", style_warn))

    story.append(Spacer(1, 0.6 * cm))
    story.append(
        Paragraph(
            f"Profile ID: {plan['profile_id']}",
            ParagraphStyle(
                "SP_foot", parent=styles["Normal"], fontSize=7, textColor=colors.grey
            ),
        )
    )

    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Sale Plan",
    )
    doc.build(story)
    return out.getvalue()
