"""The words every export uses for a result -- the same as the Results page
(frontend lib/resultSummary.ts, lib/verdicts.ts, SummaryCards.tsx). Keep in
sync, so a reader sees one vocabulary in the app, the PDF, Excel and CSV.

Each figure names its basis: the steady-return projection (every year at
the assumed average return) or the market scenarios.
"""
from __future__ import annotations

from src.reports.policy_labels import policy_label

STEADY = "steady-return projection"
TAXES = f"Lifetime taxes — {STEADY}"
TAXES_PV = f"Lifetime taxes — {STEADY}, today's dollars"
ESTATE = f"Projected estate — {STEADY}"
SUCCESS = "Spending funded in market scenarios"
NO_SIMULATION = "No market simulation"

# Close-alternatives columns, as the page heads them.
TAX_DIFF = "Tax difference · today's dollars"
ESTATE_DIFF = "Estate difference"
FUNDED = "Scenarios with spending funded"
COMPARISON = "Comparison result"
ALTERNATIVES_NOTE = (
    "Compare these alternatives with the recommendation. Negative tax amounts mean "
    "less tax; positive estate amounts mean more left to heirs. The conversion column "
    "shows the amount to convert, not a difference."
)

# Medicare surcharge (IRMAA) setting: four stored values, two behaviours
# (frontend lib/labels.ts IRMAA_LABELS).
IRMAA_HEADING = "Medicare surcharge thresholds"
IRMAA_LABEL = {
    "ignore": "Conversions may cross them; the surcharge is counted",
    "soft": "Conversions may cross them; the surcharge is counted",
    "strict": "Conversions are restricted at them",
    "avoid": "Conversions are restricted at them",
}

VERDICT_LABEL = {
    "winner": "Recommendation ahead",
    "alternative": "Alternative ahead",
    "unresolved": "Too close to distinguish",
    "equivalent": "Practically equivalent",
}


def simulated(result: dict) -> bool:
    """Whether markets were simulated. A deterministic run stores its one
    expected-return path as one "path", so the path count cannot tell."""
    return (result.get("monte_carlo_runs") or 0) > 0


def score_label(result: dict) -> str:
    wp = result.get("winning_policy") or {}
    if not simulated(result):
        return f"Modeled score — {STEADY}, today's dollars"
    n = wp.get("monte_carlo_paths") or result.get("monte_carlo_runs")
    return f"Modeled score — average across {n} market scenarios, today's dollars"


def first_year(result: dict) -> int | None:
    plan = result.get("yearly_plan") or []
    return plan[0].get("year") if plan else None


def conversion_heading(result: dict) -> str:
    """``"Roth conversion in 2026"`` -- the saved projection's own year."""
    y = first_year(result)
    return f"Roth conversion in {y}" if y is not None else "Roth conversion, first year"


def conversion_note(result: dict) -> str:
    y = first_year(result)
    return ("Amount transferred from traditional retirement accounts to Roth accounts in "
            f"{y if y is not None else 'the first year of the plan'}.")


def _pct(x: float) -> str:
    return f"{round(x * 1000) / 10:g}%"


def market_explanation(result: dict, nominal_return: float | None = None) -> list[str]:
    """How the market scenarios were drawn, from the run's own record
    (``market_model``); older runs take the return from their inputs and
    leave the volatility unstated. Mirrors the page's MarketExplanation."""
    m = result.get("market_model") or {}
    mean = m.get("mean_return", nominal_return)
    steady = (f"a projection assuming a steady {_pct(mean)} annual return" if mean is not None
              else "a projection assuming a steady annual return at the assumed rate")
    if not simulated(result):
        return [f"This run did not simulate market outcomes. Every figure comes from {steady}."]
    n = result.get("monte_carlo_runs")
    avg = f" of {_pct(mean)}" if mean is not None else ""
    out = [
        f"We use Monte Carlo simulation to test your plan under {n} possible investment-return "
        "scenarios. Returns vary from year to year, including gains and losses, around your "
        f"assumed average annual return{avg}. Every strategy faces the same market scenarios "
        "so the comparison is fair."
    ]
    if m.get("volatility") is not None:
        out.append(
            f"Annual volatility is {round(m['volatility'] * 1000) / 10:g} percentage points, "
            "measured as the standard deviation of annual returns. The model draws each "
            "year's return independently from a normal distribution."
        )
    out.append(f"The estate, taxes, charts and year-by-year table use {steady} "
               f"(labelled \u201c{STEADY}\u201d).")
    return out


