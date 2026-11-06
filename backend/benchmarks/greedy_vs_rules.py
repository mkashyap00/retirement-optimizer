"""Does the search still need greedy rollouts? The written gate.

Scores every policy -- the production search's rules, limited-duration and
level-dollar rules, and the greedy reference -- on the same Monte Carlo paths
for four households, and compares the best overall with the best that is not
greedy. This gate (with the level-dollar family) is what retired the
production greedy rollouts in October 2026; re-run it when the rule families
or the objective change.

    cd backend && uv run python -m benchmarks.greedy_vs_rules --paths 300 --seed 42 \\
        --out gvr.json --gate

Gate (PASS iff, for every case):
    best_non_greedy_score >= best_score - max(5000, 0.0025 x t0 investable assets)
    and success_non_greedy >= success_best - 0.01

It also measures the stage-1 screening loss the joint claim-age search will
take: the best of (top 3 by path_value + none) against the best of every
non-greedy candidate, with and without a one-per-bracket diversity cap.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import resource
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path

from benchmarks.greedy_reference import greedy_policies, trimmed

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 16)
VOLATILITY = Decimal("0.12")
CASES = ("standard", "widow_A", "widow_B", "salaried_couple")


def tolerance(assets: Decimal) -> float:
    return max(5000.0, 0.0025 * float(assets))


def family(policy_id: str) -> str:
    from src.optimization.search import rule_of, thru_year_of

    rule = rule_of(policy_id)
    if rule is not None and rule.startswith("level_"):
        return "level"
    if policy_id == "none" or policy_id.endswith("_annual"):
        return "rules"
    if rule is not None and thru_year_of(policy_id) is not None:
        return "duration"
    return "greedy"


# ── Cases ─────────────────────────────────────────────────────────────────────


def _standard():
    """The golden standard household (tests/integration/test_optimizer_pipeline.py)."""
    from src.optimization.state import Constraints, IncomeEntry, Settings, State

    D = Decimal
    state = State(
        year=2025, age_self=62, age_spouse=62,
        balance_taxable=D("400000"), basis_taxable=D("300000"),
        balance_traditional=D("2500000"), balance_roth=D("50000"),
        filing_status="joint", state_code="CA", pension=D("30000"),
    )
    settings = Settings(
        start_year=2025, required_spending=D("90000"), simulation_years=30,
        income_schedule=[IncomeEntry("pension", D("30000"), None, None)],
    )
    return state, settings, Constraints()


def _from_fixture(name: str):
    from fastapi.testclient import TestClient
    from src.api.app import create_app
    from src.api.assemble import build_optimizer_inputs

    payload = json.loads((FIXTURES / f"{name}.json").read_text())
    app = create_app(":memory:")
    with TestClient(app) as client:
        resp = client.post("/households", json=payload)
        resp.raise_for_status()
        return build_optimizer_inputs(app.state.db, resp.json()["household_id"], TODAY)


def build_case(name: str):
    """``(state, settings, constraints)`` for a named case."""
    if name == "standard":
        return _standard()
    if name.startswith("widow"):
        state, settings, constraints = _from_fixture("widow")
        if name == "widow_B":  # spouse dies at 78
            settings = dataclasses.replace(
                settings,
                first_death_year=state.year + (78 - state.age_spouse),
                first_death_is_spouse=True,
            )
        return state, settings, constraints
    return _from_fixture(name)


# ── One case ──────────────────────────────────────────────────────────────────


def _row(scored, fam: str, year0: int) -> dict:
    conv = scored.policy.conversions
    nz = [i for i, c in enumerate(conv) if c > 0]
    return {
        "id": scored.policy.policy_id,
        "family": fam,
        "score": float(scored.score),
        "success": float(scored.success_probability),
        "path_value": float(scored.policy.result.path_value),
        "total_conversions": float(sum(conv, Decimal(0))),
        "conversion_years": len(nz),
        "last_conversion_year": year0 + nz[-1] if nz else None,
        "schedule": [round(float(c)) for c in conv],
    }


def _shortlist(rows: list[dict], breadth: int, diversity: bool) -> list[dict]:
    """Top *breadth* by path_value (optionally one per bracket rule) + none."""
    from src.optimization.search import rule_of

    picked, rules_used = [], set()
    for r in sorted(rows, key=lambda r: r["path_value"], reverse=True):
        if len(picked) == breadth:
            break
        if r["id"] == "none":
            continue
        rule = rule_of(r["id"]) or r["id"]
        if diversity and rule in rules_used:
            continue
        rules_used.add(rule)
        picked.append(r)
    return picked + [r for r in rows if r["id"] == "none"]


def run_case(name: str, n_paths: int, seed: int, confirm_seed: int | None = None) -> dict:
    logging.disable(logging.WARNING)
    from src.api.endpoints.optimization import _ENGINES
    from src.optimization import montecarlo as MC
    from src.optimization.optimizer import _MemoFederalEngine
    from src.optimization.search import search

    timings = {}
    t = time.monotonic()
    state, settings, constraints = build_case(name)
    engines = dataclasses.replace(_ENGINES, federal=_MemoFederalEngine(_ENGINES.federal))
    timings["build"] = time.monotonic() - t

    t = time.monotonic()
    non_greedy = search(state, engines, settings, constraints)
    timings["search_rules"] = time.monotonic() - t

    t = time.monotonic()
    seen = {trimmed(p.conversions) for p in non_greedy}
    greedy = [
        p for p in greedy_policies(state, engines, settings, constraints, lookahead_years=5)
        if trimmed(p.conversions) not in seen  # a rule already expresses it
    ]
    timings["search_greedy"] = time.monotonic() - t

    t = time.monotonic()
    paths = MC._make_paths(0, n_paths, settings, VOLATILITY, seed)
    rows = []
    for pol in non_greedy + greedy:
        runs = MC._run_paths(pol, state, engines, settings, constraints, paths)
        scored = MC._build_scored(pol, *runs)
        rows.append(_row(scored, family(pol.policy_id), settings.start_year))
    timings["monte_carlo"] = time.monotonic() - t
    rows.sort(key=lambda r: r["score"], reverse=True)

    assets = state.balance_taxable + state.balance_traditional + state.balance_roth
    tol = tolerance(assets)
    best = rows[0]
    ng = [r for r in rows if r["family"] != "greedy"]
    best_ng = ng[0]
    best_rules = next(r for r in rows if r["family"] == "rules")
    best_no_level = next(r for r in rows if r["family"] in ("rules", "duration"))
    gap = best["score"] - best_ng["score"]
    success_delta = best_ng["success"] - best["success"]
    passed = gap <= tol and success_delta >= -0.01

    out = {
        "case": name,
        "start_year": settings.start_year,
        "assets": float(assets),
        "tolerance": tol,
        "counts": {
            f: sum(r["family"] == f for r in rows)
            for f in ("rules", "duration", "level", "greedy")
        },
        "best": best,
        "best_non_greedy": best_ng,
        "rank_non_greedy": rows.index(best_ng) + 1,
        "best_rules_only": best_rules,
        "rank_rules_only": rows.index(best_rules) + 1,
        "best_no_level": best_no_level,
        "gap": gap,
        "success_delta": success_delta,
        "pass": passed,
        "screening": {},
        "timings": timings,
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "rows": rows,
    }
    if not passed and best["family"] == "greedy":
        duration = [r for r in rows if r["family"] == "duration"] or ng
        out["closest_variant"] = min(
            duration,
            key=lambda r: sum(
                abs(a - b) for a, b in zip(
                    r["schedule"] + [0] * len(best["schedule"]),
                    best["schedule"] + [0] * len(r["schedule"]),
                    strict=False,
                )
            ),
        )
    for diversity in (False, True):
        short = _shortlist(ng, 3, diversity)
        best_short = max(short, key=lambda r: r["score"])
        screened_gap = best["score"] - best_short["score"]
        out["screening"]["diversity" if diversity else "plain"] = {
            "shortlist": [r["id"] for r in short],
            "best": best_short["id"],
            "loss": best_ng["score"] - best_short["score"],
            # The gate again, on what survives screening: a replacement for
            # greedy that only wins when every candidate is scored is no use
            # to a search that screens.
            "gap_to_best": screened_gap,
            "pass": screened_gap <= tol and best_short["success"] - best["success"] >= -0.01,
        }
    if confirm_seed is not None:
        out["confirm"] = _confirm(
            rows, non_greedy + greedy, state, engines, settings, constraints,
            n_paths, confirm_seed,
        )
    return out


def _confirm(rows, policies, state, engines, settings, constraints, n_paths, seed) -> dict | None:
    """Best level-dollar policy vs best greedy policy, paired on a fresh seed."""
    from src.optimization import montecarlo as MC

    level = next((r for r in rows if r["family"] == "level"), None)
    greedy = next((r for r in rows if r["family"] == "greedy"), None)
    if level is None or greedy is None:
        return None
    by_id = {p.policy_id: p for p in policies}
    paths = MC._make_paths(0, n_paths, settings, VOLATILITY, seed)
    g, lv = (
        MC._build_scored(p, *MC._run_paths(p, state, engines, settings, constraints, paths))
        for p in (by_id[greedy["id"]], by_id[level["id"]])
    )
    c = MC.compare_paired(g, lv)  # positive = greedy ahead
    return {
        "seed": seed, "greedy": greedy["id"], "level": level["id"],
        "greedy_score": float(g.score), "level_score": float(lv.score),
        "mean_difference": float(c.mean_difference),
        "ci_low": float(c.ci_low), "ci_high": float(c.ci_high), "verdict": c.verdict,
    }


# ── Report ────────────────────────────────────────────────────────────────────


def _fmt(r: dict) -> str:
    return f"{r['id']} {r['score']:,.0f} ({r['success']:.1%})"


def print_report(results: list[dict]) -> None:
    print(f"{'case':12} {'n r/d/l/g':>11}  best overall | best non-greedy (rank) | "
          "gap / tol | Δsuccess | gate")
    for c in results:
        n = c["counts"]
        print(
            f"{c['case']:12} {n['rules']:>2}/{n['duration']:>2}/{n['level']:>2}/{n['greedy']:>2}  "
            f"{_fmt(c['best'])} [{c['best']['family']}] | "
            f"{_fmt(c['best_non_greedy'])} (#{c['rank_non_greedy']}) | "
            f"{c['gap']:,.0f} / {c['tolerance']:,.0f} | {c['success_delta']:+.1%} | "
            f"{'PASS' if c['pass'] else 'FAIL'}"
        )
    print("\nRules-only (the pre-increment-2 non-greedy set): best and its gap to the best overall")
    for c in results:
        r = c["best_rules_only"]
        gap = c["best"]["score"] - r["score"]
        print(f"{c['case']:12} {_fmt(r)} (#{c['rank_rules_only']})  gap {gap:,.0f}")
    print("\nWithout the level family (rules + duration): best and its gap to the best overall")
    for c in results:
        r = c["best_no_level"]
        print(f"{c['case']:12} {_fmt(r)}  gap {c['best']['score'] - r['score']:,.0f}")
    print("\nStage-1 screening: top 3 by path_value + none. Loss vs every non-greedy "
          "candidate; gate re-applied to the screened best")
    for c in results:
        p, d = c["screening"]["plain"], c["screening"]["diversity"]
        print(f"{c['case']:12} plain {p['loss']:>8,.0f} ({p['best']}) gap {p['gap_to_best']:,.0f} "
              f"{'PASS' if p['pass'] else 'FAIL'} | one-per-rule {d['loss']:>8,.0f} ({d['best']}) "
              f"{'PASS' if d['pass'] else 'FAIL'}")
    confirms = [c for c in results if c.get("confirm")]
    if confirms:
        print("\nConfirmation on a fresh seed: best greedy vs best level (positive = greedy ahead)")
    for c in confirms:
        k = c["confirm"]
        print(f"{c['case']:12} seed {k['seed']}: {k['greedy']} {k['greedy_score']:,.0f} vs "
              f"{k['level']} {k['level_score']:,.0f}  diff {k['mean_difference']:,.0f} "
              f"[{k['ci_low']:,.0f}, {k['ci_high']:,.0f}] {k['verdict']}")
    print("\nTimings (s) and peak RSS")
    for c in results:
        t = c["timings"]
        print(f"{c['case']:12} " + "  ".join(f"{k} {v:.1f}" for k, v in t.items())
              + f"  rss {c['peak_rss_mb']:.0f} MB")
    for c in results:
        if "closest_variant" in c:
            g, v = c["best"], c["closest_variant"]
            print(f"\n{c['case']}: greedy {g['id']} vs closest {v['id']}")
            print(f"  greedy  {g['schedule'][:12]}")
            print(f"  variant {v['schedule'][:12]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--paths", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cases", nargs="*", default=list(CASES), choices=CASES)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--gate", action="store_true", help="exit 1 unless every case passes")
    ap.add_argument("--confirm-seed", type=int,
                    help="also pair the best level and greedy policies on this seed; path r uses "
                         "seed + r, so pick one at least --paths away from --seed")
    args = ap.parse_args(argv)
    if args.confirm_seed is not None and abs(args.confirm_seed - args.seed) < args.paths:
        print(f"warning: seeds {args.seed} and {args.confirm_seed} share paths; "
              "the confirmation is not independent")

    t = time.monotonic()
    with ProcessPoolExecutor(max_workers=len(args.cases)) as pool:
        n = len(args.cases)
        results = list(pool.map(run_case, args.cases, [args.paths] * n, [args.seed] * n,
                                [args.confirm_seed] * n))
    print_report(results)
    passed = all(c["pass"] for c in results)
    print(f"\nGate: {'PASS' if passed else 'FAIL'}  ({args.paths} paths, seed {args.seed}, "
          f"{time.monotonic() - t:.0f} s wall)")
    if args.out:
        args.out.write_text(json.dumps(
            {"paths": args.paths, "seed": args.seed, "pass": passed, "cases": results}, indent=1
        ))
    return 1 if args.gate and not passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
