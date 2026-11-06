"""Projection of tax tables past the last published year (data/tax_rules/indexing.py)."""
from decimal import Decimal as D

import pytest
from src.data.tax_rules.federal import FEDERAL
from src.data.tax_rules.indexing import factor, statutory_salt
from src.data.tax_rules.irmaa import IRMAA
from src.data.tax_rules.rules import TaxRules
from src.data.tax_rules.state import STATE_SURCHARGES
from src.engines.irmaa import IRMAACalculator
from src.engines.tax.federal import FederalIncome, FederalTaxEngine, ItemizedInputs
from src.engines.tax.state import StateIncome, StateTaxEngine
from src.optimization.transition import taxable_social_security

R = D("0.03")


@pytest.fixture
def rules():
    return TaxRules()


def _uppers(brackets):
    return [b.upper for b in brackets]


# ── Published years win ─────────────────────────────────────────────────────


def test_published_years_are_returned_as_published(rules):
    for y in (2025, 2026):
        assert rules.federal(y, R) is FEDERAL[y]
        assert rules.irmaa(y, R) is IRMAA[y]
    assert rules.state_brackets("CA", "joint", 2025, R) == rules.state_brackets("CA", "joint", 2025)


def test_projection_never_mutates_the_published_tables(rules):
    before = (FEDERAL[2026].brackets["joint"][:], IRMAA[2026].tiers["joint"][:])
    rules.federal(2040, R)
    rules.irmaa(2040, R)
    assert (FEDERAL[2026].brackets["joint"], IRMAA[2026].tiers["joint"]) == before


def test_projected_tables_are_cached_per_year_and_rate(rules):
    assert rules.federal(2035, R) is rules.federal(2035, R)
    assert rules.federal(2035, R) is not rules.federal(2035, D("0.02"))


def test_no_rate_keeps_the_legacy_clamp(rules):
    assert rules.federal(2040) is FEDERAL[2026]
    assert rules.irmaa(2040) is IRMAA[2026]


# ── Zero inflation reproduces the frozen INDEXED fields ─────────────────────


def test_zero_inflation_reproduces_frozen_indexed_fields(rules):
    base, fy = FEDERAL[2026], rules.federal(2040, D("0"))
    assert fy.brackets == base.brackets
    assert fy.ltcg_brackets == base.ltcg_brackets
    assert fy.standard_deduction == base.standard_deduction
    assert fy.aged_addition == base.aged_addition
    assert rules.irmaa(2040, D("0")).tiers == IRMAA[2026].tiers
    assert rules.state_brackets("CA", "joint", 2040, D("0")) == rules.state_brackets("CA", "joint")
    # ...but statutory changes still apply: SALT reverts to $10,000 in 2030.
    assert fy.salt.cap["joint"] == D("10000")


def test_negative_inflation_does_not_shrink_brackets(rules):
    assert factor(D("-0.02"), 10) == D("1")
    assert rules.federal(2040, D("-0.02")).brackets == FEDERAL[2026].brackets


# ── One factor from the published base, statutory rounding ──────────────────


def test_brackets_are_one_factor_from_the_published_base_rounded_down_to_25(rules):
    f = (1 + R) ** 10
    for status in ("single", "joint"):
        got = _uppers(rules.federal(2036, R).brackets[status])
        want = [None if u is None else (u * f / 25).to_integral_value(rounding="ROUND_FLOOR") * 25
                for u in _uppers(FEDERAL[2026].brackets[status])]
        assert got == want
        assert all(u % 25 == 0 for u in got if u is not None)


def test_deductions_round_down_to_50(rules):
    fy = rules.federal(2033, R)
    assert all(v % 50 == 0 for v in fy.standard_deduction.values())
    assert all(v % 50 == 0 for v in fy.aged_addition.values())
    assert fy.standard_deduction["joint"] > FEDERAL[2026].standard_deduction["joint"]


def test_senior_bonus_still_expires_after_2028(rules):
    eng = FederalTaxEngine(rules)
    inc = FederalIncome(ordinary=D("80000"))
    assert eng.calculate(inc, "joint", 2028, 70, 70, inflation=R).senior_deduction > 0
    assert eng.calculate(inc, "joint", 2029, 70, 70, inflation=R).senior_deduction == 0


def test_niit_thresholds_are_not_indexed(rules):
    assert rules.federal(2040, R).niit.threshold == FEDERAL[2026].niit.threshold


def test_social_security_taxation_thresholds_stay_fixed():
    """$32,000 / $44,000 joint are statutory and live outside the tables."""
    assert taxable_social_security(D("20000"), D("21999"), "joint") == D("0")
    assert taxable_social_security(D("20000"), D("23000"), "joint") > D("0")