def verdict_label(verdict: str | None) -> str:
    return VERDICT_LABEL.get(verdict or "", verdict or "")


def comparison_label(result: dict, alt: dict) -> str:
    """An alternative's comparison label; "—" without a market simulation,
    where a paired comparison would rest on the one expected-return path."""
    if not simulated(result):
        return "—"
    return verdict_label((alt.get("paired") or {}).get("verdict"))


def claim_ages(self_age, spouse_age) -> str:
    """``"You 69 · Spouse 68"``."""
    parts = [f"You {self_age}" if self_age is not None else None,
             f"Spouse {spouse_age}" if spouse_age is not None else None]
    return " · ".join(p for p in parts if p) or "—"


def start_traditional(result: dict) -> float | None:
    """The traditional balance level-dollar rules took their share of;
    absent on runs saved before it was recorded."""
    return result.get("starting_traditional_balance")


def strategy(result: dict, policy_id: str) -> str:
    """A policy's name in this result: level-dollar rules by their amount."""
    return policy_label(policy_id, start_traditional(result))


def candidate(policy_id: str, self_age=None, spouse_age=None, start: float | None = None) -> str:
    """``"No conversions · You 69 · Spouse 68"`` -- never a raw key."""
    ages = claim_ages(self_age, spouse_age)
    return policy_label(policy_id, start) + ("" if ages == "—" else f" · {ages}")


def candidate_key(key: str, start: float | None = None) -> str:
    """A stored key (``"none@69-68"``) in words."""
    policy_id, _, pair = key.partition("@")
    s, _, p = pair.partition("-")
    if p.startswith("-"):           # "69--": no spouse dimension
        p = p[1:]

    def age(a: str):
        return None if a in ("", "-") else int(a)

    return candidate(policy_id, age(s), age(p), start)


# ---------------------------------------------------------------------------
# Ranking: every strategy on the measurement that ranked it (the page's
# rankingRows / closeCallSentence in lib/resultSummary.ts)
# ---------------------------------------------------------------------------

SCORE_AVG = "Average modeled score"
DIFF = "Difference from recommendation"


def _ages(self_age, spouse_age) -> str:
    return " / ".join(str(a) for a in (self_age, spouse_age) if a is not None)


def _joint(result: dict) -> bool:
    """A claim-age search: its strategies carry keys and are named by ages."""
    return bool((result.get("winning_policy") or {}).get("key"))


def ranking_rows(result: dict) -> list[dict] | None:
    """The recommendation and each alternative on the modeled score across
    the market scenarios, highest first. None without a simulation (the
    steady-return projection ranked them) or when an alternative has no
    paired comparison and no score (runs saved before either)."""
    alts = result.get("alternative_policies") or []
    if not simulated(result) or not alts:
        return None
    wp = result.get("winning_policy") or {}
    joint = _joint(result)
    w_score = (result.get("joint_winner") or {}).get("score", wp.get("score"))
    w_paths = wp.get("monte_carlo_paths") or result.get("monte_carlo_runs")
    w_p = wp.get("success_probability") or 0
    plan = result.get("yearly_plan") or [{}]

    def name(c: dict) -> str:
        pid = c.get("policy_id", "—")
        return (candidate(pid, c.get("claim_age_self"), c.get("claim_age_spouse"),
                          start_traditional(result))
                if joint else strategy(result, pid))

    rows = [{
        "key": wp.get("key") or wp.get("policy_id"), "name": name(wp), "recommendation": True,
        "score": w_score, "difference": 0.0,
        "funded": round(w_p * w_paths), "scenarios": w_paths, "verdict": None,
        "year0": wp.get("year0_conversion", plan[0].get("conversion")),
    }]
    for a in alts:
        paired = a.get("paired")
        # The paired difference is taken on the scenarios both were scored on.
        if paired and paired.get("mean_difference") is not None:
            diff = -paired["mean_difference"]
        elif a.get("score") is not None:
            diff = a["score"] - w_score
        else:
            return None
        n = a.get("monte_carlo_paths") or w_paths
        score = a.get("score")
        if score is None and n == w_paths:
            score = w_score + diff
        rows.append({
            "key": a.get("key") or a.get("policy_id"), "name": name(a), "recommendation": False,
            "score": score, "difference": diff,
            "funded": round((w_p + (a.get("success_probability_delta") or 0)) * n),
            "scenarios": n, "verdict": (paired or {}).get("verdict"),
            "year0": a.get("year0_conversion"), "alternative": a,
        })
    rows.sort(key=lambda r: (-r["difference"], not r["recommendation"]))
    return rows


