# backend/tests/unit/test_federal_engine.py
from decimal import Decimal as D

import pytest
from src.data.tax_rules.rules import TaxRules
from src.engines.tax.federal import FederalIncome, FederalTaxEngine


@pytest.fixture
def engine():
    return FederalTaxEngine(TaxRules())


def test_golden_mfj_100k_ordinary(engine):
    # MFJ, both 60, $100k ordinary, TY2025. Taxable = 100,000-31,500 = 68,500.
    # Tax = 23,850*.10 + (68,500-23,850)*.12 = 2,385 + 5,358 = 7,743.
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "joint", 2025, 60, 60)
    assert r.total_tax == D("7743.00")
    assert r.deduction_type == "standard"
    assert r.marginal_rate == D("0.12")


def test_golden_single_50k(engine):
    # Single, 40, $50k. Taxable = 34,250. Tax = 1,192.50 + 22,325*.12 = 3,871.50.
    r = engine.calculate(FederalIncome(ordinary=D("50000")), "single", 2025, 40)
    assert r.total_tax == D("3871.50")


def test_golden_senior_deduction_mfj(engine):
    # MFJ both 67, $120k ordinary, MAGI 120k < 150k -> full $12,000 senior bonus,
    # plus the long-standing age-65 add-on to the standard deduction, $1,600 per
    # married person in 2025 (Rev. Proc. 2024-40 §3.15(3)).
    # Deduction = 31,500 + 2*1,600 + 12,000 = 46,700. Taxable = 73,300.
    # Tax = 2,385 + (73,300-23,850)*.12 = 2,385 + 5,934 = 8,319.
    r = engine.calculate(FederalIncome(ordinary=D("120000")), "joint", 2025, 67, 67)
    assert r.senior_deduction == D("12000")
    assert r.deduction_used == D("46700")
    assert r.total_tax == D("8319.00")


def test_golden_senior_phaseout_single(engine):
    # Single, 70, MAGI 100k: reduction = 6% * (100k-75k) = 1,500 -> deduction 4,500.
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "single", 2025, 70)
    assert r.senior_deduction == D("4500")


def test_senior_deduction_applies_when_itemizing(engine):
    # B1 regression: senior deduction survives itemizing.
    from src.engines.tax.federal import ItemizedInputs
    r = engine.calculate(FederalIncome(ordinary=D("200000")), "joint", 2025, 68, 68,
                         itemized=ItemizedInputs(state_tax_paid=D("30000"),
                                                 mortgage_interest=D("15000")))
    assert r.deduction_type == "itemized"
    assert r.senior_deduction > 0


def test_senior_deduction_expires_after_2028(engine):
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "joint", 2029, 70, 70)
    assert r.senior_deduction == D("0")


def test_golden_ltcg_stacks_in_zero_bracket(engine):
    # MFJ 60/60: ordinary 60k, LTCG 50k. Taxable ord = 28,500; ord tax = 2,385
    # + 4,650*.12 = 2,943. LTCG spans 28,500-78,500, all under 96,700 -> 0%.
    r = engine.calculate(FederalIncome(ordinary=D("60000"), ltcg=D("50000")),
                         "joint", 2025, 60, 60)
    assert r.ordinary_tax == D("2943.00")
    assert r.ltcg_tax == D("0.00")


def test_golden_unused_deduction_offsets_ltcg(engine):
    # B2 regression. Single 60: ordinary 10k, LTCG 60k. Deduction 15,750:
    # taxable_ordinary = 0, pref_taxable = 70,000-15,750 = 54,250.
    # Stack from 0: 48,350 @ 0%, remaining 5,900 @ 15% = 885.
    r = engine.calculate(FederalIncome(ordinary=D("10000"), ltcg=D("60000")),
                         "single", 2025, 60)
    assert r.ltcg_tax == D("885.00")
    assert r.total_tax == D("885.00")


def test_ltcg_spanning_two_brackets(engine):
    # Single 60: ordinary 63,750 (taxable 48,000), LTCG 10,000.
    # Stack floor 48,000: 350 @ 0%, 9,650 @ 15% = 1,447.50.
    r = engine.calculate(FederalIncome(ordinary=D("63750"), ltcg=D("10000")),
                         "single", 2025, 60)
    assert r.ltcg_tax == D("1447.50")


# ── Task 3: SALT phase-down + NIIT ──────────────────────────────────────────

def test_salt_phase_down_high_magi(engine):
    # MAGI 600k: cap = max(10k, 40k - 30%*(600k-500k)) = max(10k, 10k) = 10k.
    assert engine.salt_cap(D("600000"), "joint", 2025) == D("10000")
    # MAGI 550k: 40k - 15k = 25k.
    assert engine.salt_cap(D("550000"), "joint", 2025) == D("25000")
    # MAGI 400k: full 40k (below phase-down start).
    assert engine.salt_cap(D("400000"), "joint", 2025) == D("40000")


