"""Unit tests for PDF export functionality.

TDD RED phase — tests written BEFORE implementation.

Test cases:
  (1) build_pdf returns bytes starting with b'%PDF'
  (2) len(build_pdf(...)) > 5 KB for a 30-year fixture
  (3) build_pdf accepts a minimal 1-year fixture without error
  (4) build_pdf includes strategy summary content (covered by >5KB length check)
"""

from __future__ import annotations

import io

from src.reports.pdf_export import build_pdf

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_year_row(year: int, age: int, conversion: float = 0.0) -> dict:
    """Return a realistic yearly_plan row dict."""
    base_agi = 80000.0 + conversion
    return {
        "year": year,
        "age_self": age,
        "conversion": conversion,
        "withdrawal_taxable": 20000.0,
        "withdrawal_traditional": 40000.0,
        "withdrawal_roth": 10000.0,
        "rmd": 0.0 if age < 73 else 25000.0,
        "agi": base_agi,
        "magi": base_agi + 2000.0,
        "federal_tax": base_agi * 0.12,
        "state_tax": base_agi * 0.06,
        "irmaa": 0.0,
        "total_tax": base_agi * 0.18,
        "effective_rate": 0.18,
        "marginal_rate": 0.22,
        "net_spendable": 70000.0,
        "required_spending": 90000.0,
        "balance_taxable": max(0.0, 300000.0 - (year - 2026) * 5000),
        "balance_traditional": max(0.0, 800000.0 - (year - 2026) * 10000),
        "balance_roth": 100000.0 + conversion * 0.9,
        "rationale": {
            "narrative": (
                f"Year {year}: Converting ${conversion:,.0f} to fill the 22% bracket."
                if conversion > 0
                else f"Year {year}: Standard withdrawal, no conversion this year."
            )
        },
    }


def _fixture_30year_result() -> dict:
    """Return a result dict with a 30-year yearly_plan and winning_policy."""
    rows = []
    for i in range(30):
        year = 2026 + i
        age = 66 + i
        # Convert in years 0-9 (pre-RMD window), tapering off
        conversion = max(0.0, 50000.0 - i * 5000.0)
        rows.append(_make_year_row(year, age, conversion))

    return {
        "winning_policy": {
            "policy_id": "policy_roth_ladder_heavy",
            "lifetime_taxes_nominal": 420000.0,
            "lifetime_taxes_pv": 310000.0,
            "terminal_estate": 1200000.0,
            "success_probability": 0.92,
            "score": 0.87,
            "total_conversions": 275000.0,
            "projected_future_marginal_rate": 0.28,
        },
        "yearly_plan": rows,
        "alternative_policies": [
            {
                "policy_id": "fill_22",
                "lifetime_taxes_delta": -211734.0,
                "terminal_estate_delta": -237321.0,
                "success_probability_delta": 0.06,
            },
        ],
        "warnings": ["Portfolio may be insufficient for a 35-year horizon"],
    }


def _fixture_household() -> dict:
    """Return a household dict as the PDF route will pass it."""
    return {
        "filing_status": "joint",
        "state": "CA",
        "run_date": "2026-07-05",
    }


# ---------------------------------------------------------------------------
# Test (1): bytes start with %PDF magic
# ---------------------------------------------------------------------------


def test_pdf_bytes_start_with_pdf_magic():
    """build_pdf returns bytes whose first 4 bytes are b'%PDF'."""
    result = _fixture_30year_result()
    household = _fixture_household()
    pdf_bytes = build_pdf(result, household)

    assert isinstance(pdf_bytes, bytes), f"Expected bytes, got {type(pdf_bytes)}"
    assert pdf_bytes[:4] == b"%PDF", (
        f"Expected PDF magic header, got {pdf_bytes[:8]!r}"
    )


# ---------------------------------------------------------------------------
# Test (2): length > 5 KB
# ---------------------------------------------------------------------------


def test_pdf_length_exceeds_5kb():
    """build_pdf produces a PDF > 5 KB for a 30-year fixture."""
    result = _fixture_30year_result()
    household = _fixture_household()
    pdf_bytes = build_pdf(result, household)

    assert len(pdf_bytes) > 5120, (
        f"Expected PDF > 5120 bytes (5 KB), got {len(pdf_bytes)} bytes"
    )


# ---------------------------------------------------------------------------
# Test (3): accepts minimal 1-year fixture without raising
# ---------------------------------------------------------------------------


