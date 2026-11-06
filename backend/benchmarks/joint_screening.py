"""Does the joint claim-age search's screening lose a materially better plan?

Two losses, each measured against a REFERENCE that scores every policy in every
eligible claim scenario on the full sample (same paths, same seed):

1. Deterministic screening: the best reference score overall, less the best
   reference score among the candidates the search actually carries into
   Monte Carlo (top ``per_scenario_breadth`` by path_value + ``none`` per
   scenario, every policy at the entered ages).
2. Monte Carlo screening: the best reference score among those carried
   candidates, less the score of the plan the 50-path stage 1 + finalists
   actually picked.

Acceptance is the gate's materiality, max($5,000, 0.25% of investable
assets), and a success probability within 1 point — not identical winner ids:
nearly equivalent plans can legitimately swap places. Both losses AND their
total must pass, and the production winner's score must equal its reference
score.

Run (both seeds; seed 10042's paths share none with seed 42's):

    cd backend && uv run python -m benchmarks.joint_screening --seeds 42 10042 \\
        --out /tmp/joint_screening.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import resource
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from benchmarks.greedy_vs_rules import build_case

CASES = ("salaried_couple", "widow_A", "widow_B")
SUCCESS_TOLERANCE = 0.01


def _setup(name: str):
    from src.api.endpoints.optimization import _ENGINES
    from src.optimization.claiming import AgeControl, ClaimControls

    state, settings, constraints = build_case(name)
    controls = ClaimControls(AgeControl("search"), AgeControl("search"))
    return state, settings, constraints, controls, _ENGINES


def run_joint_case(name: str, seed: int, runs: int) -> dict:
    """The production joint search, in its own process (for a clean peak RSS)."""
    from src.optimization.joint import JointSearchParams, materiality, run_joint_optimization

    logging.disable(logging.WARNING)
    state, settings, constraints, controls, engines = _setup(name)
    t = time.monotonic()
    res = run_joint_optimization(state, engines, settings, constraints, controls,
                                 JointSearchParams(monte_carlo_runs=runs, seed=seed))
    s = res["search"]
    return {
        "case": name, "seed": seed, "wall_seconds": round(time.monotonic() - t, 1),
        "winner": res["joint_winner"],
        "finalists": [(f["key"], f["monte_carlo_paths"]) for f in s["stages"]["finalists"]],
        "baselines": {k: (b["key"], b["monte_carlo_paths"], b["score"])
                      for k, b in s["baselines"].items()},
        "candidates": s["stages"]["candidates"],
        "stage1_runs": s["stages"]["stage1_runs"],
        "scenarios": len(s["scenarios"]),
        "eligible_scenarios": sum(r["eligible"] for r in s["scenarios"]),
        "timings": s["timings_seconds"], "peak_rss_mb": s["peak_rss_mb"],
        "memo_entries": s["memo_entries"],
        "materiality": float(materiality(state)),
    }


def reference_scenario(name: str, key: str, seed: int, runs: int, breadth: int) -> list[dict]:
    """Every policy in one scenario on the full sample, marked screened or not."""
    from src.optimization.claiming import Candidate, enumerate_scenarios
    from src.optimization.joint import screen_scenario
    from src.optimization.montecarlo import score_candidates_staged
    from src.optimization.optimizer import _MemoFederalEngine
    from src.optimization.search import search

    logging.disable(logging.WARNING)
    state, settings, constraints, controls, engines = _setup(name)
    scenarios, _ = enumerate_scenarios(state, settings, engines, controls)
    sc = next(s for s in scenarios if s.key == key)
    memo = dataclasses.replace(engines, federal=_MemoFederalEngine(engines.federal))
    pols = search(sc.state, memo, sc.settings, constraints)
    screened = {p.policy_id for p in (pols if sc.entered else screen_scenario(pols, breadth))}
    scored = score_candidates_staged([Candidate(sc, p) for p in pols], memo, constraints,
                                     runs=runs, stage1_runs=runs, finalists=len(pols),
                                     seed=seed)
    return [{
        "key": sp.candidate.key, "policy_id": sp.candidate.policy.policy_id,
        "scenario": key, "entered": sc.entered,
        "screened": sp.candidate.policy.policy_id in screened,
        "path_rank": i, "score": float(sp.score),
        "success": float(sp.success_probability),
        "paths": [float(v) for v in sp.path_objectives],
    } for i, sp in enumerate(scored)]


def _scenario_keys(name: str) -> list[str]:
    from src.optimization.claiming import enumerate_scenarios

    state, settings, _, controls, engines = _setup(name)
    scenarios, _ = enumerate_scenarios(state, settings, engines, controls)
    return [s.key for s in scenarios if s.eligible]


def _paired(a: list[float], b: list[float]) -> tuple[float, float, float]:
    d = [x - y for x, y in zip(a, b, strict=True)]
    n = len(d)
    mean = sum(d) / n
    se = math.sqrt(sum((x - mean) ** 2 for x in d) / n) / math.sqrt(n)
    return mean, mean - 1.96 * se, mean + 1.96 * se


def summarise(joint: dict, ref: list[dict]) -> dict:
    by_key = {r["key"]: r for r in ref}
    tol = joint["materiality"]
    best_all = max(ref, key=lambda r: (r["score"], r["success"]))
    best_screened = max((r for r in ref if r["screened"]), key=lambda r: (r["score"], r["success"]))
    picked = by_key[joint["winner"]["key"]]
    # Sanity: the production winner's full-sample score IS its reference score.
    consistent = abs(picked["score"] - joint["winner"]["score"]) < 0.01

    def loss(better: dict, chosen: dict) -> dict:
        mean, lo, hi = _paired(better["paths"], chosen["paths"])
        gap = better["score"] - chosen["score"]
        dsucc = better["success"] - chosen["success"]
        return {
            "reference": better["key"], "chosen": chosen["key"],
            "loss": round(gap, 2), "ci": [round(lo, 2), round(hi, 2)],
            "success_gap": round(dsucc, 4),
            "pass": gap <= tol and dsucc <= SUCCESS_TOLERANCE,
        }

    deterministic = loss(best_all, best_screened)
    monte_carlo = loss(best_screened, picked)
    total = loss(best_all, picked)
    rank = sorted(ref, key=lambda r: (r["score"], r["success"]), reverse=True)
    return {
        **{k: joint[k] for k in ("case", "seed")},
        "tolerance": tol,
        "deterministic_screening": deterministic,
        "monte_carlo_screening": monte_carlo,
        "total": total,
        "winner_reference_rank": 1 + next(
            i for i, r in enumerate(rank) if r["key"] == picked["key"]),
        "reference_policies": len(ref),
        "screened_policies": sum(r["screened"] for r in ref),
        "best_overall_was_screened": best_all["screened"],
        "score_consistent": consistent,
        # Each loss can pass on its own while their sum exceeds the allowance,
        # and a winner whose reference score disagrees invalidates all three.
        "pass": (deterministic["pass"] and monte_carlo["pass"] and total["pass"]
                 and consistent),
        "joint": joint,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", nargs="*", default=list(CASES), choices=CASES)
    ap.add_argument("--seeds", nargs="*", type=int, default=[42, 10042])
    ap.add_argument("--runs", type=int, default=300)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    for a, b in zip(args.seeds, args.seeds[1:], strict=False):
        if abs(a - b) < args.runs:
            print(f"warning: seeds {a} and {b} share paths")

    t0 = time.monotonic()
    keys = {name: _scenario_keys(name) for name in args.cases}
    jobs = [(c, s) for s in args.seeds for c in args.cases]
    with ProcessPoolExecutor(max_workers=len(jobs), max_tasks_per_child=1) as jp, \
            ProcessPoolExecutor(max_workers=max(1, args.workers - len(jobs))) as rp:
        joint_f = {(c, s): jp.submit(run_joint_case, c, s, args.runs) for c, s in jobs}
        ref_f = {(c, s, k): rp.submit(reference_scenario, c, k, s, args.runs, 3)
                 for c, s in jobs for k in keys[c]}
        joint = {j: f.result() for j, f in joint_f.items()}
        ref: dict = {}
        for (c, s, _k), f in ref_f.items():
            ref.setdefault((c, s), []).extend(f.result())
    wall = time.monotonic() - t0

    summaries = [summarise(joint[j], ref[j]) for j in jobs]
    for r in summaries:
        j = r["joint"]
        w = j["winner"]
        print(f"\n== {r['case']}  seed {r['seed']}  tolerance ${r['tolerance']:,.0f} "
              f"{'PASS' if r['pass'] else 'FAIL'}")
        print(f"  winner {w['key']}  score {w['score']:,.0f}"
              f"  success {w['success_probability']:.3f}"
              f"  stop {w['conversion_stop_year']}  reference rank {r['winner_reference_rank']}"
              f"/{r['reference_policies']}  consistent={r['score_consistent']}")
        for label in ("deterministic_screening", "monte_carlo_screening", "total"):
            x = r[label]
            print(f"  {label:24s} loss {x['loss']:>10,.0f}"
                  f"  CI [{x['ci'][0]:,.0f}, {x['ci'][1]:,.0f}]"
                  f"  Δsuccess {x['success_gap']:+.4f}  {x['reference']} vs {x['chosen']}"
                  f"  {'ok' if x['pass'] else 'FAIL'}")
        print(f"  scenarios {j['scenarios']} (eligible {j['eligible_scenarios']}), candidates "
              f"{j['candidates']} of {r['reference_policies']} policies, stage1 {j['stage1_runs']}")
        print(f"  finalists {j['finalists']}")
        print(f"  baselines {j['baselines']}")
        print(f"  timings {j['timings']}  wall {j['wall_seconds']}s  peak RSS {j['peak_rss_mb']}"
              f"  memo {j['memo_entries']}")
    ok = all(r["pass"] for r in summaries)
    print(f"\nScreening: {'PASS' if ok else 'FAIL'}  ({wall / 60:.1f} min wall, "
          f"main RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB)")
    if args.out:
        args.out.write_text(json.dumps(summaries, indent=1, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