def test_niit_applied(engine):
    # MFJ, AGI 300k of which 40k investment income.
    # NIIT = 3.8% * min(300k-250k, 40k) = 3.8% * 40k = 1,520.
    r = engine.calculate(FederalIncome(ordinary=D("260000"), ltcg=D("40000"),
                                       investment_income=D("40000")),
                         "joint", 2025, 60, 60)
    assert r.niit == D("1520.00")


def test_no_niit_below_threshold(engine):
    r = engine.calculate(FederalIncome(ordinary=D("100000"), ltcg=D("20000"),
                                       investment_income=D("20000")),
                         "joint", 2025, 60, 60)
    assert r.niit == D("0.00")


# ── Age-65 deductions (2026 figures: Rev. Proc. 2025-32 §.14; Schedule 1-A) ──
# Two separate provisions stack for anyone 65 or older:
#   * the permanent ADDITIONAL standard deduction, IRC §63(f): $2,050 for an
#     unmarried filer, $1,650 per eligible spouse on a joint return — standard
#     deduction only, lost when itemizing;
#   * the temporary $6,000 senior bonus, OBBBA §70103, 2025-2028, taken either
#     way. Schedule 1-A Part V reduces the $6,000 by 6% of MAGI over the
#     threshold ONCE (line 35) and then enters that reduced amount for EACH
#     eligible spouse (lines 36a, 36b) — it is not one phaseout of a pooled $12k.


def test_single_senior_gets_the_additional_standard_deduction(engine):
    # Deduction = 16,100 + 2,050 + 6,000 = 24,150. Taxable = 25,850.
    # Tax = 12,400*.10 + 13,450*.12 = 1,240 + 1,614 = 2,854.
    r = engine.calculate(FederalIncome(ordinary=D("50000")), "single", 2026, 70)
    assert r.deduction_used == D("24150")
    assert r.total_tax == D("2854.00")


def test_no_additional_deduction_before_65(engine):
    r = engine.calculate(FederalIncome(ordinary=D("50000")), "single", 2026, 64)
    assert r.deduction_used == D("16100")


def test_joint_additional_deduction_counts_each_spouse_65_plus(engine):
    # One spouse 70, one 60, MAGI 100k (no phaseout): 32,200 + 1,650 + 6,000.
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "joint", 2026, 70, 60)
    assert r.deduction_used == D("39850")
    # Both 70: 32,200 + 2*1,650 + 2*6,000.
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "joint", 2026, 70, 70)
    assert r.deduction_used == D("47500")


def test_senior_bonus_phases_out_per_person_not_on_the_pooled_amount(engine):
    # MAGI 200k: line 34 = 6% * 50,000 = 3,000; line 35 = 3,000 each -> 6,000.
    r = engine.calculate(FederalIncome(ordinary=D("200000")), "joint", 2026, 70, 70)
    assert r.senior_deduction == D("6000")
    # MAGI 250k: line 34 = 6,000 -> line 35 = 0 for each spouse.
    r = engine.calculate(FederalIncome(ordinary=D("250000")), "joint", 2026, 70, 70)
    assert r.senior_deduction == D("0")
    # Only one eligible spouse: 3,000, the same either way.
    r = engine.calculate(FederalIncome(ordinary=D("200000")), "joint", 2026, 70, 60)
    assert r.senior_deduction == D("3000")


def test_additional_deduction_counts_in_the_standard_vs_itemized_choice(engine):
    # Both 70: standard = 32,200 + 2*1,650 = 35,500. Itemizing 34,000 beats the
    # bare 32,200 but not 35,500, so the standard deduction is the right pick.
    from src.engines.tax.federal import ItemizedInputs
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "joint", 2026, 70, 70,
                         itemized=ItemizedInputs(mortgage_interest=D("34000")))
    assert r.deduction_type == "standard"
    assert r.deduction_used == D("35500") + D("12000")


def test_itemizers_lose_the_additional_deduction_but_keep_the_bonus(engine):
    from src.engines.tax.federal import ItemizedInputs
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "joint", 2026, 70, 70,
                         itemized=ItemizedInputs(mortgage_interest=D("40000")))
    assert r.deduction_type == "itemized"
    assert r.deduction_used == D("40000") + D("12000")


def test_additional_deduction_outlives_the_temporary_bonus(engine):
    # 2029: the bonus has expired; §63(f) has not (2026 amounts carry forward).
    r = engine.calculate(FederalIncome(ordinary=D("100000")), "joint", 2029, 70, 70)
    assert r.senior_deduction == D("0")
    assert r.deduction_used == D("35500")