def test_pdf_accepts_minimal_fixture():
    """build_pdf does not raise for a 1-year yearly_plan."""
    result = {
        "winning_policy": {
            "policy_id": "policy_minimal",
            "lifetime_taxes_nominal": 10000.0,
            "lifetime_taxes_pv": 9000.0,
            "terminal_estate": 500000.0,
            "success_probability": 0.80,
            "score": 0.75,
            "total_conversions": 0.0,
            "projected_future_marginal_rate": 0.22,
        },
        "yearly_plan": [_make_year_row(2026, 66, 0.0)],
        "warnings": [],
    }
    household = _fixture_household()
    pdf_bytes = build_pdf(result, household)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Test (4): result with no conversions (all-zero conversion column)
# ---------------------------------------------------------------------------


def test_pdf_handles_no_conversion_years():
    """build_pdf works when no year has a conversion (top-10 table is empty)."""
    result = {
        "winning_policy": {
            "policy_id": "policy_no_conversions",
            "lifetime_taxes_nominal": 200000.0,
            "lifetime_taxes_pv": 180000.0,
            "terminal_estate": 800000.0,
            "success_probability": 0.85,
            "score": 0.80,
            "total_conversions": 0.0,
            "projected_future_marginal_rate": 0.24,
        },
        "yearly_plan": [_make_year_row(2026 + i, 66 + i, 0.0) for i in range(10)],
        "warnings": [],
    }
    household = _fixture_household()
    pdf_bytes = build_pdf(result, household)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Test (5): None-safe formatting for _cur and _pct helpers
# ---------------------------------------------------------------------------


def test_pdf_handles_none_values_in_winning_policy():
    """build_pdf handles None values in winning_policy without TypeError."""
    result = {
        "winning_policy": {
            "policy_id": "policy_with_nones",
            "lifetime_taxes_nominal": None,  # Should default to 0
            "lifetime_taxes_pv": None,  # Should default to 0
            "terminal_estate": 500000.0,
            "success_probability": None,  # Should default to 0
            "score": 0.75,
            "total_conversions": 0.0,
            "projected_future_marginal_rate": None,  # Should default to 0
        },
        "yearly_plan": [_make_year_row(2026, 66, 0.0)],
        "warnings": [],
    }
    household = _fixture_household()
    # Should not raise TypeError
    pdf_bytes = build_pdf(result, household)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Test (6): inputs snapshot section
# ---------------------------------------------------------------------------


def _pdf_text(pdf_bytes: bytes) -> str:
    """Decompress all Flate streams and return concatenated latin-1 text.

    ReportLab writes text-showing operators as literal ``(text) Tj`` inside
    compressed content streams, so section titles are findable this way.
    """
    import base64
    import re
    import zlib

    chunks: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        raw = m.group(1)
        data = None
        try:
            data = zlib.decompress(raw)  # [/FlateDecode]
        except zlib.error:
            try:
                # ReportLab default: [/ASCII85Decode /FlateDecode]
                data = zlib.decompress(base64.a85decode(raw.strip(), adobe=True))
            except Exception:
                data = raw  # uncompressed stream
        chunks.append(data.decode("latin-1", "ignore"))
    return "".join(chunks)


def test_pdf_includes_inputs_section_when_snapshot_present():
    """build_pdf renders an inputs section when the run carries a snapshot."""
    result = _fixture_30year_result()
    household = _fixture_household()
    inputs = {
        "household": {
            "filing_status": "joint",
            "self_birth_date": "1958-03-15",
            "spouse_birth_date": "1960-03-15",
            "state": "CA",
        },
        "accounts": [
            {"account_type": "traditional", "owner": "joint", "balance": 800000.0},
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
        },
        "constraints": {"irmaa_policy": "soft", "conversion_window": "anytime",
                        "preserve_taxable": False},
    }

    with_inputs = build_pdf(result, household, inputs=inputs)
    without_inputs = build_pdf(result, household)

    assert with_inputs[:4] == b"%PDF"
    text = _pdf_text(with_inputs)
    assert "Inputs Used for This Run" in text
    assert "$90,000" in text  # spending from the snapshot
    assert "$800,000" in text  # account balance from the snapshot
    # And the section is absent without a snapshot
    assert "Inputs Used for This Run" not in _pdf_text(without_inputs)


