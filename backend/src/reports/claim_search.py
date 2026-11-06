"""The "Claim-age search" section every export shares (csv / xlsx / pdf).

One place builds the rows, so the three formats cannot disagree about what a
joint run found. Each table is ``(title, header, rows, note)`` with plain
string or number cells; formats only lay them out. Initial-comparison figures
are always labeled with their scenario count: they rest on the first market
scenarios, not on all of them, as the finalists and baselines do.
"""
from __future__ import annotations

from src.reports.policy_labels import policy_label
from src.reports.result_labels import candidate_key, claim_ages, verdict_label

Table = tuple[str, list[str], list[list], str | None]


class Money(int):
    """A whole-dollar cell, so formats can show it as currency (an int is a count)."""


class Share(float):
    """A share of simulated paths (0–1), so formats can show it as a percent."""


def _m(v: float) -> Money:
    return Money(round(v))

# Section and table names, as the Results page titles them.
SECTION = "Explore other Social Security claim ages"
LONGEVITY = "What if you live longer or shorter?"
COMPARED_WITH_YOURS = "Recommended strategy compared with your original choices"

_VARIANTS = {
    "horizon_minus_5": "Plan ends 5 years earlier",
    "horizon_plus_5": "Plan ends 5 years later",
    "spouse_dies_78": "Spouse dies at 78",
    "self_dies_78": "You die at 78",
}


def _ages(self_age, spouse_age) -> str:
    return claim_ages(self_age, spouse_age)


def summary_rows(result: dict) -> list[tuple[str, str]]:
    """Claim ages and conversion stop year for the summary; [] for other runs."""
    search = result.get("search") or {}
    if not search.get("mode", "").startswith("joint"):
        return []
    wp = result.get("winning_policy") or {}
    rows = [("Recommended claim ages", _ages(wp.get("claim_age_self"),
                                              wp.get("claim_age_spouse")))]
    stop = (result.get("joint_winner") or {}).get("conversion_stop_year")
    rows.append(("Conversions stop after", "no conversions" if stop is None else str(stop)))
    return rows


def _candidate_row(label: str, c: dict, winner: dict, comparisons: dict,
                   start: float | None = None) -> list:
    is_winner = c["key"] == winner["key"]
    return [
        label, policy_label(c["policy_id"], start),
        _ages(c["claim_age_self"], c["claim_age_spouse"]),
        _m(c["score"]), _m(c["score"] - winner["score"]),
        Share(round(c["success_probability"], 4)), c["monte_carlo_paths"],
        "Recommendation" if is_winner
        else verdict_label((comparisons.get(c["key"]) or {}).get("verdict")),
    ]


