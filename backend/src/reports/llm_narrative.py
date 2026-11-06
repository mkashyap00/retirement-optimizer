"""Generate a plain-language narrative for an optimization result.

Privacy scope: only aggregate figures and per-year plan rows are sent to
the LLM.  No names, birth dates, or state codes are included.

The prompt is built from the saved result, not from the household as
entered: a claim-age search recommends ages of its own, and the model must
not mistake the ages the user entered for the ones recommended. Each figure
names its basis -- the market scenarios (which ranked the strategies) or the
steady-return projection (taxes, estate and the year-by-year plan).
"""

from __future__ import annotations

import os
from pathlib import Path

from src.reports.assumption_labels import objective_row
from src.reports.claim_search import COMPARED_WITH_YOURS
from src.reports.llm_client import LLMClient
from src.reports.result_labels import (
    STEADY,
    candidate,
    claim_ages,
    conversion_heading,
    ranking_rows,
    score_label,
    simulated,
    strategy,
    verdict_label,
)

_SYSTEM_PROMPT = (
    "You are a seasoned retirement tax planner writing a report for the "
    "plan's owner in plain, professional language. "
    "CRITICAL: use only the numbers provided — never compute, extrapolate, "
    "or invent figures; the tables are the ground truth and you are the "
    "commentary. "
    "Structure: a short executive summary, the three highest-impact "
    "decisions and why they matter, the key risks and caveats flagged in "
    "the warnings, and what the reader should watch or revisit annually. "
    "Do not give investment advice or recommend specific securities."
)


def load_system_prompt() -> str:
    """Return the system prompt, honoring ``LLM_SYSTEM_PROMPT_FILE``.

    A user-supplied prompt file (e.g. an advisor-persona prompt for a local
    LLM) fully replaces the built-in default. Missing or unreadable files
    fall back to the default rather than failing the request.
    """
    path = os.environ.get("LLM_SYSTEM_PROMPT_FILE")
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return _SYSTEM_PROMPT


def _money(v) -> str:
    return f"${v or 0:,.0f}"


def _gain(v) -> str:
    """Money that may be a loss: -$4,000 rather than $-4,000."""
    return ("-" if (v or 0) < 0 else "") + _money(abs(v or 0))


def _signed(v) -> str:
    return f"{v or 0:+,.0f}"


def _joint(result: dict) -> bool:
    return (result.get("search") or {}).get("mode", "").startswith("joint")


def _name(result: dict, c: dict) -> str:
    """A strategy in words, with its claim ages when a search chose them."""
    if _joint(result):
        return candidate(c.get("policy_id", ""), c.get("claim_age_self"),
                         c.get("claim_age_spouse"), result.get("starting_traditional_balance"))
    return strategy(result, c.get("policy_id", ""))


def _input_lines(result: dict, inputs: dict | None) -> list[str]:
    if not inputs:
        return []
    hh = inputs.get("household") or {}
    sett = inputs.get("settings") or {}
    lines = [
        "## Plan inputs (as entered)",
        f"Filing status: {hh.get('filing_status', 'unknown')}",
        f"Required annual spending (after-tax): {_money(sett.get('required_spending'))}",
    ]
    entered = claim_ages(sett.get("ss_claim_age_self"), sett.get("ss_claim_age_spouse"))
    if entered != "—":
        lines.append(
            f"Social Security claim ages entered: {entered}"
            + (" (entered for comparison; the search chose the recommended ages)"
               if _joint(result) else "")
        )
    gains = inputs.get("capital_gains")
    if gains:
        year = gains.get("tax_year")
        lines.append(
            f"Capital gains already realized in {year} (net; negative = loss): "
            f"short-term {_gain(gains.get('short_term'))}, "
            f"long-term {_gain(gains.get('long_term'))}"
        )
        carried = (gains.get("carryover_short_term") or 0, gains.get("carryover_long_term") or 0)
        if any(carried):
            lines.append(
                f"Capital loss carried into {year}: short-term {_money(carried[0])}, "
                f"long-term {_money(carried[1])}"
            )
    label, value = objective_row(result, sett)
    lines += [f"{label}: {value}", ""]
    return lines


def _recommendation_lines(result: dict) -> list[str]:
    wp = result.get("winning_policy") or {}
    plan = result.get("yearly_plan") or [{}]
    ages = result.get("claim_ages") or {}
    lines = ["## Recommendation", f"Strategy: {strategy(result, wp.get('policy_id', ''))}"]
    rec = claim_ages(ages.get("self"), ages.get("spouse"))
    if rec != "—":
        lines.append(
            f"Social Security claim ages {'recommended' if _joint(result) else 'used'}: {rec}"
        )
    lines.append(f"{conversion_heading(result)}: "
                 f"{_money(wp.get('year0_conversion', plan[0].get('conversion')))}")
    if "conversion_stop_year" in (result.get("joint_winner") or {}):
        stop = result["joint_winner"]["conversion_stop_year"]
        lines.append(f"Conversions stop after: {'no conversions' if stop is None else stop}")
    if result.get("forced_policy"):
        lines.append("This strategy was chosen by the user, not ranked by the optimizer.")
    return lines + [""]


def _score_lines(result: dict) -> list[str]:
    wp = result.get("winning_policy") or {}
    score = (result.get("joint_winner") or {}).get("score", wp.get("score"))
    if not simulated(result):
        return ["## No market simulation", f"{score_label(result)}: {_money(score)}", ""]
    n = wp.get("monte_carlo_paths") or result.get("monte_carlo_runs")
    return [
        f"## Market scenarios ({n} scenarios; returns vary from year to year)",
        f"{score_label(result)}: {_money(score)}",
        "(The modeled score is the after-tax estate less unfunded spending; it ranked "
        "the strategies.)",
        f"Share of scenarios with spending funded every year: "
        f"{wp.get('success_probability', 0):.1%}",
        "",
    ]


