"""Golden tests for Social Security calculator engine (Plan 03 Task 7)."""
from decimal import Decimal

from src.engines.social_security import SocialSecurityCalculator

D = Decimal


def test_claim_at_62_fra_67_is_70pct():
    # 36 months * 5/9% + 24 months * 5/12% = 20% + 10% = 30% reduction
    calc = SocialSecurityCalculator()
    assert calc.monthly_benefit(D("2000"), 62) == D("1400.00")


def test_claim_at_fra_is_100pct():
    assert SocialSecurityCalculator().monthly_benefit(D("2000"), 67) == D("2000.00")


def test_claim_at_70_is_124pct():
    # 8%/year * 3 years delayed credits
    assert SocialSecurityCalculator().monthly_benefit(D("2000"), 70) == D("2480.00")


def test_spousal_tops_up_to_half_primary():
    calc = SocialSecurityCalculator()
    # own PIA 800, primary PIA 2400 -> spousal = max(800, 1200) at FRA
    assert calc.spousal_benefit(D("800"), D("2400"), 67, D("67")) == D("1200.00")


# ---------------------------------------------------------------------------
# Survivor benefit
# ---------------------------------------------------------------------------


def test_survivor_takes_the_larger_benefit_never_the_sum():
    calc = SocialSecurityCalculator()
    assert calc.survivor_benefit(D("1800"), D("3600"), 70) == D("3600.00")
    assert calc.survivor_benefit(D("3600"), D("1800"), 70) == D("3600.00")


def test_survivor_benefit_is_reduced_before_full_retirement_age():
    """71.5% at 60, rising to 100% at FRA — its own curve, not the own-benefit
    or spousal one."""
    calc = SocialSecurityCalculator()
    assert calc.survivor_benefit(D("0"), D("2000"), 60) == D("1430.00")  # 71.5%
    assert calc.survivor_benefit(D("0"), D("2000"), 67) == D("2000.00")  # 100%
    mid = calc.survivor_benefit(D("0"), D("2000"), 63)
    assert D("1430") < mid < D("2000")


def test_no_survivor_benefit_before_sixty():
    calc = SocialSecurityCalculator()
    # Own benefit still shows through; the survivor portion contributes nothing.
    assert calc.survivor_benefit(D("900"), D("3000"), 55) == D("900.00")


def test_survivor_basis_ignores_delayed_credits_never_earned():
    """A worker planning to claim at 70 who dies at 62 earned no credits.

    Crediting them would overstate survivor income and understate the widow's
    penalty — the exact bias this feature exists to remove, so it is worth a
    test of its own rather than a comment.
    """
    calc = SocialSecurityCalculator()
    # Died at 62, planned 70 -> basis is the FRA amount (PIA), not 124% of it.
    assert calc.survivor_basis_claim_age(70, age_at_death=62) == 67
    # Died at 69 without claiming -> credits earned to death do count.
    assert calc.survivor_basis_claim_age(70, age_at_death=69) == 69
    # Had already claimed at 65 -> the survivor inherits that reduced amount.
    assert calc.survivor_basis_claim_age(65, age_at_death=80) == 65
    # Unknown age at death -> fall back to the planned claim age.
    assert calc.survivor_basis_claim_age(70, age_at_death=None) == 70
    # Never credits past 70.
    assert calc.survivor_basis_claim_age(70, age_at_death=95) == 70


# ── Dual entitlement: own benefit + reduced spousal EXCESS ──────────────────
# SSA POMS RS 00615.020 (Method C): the own retirement benefit is computed on
# its own; the spousal benefit is only the EXCESS of half the primary's PIA
# over the recipient's UNREDUCED own PIA, reduced for the months before FRA at
# which SPOUSAL entitlement begins. FRA 67 here; 60 months early reduces a
# retirement benefit 30% (36 x 5/9% + 24 x 5/12%) and a spousal one 35%
# (36 x 25/36% + 24 x 5/12%).

def test_early_dual_entitlement_adds_the_reduced_excess_to_the_reduced_own():
    # Own: 1,000 x 0.70 = 700. Excess: 2,000 - 1,000 = 1,000, x 0.65 = 650.
    calc = SocialSecurityCalculator()
    assert calc.spousal_benefit(D("1000"), D("4000"), 62, D("67")) == D("1350.00")


def test_no_excess_when_own_pia_is_at_least_half_the_primary():
    # 2,500 >= 2,000: own reduced benefit only, 2,500 x 0.70.
    calc = SocialSecurityCalculator()
    assert calc.spousal_benefit(D("2500"), D("4000"), 62, D("67")) == D("1750.00")


def test_zero_own_pia_gets_the_reduced_spousal_benefit():
    calc = SocialSecurityCalculator()
    assert calc.spousal_benefit(D("0"), D("4000"), 62, D("67")) == D("1300.00")


def test_excess_is_reduced_by_the_age_spousal_entitlement_began():
    # Own claimed at 62 (700); the primary files when the recipient is 66, so
    # the excess is 12 months early: 1,000 x (1 - 12 x 25/36%) = 916.67.
    calc = SocialSecurityCalculator()
    got = calc.spousal_benefit(D("1000"), D("4000"), 62, D("67"), spousal_start_age=66)
    assert got == D("1616.67")


def test_delayed_credits_raise_the_own_benefit_but_not_the_excess():
    # Own at 70: 1,000 x 1.24 = 1,240. Excess from the UNREDUCED own PIA,
    # 2,000 - 1,000 = 1,000, unreduced at 70 — spousal benefits earn no credits.
    calc = SocialSecurityCalculator()
    assert calc.spousal_benefit(D("1000"), D("4000"), 70, D("67")) == D("2240.00")