def test_pdf_embeds_charts():
    """The PDF contains the three chart titles (drawn as vector graphics)."""
    result = _fixture_30year_result()
    pdf_bytes = build_pdf(result, _fixture_household())
    text = _pdf_text(pdf_bytes)
    # Raw PDF text escapes the parentheses around "steady-return projection".
    assert "Account balances by year" in text
    assert "Annual taxes by type" in text
    assert "Roth conversions by year" in text
    assert text.count("steady-return projection") >= 3


def test_pdf_includes_alternative_policies_section():
    """The PDF records the rejected policies as deltas vs the winner."""
    pdf_bytes = build_pdf(_fixture_30year_result(), _fixture_household())
    text = _pdf_text(pdf_bytes)
    assert "Close alternatives" in text
    assert "Fill the 22% bracket" in text
    assert "-$211,734" in text


def test_pdf_includes_sale_plans_section():
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
    text = _pdf_text(
        build_pdf(_fixture_30year_result(), _fixture_household(), sale_plans=sale_plans)
    )
    assert "Sale Plan" in text
    assert "VTI" in text


def test_pdf_title_page_shows_run_and_household_ids():
    """When the household dict carries run_id / household_id, the title page
    renders both labels (so a printed report is traceable to its run)."""
    household = {**_fixture_household(), "run_id": "run-abc", "household_id": "hh-xyz"}
    text = _pdf_text(build_pdf(_fixture_30year_result(), household))
    assert "Run ID:" in text
    assert "Household ID:" in text


def test_pdf_ages_blank_after_plan_to_age():
    """The full-year table must stop showing a person's age past their
    Plan-to age (the household simulates to the longer spouse horizon)."""
    import re

    result = _fixture_30year_result()  # ages 66..95

    # Table cells render as literal "(text)" show-ops; matching the
    # parenthesized form avoids false hits on vector-path coordinates.
    def _has_cell(text: str, cell: str) -> bool:
        return re.search(rf"\({re.escape(cell)}\)", text) is not None

    # Sanity: without a plan-to age, the tail ages render
    base = _pdf_text(build_pdf(result, _fixture_household()))
    assert _has_cell(base, "94") and _has_cell(base, "95")

    inputs = {"household": {"self_death_age": 93}}
    text = _pdf_text(build_pdf(result, _fixture_household(), inputs))
    assert _has_cell(text, "93"), "age 93 is still in-plan"
    assert not _has_cell(text, "94"), "age past plan-to age must be blank"
    assert not _has_cell(text, "95"), "age past plan-to age must be blank"


# ---------------------------------------------------------------------------
# Dynamic spending reaches the report
# ---------------------------------------------------------------------------