def tables(result: dict) -> list[Table]:
    """Every claim-search table for *result*; [] when it is not a joint run."""
    search = result.get("search") or {}
    mode = search.get("mode")
    start = result.get("starting_traditional_balance")
    if mode == "joint_deterministic":
        return [(
            "Claim-age pairs (steady-return projection, no market simulation)",
            ["Claim ages", "Eligible", "Entered", "Best strategy", "Value"],
            [[_ages(r["claim_age_self"], r["claim_age_spouse"]), r["eligible"], r["entered"],
              policy_label(r["policy_id"], start), _m(r["value"])]
             for r in search["deterministic_matrix"]],
            None,
        ), *_exclusions(search)]
    if mode != "joint":
        return []

    stages = search["stages"]
    n1, n = stages["stage1_runs"], stages["final_runs"]
    winner = result["joint_winner"]
    # The recommendation's own score on the first n1 paths. Older runs lack
    # it, and the full-sample score is no substitute: a mean over other paths.
    w1 = stages.get("winner_stage1_score")
    out: list[Table] = [(
        f"Claim-age pairs — initial comparison, {n1} market scenarios",
        ["Claim ages", "Eligible", "Entered",
         f"Best strategy (first {n1})", f"Score (first {n1})",
         f"vs recommendation (first {n1})",
         f"Best strategy (all {n})", f"Score (all {n})"],
        [[_ages(r["claim_age_self"], r["claim_age_spouse"]), r["eligible"], r["entered"],
          policy_label(r["stage1"]["policy_id"], start), _m(r["stage1"]["score"]),
          "" if w1 is None else _m(r["stage1"]["score"] - w1),
          policy_label(r["final"]["policy_id"], start) if r["final"] else "",
          _m(r["final"]["score"]) if r["final"] else ""]
         for r in search["scenarios"]],
        (f"The initial {n1} market scenarios are included in the final {n}. Scores in the "
         f"first columns rest on those {n1}, compared with the recommendation on the same "
         f"{n1}; a strategy that looks better there may rank lower using all {n}."
         + ("" if w1 is not None else " Screening comparison unavailable for this saved run.")),
    )]
    comparisons = search.get("comparisons") or {}
    header = ["", "Strategy", "Claim ages", "Modeled score", "vs recommendation",
              "Scenarios with spending funded", "Market scenarios", "Comparison result"]
    # Strategy and claim ages already name each finalist: no label column.
    out.append((f"Strategies tested using all {n} market scenarios", header[1:],
                [_candidate_row("", c, winner, comparisons, start)[1:]
                 for c in stages["finalists"]], None))
    b = search["baselines"]
    # No entered-age rows when a searched age was left without a comparison age.
    baseline_rows = [(label, b[k]) for label, k in (
        ("Your ages, no conversions", "entered_no_conversion"),
        ("Your ages, best conversions", "entered_best_conversion"),
        ("Recommended ages, no conversions", "winner_ages_no_conversion"),
    ) if b.get(k)]
    out.append((COMPARED_WITH_YOURS, header, [
        _candidate_row(label, c, winner, comparisons, start) for label, c in baseline_rows
    ], ("" if b.get("entered_best_conversion") else "No comparison claim ages were provided. ")
       + "Differences are in the modeled score, not tax saved or extra estate; the rows "
       "overlap, so do not add them. Practically equivalent: the whole range of differences "
       f"lies within ±${search['materiality']:,.0f}."))
    if search.get("sensitivity"):
        # One row per strategy, one column per check, matched by key.
        variants = search["sensitivity"]
        keys: list[str] = []
        for row in variants:
            for r in row["results"]:
                if r["key"] not in keys:
                    keys.append(r["key"])
        keys.sort(key=lambda k: k != winner["key"])

        def cell(row: dict, k: str):
            r = next((x for x in row["results"] if x["key"] == k), None)
            if r is None:
                return ""
            return _m(r["score"] if k == winner["key"] else r["vs_winner"])

        out.append((
            f"{LONGEVITY} (not used to rank)",
            ["Strategy and claim ages",
             *[_VARIANTS.get(r["variant"], r["variant"]) for r in variants]],
            [[("Recommendation: " if k == winner["key"] else "") + candidate_key(k, start),
              *[cell(row, k) for row in variants]] for k in keys]
            + [["Highest among the strategies checked?",
                *["Yes" if all(r["vs_winner"] <= 0 for r in row["results"]) else "No"
                  for row in variants]]],
            "Recommendation row: its modeled score under each check; other rows: the "
            "difference from it under the same check. Each strategy is rebuilt under the "
            "check with its rule and stop year unchanged.",
        ))
    out.extend(_exclusions(search))
    a = search.get("assumptions") or {}
    out.append(("Search assumptions", ["Item", "Value"], [
        ["Market scenarios, initial comparison", n1],
        ["Market scenarios, final comparison", n],
        ["Strategies per claim pair", stages["per_scenario_breadth"]],
        ["Candidates scored", stages["candidates"]],
        ["Random seed", a.get("seed", "")],
        ["MAGI look-back", a.get("magi_proxy_note", "")],
    ], None))
    return out


def _exclusions(search: dict) -> list[Table]:
    ex = search.get("exclusions") or []
    if not ex:
        return []
    return [("Excluded claim ages", ["Person", "Age", "Reason"],
             [["You" if e["person"] == "self" else "Spouse", e["age"], e["reason"]]
              for e in ex], None)]