def ranking_note(rows: list[dict]) -> str:
    return ("Each strategy's modeled score: the after-tax estate less unfunded spending, "
            f"averaged across the same {rows[0]['scenarios']} market scenarios in today's "
            "dollars. This is the measurement that ranked them. Too close to distinguish "
            "means the simulation cannot establish which is better: it does not mean the "
            "alternative is worse, and it does not mean the two are equivalent."
            + (" A strategy set aside early in the search was scored on fewer market scenarios, "
               "as its spending-funded count shows; its difference is measured on the "
               "scenarios both share."
               if any(r["scenarios"] != rows[0]["scenarios"] for r in rows) else ""))


def _list_or(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} or {items[-1]}"


def close_call_sentence(result: dict) -> str | None:
    """``"Ages 69 / 68 have the highest average modeled score. However, this
    simulation cannot clearly separate them from ages 68 / 67 or 68 / 66."``
    None when nothing is a close call (or on a forced or deterministic run)."""
    if result.get("forced_policy") or not simulated(result):
        return None
    alts = [a for a in result.get("alternative_policies") or [] if a.get("paired")]
    if any(a["paired"]["verdict"] == "alternative" for a in alts):
        return None
    unresolved = [a for a in alts if a["paired"]["verdict"] == "unresolved"]
    equivalent = [a for a in alts if a["paired"]["verdict"] == "equivalent"]
    if not unresolved and not equivalent:
        return None
    wp = result.get("winning_policy") or {}
    joint = _joint(result)
    if joint and all(a["policy_id"] == wp.get("policy_id") for a in unresolved + equivalent):
        w_ages = _ages(wp.get("claim_age_self"), wp.get("claim_age_spouse"))
        subject, them = f"Ages {w_ages} have", "them"

        def names(xs):
            return "ages " + _list_or([_ages(a.get("claim_age_self"), a.get("claim_age_spouse"))
                                       for a in xs])
    else:
        subject, them = "The recommendation has", "it"

        def names(xs):
            return _list_or([
                f"“{strategy(result, a['policy_id'])}”"
                + (f" at ages {_ages(a.get('claim_age_self'), a.get('claim_age_spouse'))}"
                   if joint else "")
                for a in xs])
    parts = [f"{subject} the highest average modeled score."]
    if unresolved:
        parts.append(f"However, this simulation cannot clearly separate {them} from "
                     f"{names(unresolved)}.")
    if equivalent:
        lead = "It also treats" if unresolved else "However, the simulation treats"
        parts.append(f"{lead} {them} as practically equivalent to {names(equivalent)}: the "
                     "modeled difference is small enough to treat these options similarly.")
    return " ".join(parts)


def steady_title(result: dict, nominal_return: float | None = None) -> str:
    """``"Compare taxes and estate assuming a steady 6% return"``."""
    mean = (result.get("market_model") or {}).get("mean_return", nominal_return)
    return ("Compare taxes and estate assuming a steady "
            + (f"{_pct(mean)} " if mean is not None else "") + "return")


def steady_note(result: dict, nominal_return: float | None = None) -> str:
    mean = (result.get("market_model") or {}).get("mean_return", nominal_return)
    every = _pct(mean) if mean is not None else "the assumed average return"
    return (f"One projection in which every year earns exactly {every}, compared with the "
            "recommendation. Negative tax amounts mean less tax; positive estate amounts mean "
            "more left to heirs. These figures did not decide the ranking.")
