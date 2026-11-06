"""Walk example households through the search and the staged Monte Carlo.

The tables in ``docs/HOW_A_RECOMMENDATION_IS_CHOSEN.md`` are this script's
output. It runs the same code the app runs -- ``search`` builds the
strategies, ``score_policies_adaptive`` screens and scores them -- but calls
the stages one at a time so each can be printed: which rules produced a
schedule and which were dropped, the steady-return ranking, the stage-1
screen on the first third of the market scenarios, the finalists on the full
budget, and the paired verdicts. The ``happy`` case is also run as a
claim-age search so the joint pipeline can be shown.

    cd backend && uv run python -m benchmarks.walkthrough --out /tmp/walkthrough.json
    cd backend && uv run python -m benchmarks.walkthrough --case tight --paths 300

Re-run it when the engine, the search or a tax table changes, and paste the
tables back into the document.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections.abc import Callable
from decimal import Decimal

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.claiming import AgeControl, ClaimControls
from src.optimization.joint import JointSearchParams, run_joint_optimization
from src.optimization.montecarlo import ScoredPolicy, compare_paired, score_policies_adaptive
from src.optimization.optimizer import materiality
from src.optimization.search import (
    _ANNUAL_RULE_IDS,
    _LEVEL_RULES,
    Policy,
    _build_rule_schedule,
    _dedup_key,
    rule_of,
    search,
    thru_year_of,
)
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State
from src.reports.policy_labels import policy_label
from src.reports.result_labels import VERDICT_LABEL

D = Decimal
_ZERO = D("0")

Case = tuple[State, Settings, Constraints]

# A policy the stage-1 screen eliminates that the document still wants fully
# scored, for contrast with the finalists. Pinned, so it receives the full
# budget but keeps the rank stage 1 gave it -- exactly what a forced policy
# gets in the app.
CONTRAST: dict[str, str] = {"tight": "fill_32_annual"}


def engines() -> Engines:
    rules = TaxRules()
    return Engines(
        federal=FederalTaxEngine(rules),
        state=StateTaxEngine(rules),
        irmaa=IRMAACalculator(rules),
        rmd=RMDCalculator(rules),
        ss=SocialSecurityCalculator(),
        rules=rules,
    )


# ── The example households ────────────────────────────────────────────────────
#
# Synthetic, chosen so each shows one behaviour of the search. Social Security
# is claimed at a fixed age in every case so the strategy search is the only
# moving part; ``happy`` is run again with both ages searched.


def happy() -> Case:
    """The standard test household plus Social Security: a comfortably funded
    couple where a bracket fill wins."""
    state = State(
        year=2026, age_self=62, age_spouse=62,
        balance_taxable=D("400000"), basis_taxable=D("300000"),
        balance_traditional=D("2500000"), balance_roth=D("50000"),
        filing_status="joint", state_code="CA", pension=D("30000"),
    )
    settings = Settings(
        start_year=2026, required_spending=D("90000"), simulation_years=30,
        income_schedule=[IncomeEntry("pension", D("30000"), None, None)],
        ss_pia_self=D("2800"), ss_claim_age_self=67, ss_receiving_self=False,
        ss_pia_spouse=D("1600"), ss_claim_age_spouse=67, ss_receiving_spouse=False,
        birth_year_self=1964, birth_year_spouse=1964,
    )
    return state, settings, Constraints()


def tight() -> Case:
    """A small IRA with nothing beside it and spending that strains it."""
    state = State(
        year=2026, age_self=65, age_spouse=63,
        balance_taxable=_ZERO, basis_taxable=_ZERO,
        balance_traditional=D("500000"), balance_roth=_ZERO,
        filing_status="joint", state_code="CA",
    )
    settings = Settings(
        start_year=2026, required_spending=D("60000"), simulation_years=30,
        ss_pia_self=D("2000"), ss_claim_age_self=67, ss_receiving_self=False,
        ss_pia_spouse=D("1200"), ss_claim_age_spouse=67, ss_receiving_spouse=False,
        birth_year_self=1961, birth_year_spouse=1963,
    )
    return state, settings, Constraints()


def large() -> Case:
    """A very large IRA and modest spending: heavy conversions, big RMDs."""
    state = State(
        year=2026, age_self=62, age_spouse=62,
        balance_taxable=D("500000"), basis_taxable=D("400000"),
        balance_traditional=D("6000000"), balance_roth=D("100000"),
        filing_status="joint", state_code="CA",
    )
    settings = Settings(
        start_year=2026, required_spending=D("80000"), simulation_years=30,
        ss_pia_self=D("3500"), ss_claim_age_self=70, ss_receiving_self=False,
        ss_pia_spouse=D("2000"), ss_claim_age_spouse=70, ss_receiving_spouse=False,
        birth_year_self=1964, birth_year_spouse=1964,
    )
    return state, settings, Constraints()


def working() -> Case:
    """Both still earning: the salaries fill the brackets for years."""
    state = State(
        year=2026, age_self=58, age_spouse=56,
        balance_taxable=D("200000"), basis_taxable=D("150000"),
        balance_traditional=D("1000000"), balance_roth=_ZERO,
        filing_status="joint", state_code="CA", salary=D("210000"),
    )
    settings = Settings(
        start_year=2026, required_spending=D("110000"), simulation_years=35,
        income_schedule=[
            IncomeEntry("salary", D("150000"), None, 2031, owner="self"),
            IncomeEntry("salary", D("60000"), None, 2029, owner="spouse"),
        ],
        ss_pia_self=D("3200"), ss_claim_age_self=67, ss_receiving_self=False,
        ss_pia_spouse=D("1500"), ss_claim_age_spouse=67, ss_receiving_spouse=False,
        birth_year_self=1968, birth_year_spouse=1970,
    )
    return state, settings, Constraints()


CASES: dict[str, Callable[[], Case]] = {
    "happy": happy, "tight": tight, "large": large, "working": working,
}


# ── Formatting ────────────────────────────────────────────────────────────────


def money(x: Decimal | float | int) -> str:
    v = float(x)
    return f"−${-v:,.0f}" if v < 0 else f"${v:,.0f}"


def pct(x: Decimal | float) -> str:
    return f"{float(x) * 100:.1f}%"


def table(header: list[str], rows: list[list[str]], align: str | None = None) -> str:
    align = align or ("l" + "r" * (len(header) - 1))
    sep = "|" + "|".join(":---" if a == "l" else "---:" for a in align) + "|"
    lines = ["| " + " | ".join(header) + " |", sep]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def label(policy_id: str, state: State) -> str:
    return policy_label(policy_id, float(state.balance_traditional))


def conv_years(p: Policy) -> list[int]:
    return [i for i, c in enumerate(p.conversions) if c > _ZERO]


def stop_year(p: Policy, start_year: int) -> str:
    ys = conv_years(p)
    return "—" if not ys else str(start_year + ys[-1])


def stage1_mean(sp: ScoredPolicy, n: int) -> Decimal:
    return sum(sp.path_objectives[:n], _ZERO) / D(n)


# ── One case ──────────────────────────────────────────────────────────────────


def build_rows(case: Case, eng: Engines, policies: list[Policy]) -> list[dict]:
    """One row per rule: what the walk produced, or why it produced nothing."""
    state, settings, constraints = case
    by_rule: dict[str, list[Policy]] = {}
    for p in policies:
        r = rule_of(p.policy_id)
        if r is not None:
            by_rule.setdefault(r, []).append(p)
    rows = []
    rules = [(r, None) for r in _ANNUAL_RULE_IDS] + list(_LEVEL_RULES)
    for rule, share in rules:
        requested = None if share is None else {rule: share * state.balance_traditional}
        schedule, feasible = _build_rule_schedule(
            state, rule, eng, settings, constraints, requested=requested
        )
        ys = [i for i, c in enumerate(schedule) if c > _ZERO]
        if not feasible:
            status = "dropped: cannot fund the first year"
        elif _dedup_key(schedule) == ():
            status = "skipped: never converts (same as no conversions)"
        else:
            status = "kept"
        variants = [p for p in by_rule.get(rule, []) if thru_year_of(p.policy_id) is not None]
        full = next((p for p in by_rule.get(rule, []) if p.policy_id == f"{rule}_annual"), None)
        rows.append({
            "rule": rule,
            "label": label(f"{rule}_annual", state),
            "requested": None if share is None else float(share * state.balance_traditional),
            "status": status,
            "converting_years": len(ys),
            "first_year": None if not ys else settings.start_year + ys[0],
            "last_year": None if not ys else settings.start_year + ys[-1],
            "total": float(sum(schedule, _ZERO)),
            # First year the full rule's steady-return path reports a
            # shortfall, from the evaluated result (the walk appends a year's
            # amount before it learns the year ran short, so the schedule's
            # length is one year late).
            "shortfall_year": None if full is None else full.result.depletion_year,
            "variants_kept": len(variants),
            "schedule": [float(c) for c in schedule],
        })
    return rows


def run_case(name: str, eng: Engines, paths: int, seed: int) -> dict:
    case = CASES[name]()
    state, settings, constraints = case
    t0 = time.monotonic()
    policies = search(state, eng, settings, constraints)
    t_search = time.monotonic() - t0
    rows = build_rows(case, eng, policies)

    t0 = time.monotonic()
    scored = score_policies_adaptive(
        policies, state, eng, settings, constraints, runs=paths, seed=seed,
        contenders="none", pinned=CONTRAST.get(name),
    )
    t_mc = time.monotonic() - t0
    stage1 = max(1, paths // 3)
    full = [sp for sp in scored if len(sp.path_objectives) == paths]
    winner = full[0]  # score_policies_adaptive ranks the fully sampled first
    mat = materiality(state)
    det_rank = {p.policy_id: i + 1 for i, p in enumerate(policies)}

    def pol(p: Policy) -> dict:
        return {
            "id": p.policy_id, "label": label(p.policy_id, state),
            "conversion_years": len(conv_years(p)),
            "total_converted": float(sum(p.conversions, _ZERO)),
            "first_amount": float(p.conversions[0]) if p.conversions else 0.0,
            "stop_year": stop_year(p, settings.start_year),
            "path_value": float(p.result.path_value),
            "terminal_estate_pv": float(p.result.terminal_estate_pv),
            "shortfall_pv": float(p.result.shortfall_pv),
            "feasible": p.result.feasible,
        }

    def sc(sp: ScoredPolicy) -> dict:
        paired = None if sp is winner else compare_paired(winner, sp, mat)
        return {
            **pol(sp.policy),
            "det_rank": det_rank[sp.policy.policy_id],
            "stage1_score": float(stage1_mean(sp, stage1)),
            "paths": len(sp.path_objectives),
            "score": float(sp.score),
            "success": float(sp.success_probability),
            "verdict": None if paired is None else paired.verdict,
            "mean_difference": None if paired is None else float(paired.mean_difference),
            "ci": None if paired is None else [float(paired.ci_low), float(paired.ci_high)],
        }

    return {
        "case": name,
        "inputs": {
            "ages": [state.age_self, state.age_spouse], "filing_status": state.filing_status,
            "state": state.state_code, "taxable": float(state.balance_taxable),
            "basis": float(state.basis_taxable),
            "traditional": float(state.balance_traditional), "roth": float(state.balance_roth),
            "pension": float(state.pension), "salary": float(state.salary),
            "spending": float(settings.required_spending), "years": settings.simulation_years,
            "start_year": settings.start_year,
            "claim_ages": [settings.ss_claim_age_self, settings.ss_claim_age_spouse],
            "pias": [float(settings.ss_pia_self or 0), float(settings.ss_pia_spouse or 0)],
        },
        "rules": rows,
        "policies": len(policies),
        "deterministic": [pol(p) for p in policies],
        "scored": [sc(sp) for sp in scored],
        "stage1_paths": stage1, "paths": paths, "materiality": float(mat),
        "winner": sc(winner),
        "contrast": CONTRAST.get(name),
        # Steady-return projection of the baseline, for the shortfall range.
        "none_shortfall_year": next(
            p for p in policies if p.policy_id == "none"
        ).result.depletion_year,
        "timings": {"search": t_search, "monte_carlo": t_mc},
    }


def run_joint(eng: Engines, paths: int, seed: int) -> dict:
    """The happy household with both claim ages searched and 65/63 entered
    as the comparison ages."""
    state, settings, constraints = happy()
    settings = dataclasses.replace(settings, ss_claim_age_self=65, ss_claim_age_spouse=63)
    controls = ClaimControls(AgeControl("search"), AgeControl("search"))
    params = JointSearchParams(monte_carlo_runs=paths, seed=seed)
    t0 = time.monotonic()
    out = run_joint_optimization(state, eng, settings, constraints, controls, params)
    out["elapsed"] = time.monotonic() - t0
    return out


# ── Markdown ──────────────────────────────────────────────────────────────────


def md_case(r: dict) -> str:
    inp = r["inputs"]
    out = [f"## Case `{r['case']}`", ""]
    out.append(
        f"Ages {inp['ages'][0]}/{inp['ages'][1]}, {inp['filing_status']}, {inp['state']}; "
        f"taxable {money(inp['taxable'])} (basis {money(inp['basis'])}), traditional "
        f"{money(inp['traditional'])}, Roth {money(inp['roth'])}; pension {money(inp['pension'])}, "
        f"salary {money(inp['salary'])}; spending {money(inp['spending'])}; "
        f"{inp['years']} years from {inp['start_year']}; claim ages "
        f"{inp['claim_ages'][0]}/{inp['claim_ages'][1]}, PIAs {money(inp['pias'][0])}/"
        f"{money(inp['pias'][1])}."
    )
    out += ["", "### 1. Building the strategies", ""]
    rows = []
    for x in r["rules"]:
        rows.append([
            x["label"], "—" if x["requested"] is None else money(x["requested"]),
            x["status"], str(x["converting_years"]),
            "—" if x["first_year"] is None else f"{x['first_year']}–{x['last_year']}",
            money(x["total"]),
            "—" if x["shortfall_year"] is None else str(x["shortfall_year"]),
            str(x["variants_kept"]),
        ])
    out.append(table(
        ["Rule", "Amount asked each year", "Result", "Years that convert",
         "Converting years", "Total converted", "First shortfall (steady return)",
         "Stop-year variants kept"],
        rows, "llrrrrrr",
    ))
    out.append(f"\n**{r['policies']} strategies** in all, including *no conversions*.")
    if r.get("none_shortfall_year") is not None:
        out.append(
            f"\n*No conversions* first runs short in {r['none_shortfall_year']} on the "
            "steady-return projection. These are steady-return dates; each market scenario "
            "has its own."
        )

    out += ["", "### 2. Steady-return ranking (top 8 and no conversions)", ""]
    det = r["deterministic"]
    shown = det[:8] + [d for d in det[8:] if d["id"] == "none"]
    out.append(table(
        ["#", "Strategy", "Years converting", "Total converted", "Steady-return value",
         "Unfunded spending (PV)"],
        [[str(det.index(d) + 1), d["label"], str(d["conversion_years"]),
          money(d["total_converted"]), money(d["path_value"]), money(d["shortfall_pv"])]
         for d in shown],
        "rlrrrr",
    ))

    out += ["", f"### 3. Stage 1 — every strategy on the first {r['stage1_paths']} market "
            "scenarios (top 8 and no conversions)", ""]
    by_s1 = sorted(r["scored"], key=lambda s: s["stage1_score"], reverse=True)
    finalists = {s["id"] for s in r["scored"] if s["paths"] == r["paths"]}
    shown = by_s1[:8] + [s for s in by_s1[8:] if s["id"] == "none"]
    out.append(table(
        ["#", "Strategy", "Steady-return rank", f"Average score, {r['stage1_paths']} scenarios",
         "Carried to all scenarios"],
        [[str(by_s1.index(s) + 1), s["label"], str(s["det_rank"]), money(s["stage1_score"]),
          ("yes (pinned)" if s["id"] == r.get("contrast") else "yes") if s["id"] in finalists
          else ""] for s in shown],
        "rlrrl",
    ))

    out += ["", f"### 4. Finalists on all {r['paths']} market scenarios", ""]
    fin = [s for s in r["scored"] if s["paths"] == r["paths"]]
    if r.get("contrast"):
        shown_c = [s for s in by_s1 if s["id"] == r["contrast"]]
        fin = [s for s in fin if s["id"] != r["contrast"]] + shown_c
    out.append(table(
        ["Strategy", "Modeled score", "Spending funded", "Compared with the winner",
         "Alternative minus winner", "95% interval"],
        [[s["label"] + (" (pinned for contrast)" if s["id"] == r.get("contrast") else ""),
          money(s["score"]), pct(s["success"]),
          "winner" if s["verdict"] is None else VERDICT_LABEL[s["verdict"]],
          "—" if s["mean_difference"] is None else money(-s["mean_difference"]),
          "—" if s["ci"] is None else f"[{money(-s['ci'][1])}, {money(-s['ci'][0])}]"]
         for s in fin],
        "lrrlrr",
    ))
    out.append(f"\nComparison threshold (materiality): {money(r['materiality'])}.")
    w = r["winner"]
    what = (
        "makes no conversions" if w["conversion_years"] == 0 else
        f"converts {money(w['first_amount'])} in {inp['start_year']}, "
        f"{money(w['total_converted'])} over {w['conversion_years']} years, last conversion "
        f"{w['stop_year']}"
    )
    out.append(
        f"\n**Recommendation: {w['label']}** — {what}; spending funded in "
        f"{pct(w['success'])} of scenarios."
    )
    t = r["timings"]
    out.append(f"\n*Search {t['search']:.0f} s, market simulation {t['monte_carlo']:.0f} s.*")
    return "\n".join(out)


def md_joint(j: dict) -> str:
    s = j["search"]
    st = s["stages"]
    out = ["## Case `happy` as a claim-age search (65/63 entered for comparison)", ""]
    elig = [x for x in s["scenarios"] if x["eligible"]]
    out.append(
        f"{len(s['scenarios'])} claim-age pairs enumerated, {len(elig)} eligible; "
        f"{len(s['exclusions'])} exclusions. {st['candidates']} candidates entered stage 1 "
        f"({st['per_scenario_breadth']} best by steady-return value plus no conversions per "
        f"pair; every strategy at the entered pair) on {st['stage1_runs']} market scenarios; "
        f"{len(st['finalists'])} finalists on all {st['final_runs']}."
    )
    out += ["", "### Finalists", ""]
    w = j["joint_winner"]
    cmp = s["comparisons"]
    out.append(table(
        ["Claim ages", "Strategy", "Modeled score", "Spending funded", "Scenarios",
         "Compared with the winner"],
        [[f"{f['claim_age_self']}/{f['claim_age_spouse']}", policy_label(f["policy_id"]),
          money(f["score"]), pct(f["success_probability"]), str(f["monte_carlo_paths"]),
          "winner" if f["key"] == w["key"] else VERDICT_LABEL[cmp[f["key"]]["verdict"]]]
         for f in st["finalists"]],
        "llrrrl",
    ))
    out.append(
        f"\n**Winner: ages {w['claim_age_self']}/{w['claim_age_spouse']}, "
        f"{policy_label(w['policy_id'])}**, score {money(w['score'])}, spending funded "
        f"{pct(w['success_probability'])}."
    )
    b = s["baselines"]
    out += ["", "### Baselines", ""]
    rows = []
    for key, name in (("entered_best_conversion", "Your ages, best conversions"),
                      ("entered_no_conversion", "Your ages, no conversions"),
                      ("winner_ages_no_conversion", "Winner's ages, no conversions")):
        if key in b:
            x = b[key]
            rows.append([name, f"{x['claim_age_self']}/{x['claim_age_spouse']}",
                         policy_label(x["policy_id"]), money(x["score"]),
                         pct(x["success_probability"]), str(x["monte_carlo_paths"])])
    out.append(table(["Baseline", "Claim ages", "Strategy", "Modeled score", "Spending funded",
                      "Scenarios"], rows, "lllrrr"))
    out.append(f"\n*Whole search {j['elapsed']:.0f} s.*")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--case", choices=[*CASES, "joint"], action="append",
                    help="run only these (default: every case, then the joint search)")
    ap.add_argument("--paths", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", help="write every number as JSON here")
    args = ap.parse_args(argv)
    names = args.case or [*CASES, "joint"]

    eng = engines()
    results: dict = {}
    for name in names:
        if name == "joint":
            results["joint"] = run_joint(eng, args.paths, args.seed)
            print(md_joint(results["joint"]), "\n")
        else:
            results[name] = run_case(name, eng, args.paths, args.seed)
            print(md_case(results[name]), "\n")
        sys.stdout.flush()
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(results, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
