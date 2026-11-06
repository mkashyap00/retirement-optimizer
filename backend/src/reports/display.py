"""Shared display transforms for report exporters (xlsx, pdf).

Keep in sync with the frontend YearTable, which applies the same rule.
"""

from __future__ import annotations

import math


def blank_ages_after_death(yearly_plan: list[dict], inputs: dict | None) -> list[dict]:
    """Return plan rows with age columns blanked past each person's Plan-to age.

    The household simulates to the LONGER of the two horizons, so the
    shorter-lived person's age column would otherwise keep counting past
    their own plan-to age. Rows are shallow-copied; the input list is not
    mutated.
    """
    hh = (inputs or {}).get("household") or {}
    self_death = hh.get("self_death_age")
    spouse_death = hh.get("spouse_death_age")
    if self_death is None and spouse_death is None:
        return yearly_plan

    out: list[dict] = []
    for row in yearly_plan:
        blanked = dict(row)
        age_self = row.get("age_self")
        if self_death is not None and age_self is not None and age_self > self_death:
            blanked["age_self"] = None
        age_spouse = row.get("age_spouse")
        if (
            spouse_death is not None
            and age_spouse is not None
            and age_spouse > spouse_death
        ):
            blanked["age_spouse"] = None
        out.append(blanked)
    return out


def bracket_room(year_row: dict) -> tuple[float | None, float | None]:
    """Return ``(bracket_rate, bracket_room_left)`` for a yearly-plan row.

    The bracket holding the year's last dollar of taxable ordinary income, and
    how much more ordinary income fits in it before the next rate applies —
    what a further Roth conversion would use up. Room is ``None`` in the top
    bracket (no ceiling); both are ``None`` for rows stored without bracket
    facts. Keep in sync with the frontend YearTable "Bracket Room" column.
    """
    bracket = (year_row.get("rationale") or {}).get("bracket") or {}
    rate = bracket.get("bracket_rate")
    if rate is None:
        return None, None
    if bracket.get("bracket_top") is None:
        return rate, None
    return rate, bracket.get("headroom_remaining")


# ---------------------------------------------------------------------------
# Summary-card wording — mirrors frontend SummaryCards.tsx; keep in sync.
# ---------------------------------------------------------------------------


def _js_round(x: float) -> int:
    """JavaScript's Math.round: halves round up. Python's round() sends 2.5 to
    2, which would let the workbook and the page disagree on the same number."""
    return math.floor(x + 0.5)


def lifetime_taxes_pv_hint(winning_policy: dict) -> str:
    """``"$725,300 in today's dollars (2% discount)"``.

    Runs saved before ``discount_rate`` was reported used the fixed 2% default.
    """
    pv = winning_policy.get("lifetime_taxes_pv") or 0
    rate = winning_policy.get("discount_rate")
    rate = 0.02 if rate is None else rate
    return f"${pv:,.0f} in today's dollars ({_js_round(rate * 1000) / 10:g}% discount)"


def success_interval_hint(probability: float, runs: int | None) -> str | None:
    """``"± 5 pts (300 scenarios)"`` — the 95% Monte Carlo interval.

    ``None`` when the simulation was skipped: one return path gives 100% or
    0%, and an interval around that would be noise dressed as a measurement.
    """
    if not runs or runs <= 0:
        return None
    half_width = 1.96 * math.sqrt(probability * (1 - probability) / runs)
    return f"± {_js_round(half_width * 100)} pts ({runs} scenarios)"


def years_reduced_note(mean_years_reduced: float | None) -> str | None:
    """``"Spending below target in approximately 2 years per market scenario."``

    Neutral: the count includes years savings could not fund, with or
    without guardrails. Mirrors SummaryCards.tsx."""
    if not mean_years_reduced or mean_years_reduced <= 0:
        return None
    yrs = mean_years_reduced
    rounded = f"{yrs:.1f}" if yrs < 1 else str(_js_round(yrs))
    return (f"Spending below target in approximately {rounded} "
            f"year{'' if rounded == '1' else 's'} per market scenario.")


def strategy_heading(result: dict) -> str:
    """Label for the run's strategy: "Recommended strategy", or — on a forced run,
    where the user pinned it and the optimizer did not pick it — "Strategy you
    chose to run". Mirrors the Results-page banner in SummaryCards.tsx."""
    return "Strategy you chose to run" if result.get("forced_policy") else "Recommended strategy"