def test_effective_federal_rate_is_stable_when_income_and_tables_grow_together(rules):
    eng = FederalTaxEngine(rules)
    base_income = D("150000")
    rate0 = eng.calculate(FederalIncome(ordinary=base_income), "joint", 2026, 60, 60,
                          inflation=R).total_tax / base_income
    for n in (1, 5, 10, 20):
        income = base_income * (1 + R) ** n
        res = eng.calculate(FederalIncome(ordinary=income), "joint", 2026 + n, 60, 60,
                            inflation=R)
        assert abs(res.total_tax / income - rate0) < D("0.001"), n


# ── SALT: the enacted schedule, not inflation ───────────────────────────────


def test_salt_schedule():
    assert statutory_salt(2026).phase_down_start == D("505000")
    assert statutory_salt(2026).cap["joint"] == D("40400")
    assert statutory_salt(2027).cap["joint"] == D("40804")
    assert statutory_salt(2027).phase_down_start == D("510050")
    assert statutory_salt(2029).cap["joint"].quantize(D("1")) == D("41624")
    assert statutory_salt(2030).cap["joint"] == D("10000")
    assert FEDERAL[2026].salt == statutory_salt(2026)


@pytest.mark.parametrize("year, magi, cap", [
    (2026, D("400000"), D("40400")),
    (2026, D("605000"), D("10400")),                 # 40,400 − 30% × 100,000
    (2029, D("400000"), statutory_salt(2029).cap["joint"]),
    (2030, D("400000"), D("10000")),                 # reverted; no phase-down
])
def test_itemizer_salt_cap_by_year(rules, year, magi, cap):
    eng = FederalTaxEngine(rules)
    res = eng.calculate(
        FederalIncome(ordinary=magi), "joint", year, 60, 60,
        itemized=ItemizedInputs(state_tax_paid=D("60000"), mortgage_interest=D("30000")),
        inflation=R,
    )
    assert res.deduction_type == "itemized"
    assert res.deduction_used == cap + D("30000")


# ── IRMAA: thresholds indexed, top tier frozen through 2027 ─────────────────


def test_irmaa_thresholds_round_to_1000_and_premiums_do_not_move(rules):
    y = rules.irmaa(2032, R)
    for status in ("single", "joint"):
        for t, base in zip(y.tiers[status], IRMAA[2026].tiers[status], strict=True):
            assert t.part_b_monthly == base.part_b_monthly
            assert t.part_d_monthly == base.part_d_monthly
            if t.magi_upper is not None:
                assert t.magi_upper % 1000 == 0
    assert y.part_b_standard == IRMAA[2026].part_b_standard


def test_irmaa_top_tier_frozen_through_2027_then_indexed(rules):
    top = {"single": D("500000"), "joint": D("750000")}
    for status, frozen in top.items():
        t27 = [t.magi_upper for t in rules.irmaa(2027, R).tiers[status] if t.magi_upper][-1]
        t28 = [t.magi_upper for t in rules.irmaa(2028, R).tiers[status] if t.magi_upper][-1]
        assert t27 == frozen
        assert t28 == (frozen * (1 + R) / 1000).to_integral_value(rounding="ROUND_HALF_UP") * 1000
    # lower tiers index from the 2026 base in 2027 already
    first27 = rules.irmaa(2027, R).tiers["joint"][0].magi_upper
    assert first27 == D("225000")    # 218,000 × 1.03 = 224,540 -> nearest 1,000


def test_irmaa_lookback_uses_the_premium_years_projected_table(rules):
    """A 2030 premium is judged on 2028 MAGI against the 2030 thresholds."""
    calc = IRMAACalculator(rules)
    magi = D("219000")   # above the 2026 first tier, below the projected 2030 one
    assert calc.annual_surcharge(magi, "joint", 2030, 2) > 0          # frozen clamp
    assert calc.annual_surcharge(magi, "joint", 2030, 2, inflation=R) == 0


# ── State: California only; the $1M surcharge stays fixed ───────────────────


def test_california_ordinary_brackets_index_and_the_surcharge_threshold_does_not(rules):
    f = (1 + R) ** 5
    got = _uppers(rules.state_brackets("CA", "joint", 2030, R))
    base = _uppers(rules.state_brackets("CA", "joint", 2025))
    assert got[:-1] == [(u * f).to_integral_value(rounding="ROUND_HALF_UP") for u in base[:-1]]
    assert STATE_SURCHARGES["CA"] == (D("1000000"), D("0.01"))
    eng = StateTaxEngine(rules)
    ded = rules.state_standard_deduction("CA", "single", 2030, R)
    above = eng.calculate(StateIncome(ordinary=D("1200000") + ded), "CA", "single", 2030, R)
    below = eng.calculate(StateIncome(ordinary=D("1199000") + ded), "CA", "single", 2030, R)
    # The last $1,000 sits above both the top ordinary bracket and $1M: 13.3%.
    assert above - below == D("133.00")


def test_other_states_keep_their_published_schedule(rules):
    assert rules.state_brackets("NY", "joint", 2035, R) == rules.state_brackets("NY", "joint")
    assert rules.state_standard_deduction("NY", "joint", 2035, R) == (
        rules.state_standard_deduction("NY", "joint"))