def _spending_inputs(rule="fixed", floor=None, estate_weight=1):
    s = {
        "required_spending": 130000,
        "inflation": 0.03,
        "nominal_return": 0.06,
        "estate_weight": estate_weight,
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


def test_assumptions_state_the_spending_rule():
    text = _pdf_text(build_pdf(
        _fixture_30year_result(), _fixture_household(),
        inputs=_spending_inputs("guardrails", floor=95000),
    ))
    assert "If markets go badly" in text
    assert "Cut back, then recover" in text
    assert "Essential spending floor" in text


def test_assumptions_state_the_default_rule_too():
    """Silence would read as 'not modelled', not as 'spending stayed fixed'."""
    text = _pdf_text(build_pdf(
        _fixture_30year_result(), _fixture_household(), inputs=_spending_inputs("fixed"),
    ))
    assert "Keep spending the same" in text
    assert "Essential spending floor" not in text


def test_assumptions_carry_optimization_priority_on_old_runs():
    """Runs saved before October 2026 (no ``objective`` in the result) were
    scored under the taxes-vs-estate priority, and keep showing it."""
    text = _pdf_text(build_pdf(
        _fixture_30year_result(), _fixture_household(),
        inputs=_spending_inputs("fixed", estate_weight=0),
    ))
    assert "Optimization priority" in text
    assert "Lifetime taxes" in text


def test_assumptions_name_the_objective_on_new_runs():
    """A new run states its objective even when the snapshot still stores an
    old estate_weight, which no longer means anything."""
    result = {**_fixture_30year_result(), "objective": "pv_estate_minus_weighted_shortfall"}
    text = _pdf_text(build_pdf(
        result, _fixture_household(), inputs=_spending_inputs("fixed", estate_weight=0),
    ))
    assert "Optimization priority" not in text
    assert "After-tax estate, less unfunded spending" in text


def test_plan_table_gains_a_below_target_column_only_when_needed():
    """Since Step 4 the table runs past depletion.

    Without this column a reader watches Net Spend collapse for years with no
    explanation anywhere on the page.
    """
    short = _fixture_30year_result()
    for row in short["yearly_plan"]:
        row["target_spending"] = 130000.0
        row["net_spendable"] = 90000.0
    assert "Below Target" in _pdf_text(build_pdf(short, _fixture_household()))

    ok = _fixture_30year_result()
    for row in ok["yearly_plan"]:
        row["target_spending"] = 90000.0
        row["net_spendable"] = 90000.0
    assert "Below Target" not in _pdf_text(build_pdf(ok, _fixture_household()))


def test_plan_table_omits_the_column_for_old_runs():
    """Runs stored before target_spending existed must still render."""
    legacy = _fixture_30year_result()
    for row in legacy["yearly_plan"]:
        row.pop("target_spending", None)
    text = _pdf_text(build_pdf(legacy, _fixture_household()))
    assert "Below Target" not in text
    assert "Full 30-Year Plan" in text


def test_strategy_summary_names_the_winning_policy():
    """The Strategy Summary showed the raw id ("Policy ID: fill_10_annual")
    where the Results page and the Excel Results sheet show its name."""
    result = _fixture_30year_result()
    result["winning_policy"]["policy_id"] = "fill_10_annual"
    text = _pdf_text(build_pdf(result, _fixture_household()))
    # ReportLab draws the bold label and the value as separate text runs.
    assert "(Recommended strategy:) Tj" in text
    assert "( Fill the 10% bracket every year) Tj" in text
    assert "Policy ID" not in text


def test_strategy_summary_does_not_call_a_forced_policy_the_winner():
    result = _fixture_30year_result()
    result["winning_policy"]["policy_id"] = "fill_22_annual"
    result["forced_policy"] = "fill_22_annual"
    text = _pdf_text(build_pdf(result, _fixture_household()))
    assert "(Strategy you chose to run:) Tj" in text
    assert "( Fill the 22% bracket every year) Tj" in text
    assert "Recommended strategy:" not in text


def test_pdf_alternatives_show_each_strategys_conversion_this_year():
    result = _fixture_30year_result()
    result["alternative_policies"][0]["year0_conversion"] = 98000.0
    text = _pdf_text(build_pdf(result, _fixture_household()))
    from pypdf import PdfReader

    first = result["yearly_plan"][0]["year"]
    pdf = PdfReader(io.BytesIO(build_pdf(result, _fixture_household())))
    words = " ".join("".join(p.extract_text() for p in pdf.pages).split())
    # The saved projection's own year, in the heading and the note under it.
    assert f"Roth conversion in {first}" in words
    assert f"to Roth accounts in {first}." in words
    assert "$98,000" in text


def test_the_sale_plan_page_dates_its_prices_and_flags_a_shortfall():
    sale_plans = {
        "as_of": "2020-01-01",
        "generated_on": "2026-10-15",
        "years": [{
            "year": 2026, "target_cash": 1000.0, "cash_raised": 100.0,
            "cash_short": 900.0,
            "warnings": ["Insufficient taxable holdings to raise the requested cash."],
            "sold": [{"ticker": "SNOW", "holding_period": "short_term",
                      "shares_sold": 1.0, "proceeds": 100.0, "realized_gain": 60.0}],
        }],
    }
    text = _pdf_text(build_pdf(_fixture_30year_result(), _fixture_household(),
                               sale_plans=sale_plans))
    flat = " ".join(text.split())
    assert "priced as of 2020-01-01" in flat
    assert "$900 short" in flat
    assert "Insufficient taxable holdings" in flat


def test_alternatives_lead_with_scores_then_the_steady_return_comparison():
    """The PDF ranks alternatives as the page does; the steady-return tax and
    estate deltas follow under their own heading."""
    import re

    from pypdf import PdfReader
    from tests.unit.test_xlsx_export import _ranked_joint_result

    pdf = build_pdf(_ranked_joint_result(), _fixture_household())
    text = re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))
    assert "Average modeled score" in text
    assert "294 of 300" in text
    assert "cannot clearly separate them from ages 68 / 66 or 68 / 67" in text
    assert text.index("Average modeled score") < text.index(
        "Compare taxes and estate assuming a steady 6% return")