def _steady_lines(result: dict) -> list[str]:
    wp = result.get("winning_policy") or {}
    return [
        f"## Recommendation — {STEADY} (every year at the assumed average return)",
        f"Lifetime taxes (nominal): {_money(wp.get('lifetime_taxes_nominal'))}",
        f"Lifetime taxes (today's dollars): {_money(wp.get('lifetime_taxes_pv'))}",
        f"Projected estate at the end of the plan: {_money(wp.get('terminal_estate'))}",
        f"Total Roth conversions: {_money(wp.get('total_conversions'))}",
        f"Projected future marginal rate: {wp.get('projected_future_marginal_rate', 0):.1%}",
        "",
    ]


def _baseline_lines(result: dict) -> list[str]:
    """The search's comparison with the ages the user entered."""
    search = result.get("search") or {}
    b = search.get("baselines") or {}
    if search.get("mode") != "joint" or not b:
        return []
    winner = result.get("joint_winner") or {}
    comparisons = search.get("comparisons") or {}
    lines = [f"## {COMPARED_WITH_YOURS} (modeled score, market scenarios)"]
    for label, k in (("Your entered ages, no conversions", "entered_no_conversion"),
                     ("Your entered ages, best conversions", "entered_best_conversion"),
                     ("Recommended ages, no conversions", "winner_ages_no_conversion")):
        c = b.get(k)
        if not c:
            continue
        verdict = verdict_label((comparisons.get(c.get("key")) or {}).get("verdict"))
        lines.append(
            f"- {label} ({_name(result, c)}): modeled score {_money(c.get('score'))}, "
            f"{_signed((c.get('score') or 0) - (winner.get('score') or 0))} vs recommendation"
            + (f"; {verdict}" if verdict else "")
        )
    return lines + [""]


def _alternative_lines(result: dict) -> list[str]:
    alternatives = result.get("alternative_policies") or []
    lines = ["## Alternative strategies (+ = the alternative is higher)"]
    if not alternatives:
        return lines + ["None recorded"]
    steady = (f"{STEADY}: lifetime taxes in today's dollars {{tax}}, "
              "projected estate {estate}")
    rows = ranking_rows(result)
    if rows:
        for r in rows:
            if r["recommendation"]:
                continue
            a = r["alternative"]
            lines.append(
                f"- {_name(result, a)}: modeled score {_signed(r['difference'])} vs "
                f"recommendation ({r['scenarios']} market scenarios)"
                + (f", {verdict_label(r['verdict'])}" if r["verdict"] else "") + "; "
                + steady.format(tax=_signed(a.get("lifetime_taxes_delta")),
                                estate=_signed(a.get("terminal_estate_delta")))
            )
        return lines
    for a in alternatives:
        lines.append(
            f"- {_name(result, a)}: "
            + steady.format(tax=_signed(a.get("lifetime_taxes_delta")),
                            estate=_signed(a.get("terminal_estate_delta")))
            + f", scenarios funded {a.get('success_probability_delta', 0):+.1%}"
        )
    return lines


def _plan_table(result: dict) -> list[str]:
    header = (
        "| year | age | conversion | total_tax | marginal_rate "
        "| net_spendable | total_balance |"
    )
    sep = "|------|-----|------------|-----------|---------------|---------------|---------------|"
    table_rows = [f"## Year-by-year plan ({STEADY})", header, sep]
    for r in result.get("yearly_plan") or []:
        total_bal = (
            r.get("balance_taxable", 0)
            + r.get("balance_traditional", 0)
            + r.get("balance_roth", 0)
        )
        table_rows.append(
            f"| {r.get('year')} "
            f"| {r.get('age_self')} "
            f"| ${r.get('conversion', 0):,.0f} "
            f"| ${r.get('total_tax', 0):,.0f} "
            f"| {r.get('marginal_rate', 0):.1%} "
            f"| ${r.get('net_spendable', 0):,.0f} "
            f"| ${total_bal:,.0f} |"
        )
    return table_rows


def build_prompt(result: dict, inputs: dict | None = None) -> str:
    """The user message sent to the LLM for *result* (and the run's *inputs*)."""
    # warnings are first-party template strings from the optimizer (never user
    # input or PII); passed through verbatim.
    warnings = result.get("warnings") or []
    return "\n".join([
        *_input_lines(result, inputs),
        *_recommendation_lines(result),
        *_score_lines(result),
        *_steady_lines(result),
        *_baseline_lines(result),
        *_plan_table(result),
        "",
        *_alternative_lines(result),
        "",
        "## Warnings",
        *(warnings or ["None"]),
    ])


def generate_narrative(
    result: dict,
    client: LLMClient,
    inputs: dict | None = None,
    system_prompt: str | None = None,
) -> str:
    """Build a privacy-scoped prompt from *result* and call the LLM.

    Only aggregate figures and per-year plan rows are included in the
    prompt — no birth dates, state codes, or personally identifiable
    information.

    Args:
        result: The optimization result dict (as stored in the DB).
        client: Any :class:`~src.reports.llm_client.LLMClient` implementation.
        inputs: The run's own copy of the inputs; entered claim ages come
            from here, recommended ones from *result*.

    Returns:
        Plain-language narrative string produced by the LLM.
    """
    return client.complete(
        system=system_prompt if system_prompt is not None else load_system_prompt(),
        user=build_prompt(result, inputs),
    )
