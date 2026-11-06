"""benchmarks/joint_screening.summarise: the acceptance condition, on synthetic rows."""
from __future__ import annotations

from benchmarks.joint_screening import summarise

TOL = 6250.0


def _row(key: str, score: float, *, screened: bool, success: float = 0.95) -> dict:
    return {"key": key, "score": score, "success": success, "screened": screened,
            "paths": [score] * 4}


def _joint(score: float = 0.0) -> dict:
    return {"case": "synthetic", "seed": 42, "materiality": TOL,
            "winner": {"key": "picked", "score": score}}


def test_two_passing_losses_whose_total_exceeds_the_allowance_fail():
    ref = [_row("best", 8000, screened=False), _row("kept", 4000, screened=True),
           _row("picked", 0, screened=True)]
    r = summarise(_joint(), ref)
    assert r["deterministic_screening"]["pass"] and r["monte_carlo_screening"]["pass"]
    assert r["total"]["loss"] == 8000 and not r["total"]["pass"]
    assert not r["pass"]


def test_an_inconsistent_winner_score_fails_even_at_zero_loss():
    ref = [_row("picked", 1000, screened=True)]
    assert summarise(_joint(1000), ref)["pass"]
    r = summarise(_joint(1000.5), ref)
    assert not r["score_consistent"] and not r["pass"]


def test_a_success_gap_beyond_one_point_fails():
    ref = [_row("best", 100, screened=True, success=0.96),
           _row("picked", 0, screened=True, success=0.94)]
    r = summarise(_joint(), ref)
    assert not r["monte_carlo_screening"]["pass"] and not r["pass"]
