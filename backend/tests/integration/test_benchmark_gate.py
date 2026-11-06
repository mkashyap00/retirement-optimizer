"""The greedy-vs-rules benchmark's mechanics, on a small sample.

This is not the gate that decided whether greedy rollouts could be removed --
that is ``python -m benchmarks.greedy_vs_rules --paths 300 --gate``. It checks
that the script still builds its cases, scores every family on shared paths
and applies the written rule.
"""
import pytest
from benchmarks.greedy_vs_rules import _shortlist, run_case, tolerance


@pytest.mark.slow
@pytest.mark.parametrize("case", ["standard", "widow_A"])
def test_benchmark_scores_every_family_and_applies_the_gate(case):
    out = run_case(case, n_paths=100, seed=42)

    assert out["counts"]["rules"] >= 2  # none + at least one _annual rule
    assert out["counts"]["duration"] >= 1
    ids = [r["id"] for r in out["rows"]]
    assert len(ids) == len(set(ids))
    assert out["rows"][0] == out["best"]
    assert out["best_non_greedy"]["family"] != "greedy"
    assert out["tolerance"] == tolerance(out["assets"])
    assert out["gap"] == pytest.approx(out["best"]["score"] - out["best_non_greedy"]["score"])
    assert out["pass"] == (
        out["gap"] <= out["tolerance"] and out["success_delta"] >= -0.01
    )
    for screen in out["screening"].values():
        assert "none" in screen["shortlist"]
        assert screen["loss"] >= 0


def test_tolerance_is_the_larger_of_5000_and_a_quarter_percent():
    assert tolerance(1_000_000) == 5000
    assert tolerance(4_000_000) == 10_000


def test_diversity_cap_keeps_one_candidate_per_bracket():
    rows = [
        {"id": "fill_22_annual", "path_value": 5},
        {"id": "fill_22_thru_2030", "path_value": 4},
        {"id": "fill_12_annual", "path_value": 3},
        {"id": "none", "path_value": 2},
        {"id": "fill_24_thru_2029", "path_value": 1},
    ]
    plain = [r["id"] for r in _shortlist(rows, 3, diversity=False)]
    capped = [r["id"] for r in _shortlist(rows, 3, diversity=True)]
    assert plain == ["fill_22_annual", "fill_22_thru_2030", "fill_12_annual", "none"]
    assert capped == ["fill_22_annual", "fill_12_annual", "fill_24_thru_2029", "none"]
