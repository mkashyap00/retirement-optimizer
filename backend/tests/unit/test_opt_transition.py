"""Tests for the pure single-year transition function (`simulate_year`).

This is the correctness-critical heart of the optimizer. Every tax number here
comes from the REAL engines (federal/state/irmaa/rmd) — never fake math.
"""

import dataclasses
from decimal import Decimal as D

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from src.data.tax_rules.rules import TaxRules
from src.data.tax_rules.social_security import full_retirement_age
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State
from src.optimization.transition import (
    _annual_social_security,
    simulate_year,
    ss_cola_factor,
    taxable_social_security,
)


def _engines():
    rules = TaxRules()
    return Engines(
        FederalTaxEngine(rules),
        StateTaxEngine(rules),
        IRMAACalculator(rules),
        RMDCalculator(rules),
        SocialSecurityCalculator(),
        rules,
    )


def _state():  # retired MFJ couple, 68/66, in CA
    return State(
        year=2025,
        age_self=68,
        age_spouse=66,
        balance_taxable=D("300000"),
        balance_traditional=D("800000"),
        balance_roth=D("100000"),
        basis_taxable=D("200000"),
        filing_status="joint",
        state_code="CA",
        social_security=D("40000"),
        pension=D("20000"),
        medicare_self=True,
        medicare_spouse=True,
        magi_two_years_ago=D("80000"),
        magi_last_year=D("80000"),
    )


def _settings():
    return Settings(
        start_year=2025,
        required_spending=D("80000"),
        income_schedule=[IncomeEntry("pension", D("20000"), None, None)],
    )


def test_conversion_moves_traditional_to_roth_exactly():
    s2, ledger = simulate_year(_state(), D("50000"), _engines(), _settings(), Constraints())
    growth = D("1") + _settings().nominal_return
    assert ledger.conversion == D("50000")
    # roth grew by (100k + 50k) * growth, no roth withdrawal needed
    assert s2.balance_roth == (D("150000") * growth).quantize(D("0.01"))


def test_roth_withdrawal_not_taxed():
    # Force spending high enough to dip into Roth; tax must not include Roth dollars.
    s = _state()
    s.balance_taxable = D("0")
    s.basis_taxable = D("0")
    s.balance_traditional = D("0")
    s.balance_roth = D("500000")
    settings = Settings(
        start_year=2025, required_spending=D("100000"),
        income_schedule=[IncomeEntry("pension", D("20000"), None, None)],
    )
    s2, ledger = simulate_year(s, D("0"), _engines(), settings, Constraints())
    assert ledger.withdrawal_roth > 0
    assert ledger.federal_tax < D("2500")  # only SS/pension partially taxable


def test_taxable_sale_realizes_gain_fraction_not_full_amount():
    settings = Settings(
        start_year=2025, required_spending=D("90000"),
        income_schedule=[IncomeEntry("pension", D("20000"), None, None)],
    )
    s2, ledger = simulate_year(_state(), D("0"), _engines(), settings, Constraints())
    if ledger.withdrawal_taxable > 0:
        # basis fraction is 2/3 -> gains = 1/3 of sale
        expected = ledger.withdrawal_taxable * (D("1") - D("200000") / D("300000"))
        assert abs(ledger.realized_gains - expected) < D("1")


def test_underfunded_year_reports_the_gap_instead_of_failing():
    """A year that cannot fund spending drains what it has and reports the rest.

    Before Step 4 this returned None, so a year funding $135k of a $150k need
    was charged as a total failure — and so was every year after it. It now
    spends all $30k of the portfolio and reports the unmet remainder, which is
    what makes the objective's shortfall term a real dollar amount.
    """
    s = _state()
    s.balance_taxable = s.balance_traditional = s.balance_roth = D("10000")
    s.basis_taxable = D("10000")
    s.social_security = D("0")
    s.pension = D("0")
    settings = Settings(start_year=2025, required_spending=D("200000"))

    next_state, ledger = simulate_year(s, D("0"), _engines(), settings, Constraints())

    # Every account is drained — this is not a year that gave up early.
    assert next_state.balance_taxable == D("0")
    assert next_state.balance_traditional == D("0")
    assert next_state.balance_roth == D("0")
    # $30,000 of assets, no other income, no tax (basis == balance on the
    # taxable account, so the sale realizes no gain): $170,000 short.
    assert ledger.total_tax == D("0")
    assert ledger.net_spendable == D("30000")
    assert ledger.shortfall == D("170000")


def test_funded_year_reports_zero_shortfall():
    """The fixed point converges to within cents; that residue is not a gap."""
    _, ledger = simulate_year(_state(), D("0"), _engines(), _settings(), Constraints())
    assert ledger.net_spendable >= ledger.required_spending - D("1")
    assert ledger.shortfall == D("0")


def test_conversion_is_clamped_to_the_ira_balance():
    """Requesting more than the IRA holds converts what is there, not nothing.

    Schedules are sized on the deterministic balance but replayed on Monte
    Carlo paths where markets fell. Refusing the year would score a market
    drop as a plan failure; clamping converts the remainder.
    """
    s = _state()
    s.balance_traditional = D("100000")
    s.basis_traditional = D("0")
    _, ledger = simulate_year(
        s, D("999999999"), _engines(), _settings(), Constraints()
    )
    assert ledger.conversion + ledger.rmd == D("100000")


def test_taxable_ss_uses_provisional_income_rules():
    # Low other income: none of SS taxable.
    assert taxable_social_security(D("30000"), D("0"), "joint") == D("0")
    # High other income: capped at 85%.
    assert taxable_social_security(D("40000"), D("200000"), "joint") == D("34000")


def test_conversion_with_ira_basis_partly_nontaxable():
    # Pro-rata rule (Form 8606): trad 100k, basis 40k, convert 50k.
    # taxable frac = 1 - 40/100 = 0.6 -> 30k taxable; basis drops by 20k to 20k.
    s = _state()
    s.balance_traditional = D("100000")
    s.basis_traditional = D("40000")
    # give enough taxable cash so we don't dip below and can isolate conversion
    s2, ledger = simulate_year(s, D("50000"), _engines(), _settings(), Constraints())
    assert s2.basis_traditional == D("20000")


# --- hypothesis property ---------------------------------------------------


@given(conv=st.decimals(min_value=D("0"), max_value=D("800000"), places=2))
@hyp_settings(max_examples=60, deadline=None)
def test_property_zero_shortfall_implies_funded(conv):
    _, ledger = simulate_year(_state(), conv, _engines(), _settings(), Constraints())
    if ledger.shortfall == D("0"):
        assert ledger.net_spendable >= D("80000") - D("1")
    else:
        # The two views of the same year must agree exactly.
        assert ledger.shortfall == D("80000") - ledger.net_spendable
    assert ledger.end_taxable >= 0
    assert ledger.end_traditional >= 0
    assert ledger.end_roth >= 0


# ---------------------------------------------------------------------------
# Social Security activation at claim age (settings-driven)
# ---------------------------------------------------------------------------


def _young_state():
    """63/59 couple, not yet claiming — SS must activate mid-simulation."""
    return State(
        year=2026,
        age_self=63,
        age_spouse=59,
        balance_taxable=D("500000"),
        balance_traditional=D("800000"),
        balance_roth=D("100000"),
        basis_taxable=D("400000"),
        filing_status="joint",
        state_code="CA",
        social_security=D("0"),  # nobody claiming at t0
    )


def _ss_settings():
    return Settings(
        start_year=2026,
        required_spending=D("80000"),
        ss_pia_self=D("3500"),
        ss_claim_age_self=67,
        ss_pia_spouse=D("2000"),
        ss_claim_age_spouse=67,
        ss_cola=D("0"),  # these tests are about activation timing, not COLA
    )


def test_social_security_activates_at_claim_age():
    """A 63yo claiming at 67 must see SS switch on in the year they turn 67 —
    regression for benefits being carried forward as $0 forever."""
    engines, settings = _engines(), _ss_settings()
    s = _young_state()
    ss_by_age: dict[int, D] = {}
    for _ in range(8):  # ages 63..70
        result = simulate_year(s, D("0"), engines, settings, Constraints())
        assert result is not None
        s, ledger = result
        # next_state.social_security is the benefit for next year's ages
        ss_by_age[s.age_self] = s.social_security

    assert ss_by_age[64] == D("0"), "no benefit before claim age"
    assert ss_by_age[66] == D("0"), "no benefit the year before claiming"
    assert ss_by_age[67] > D("0"), "self benefit must start at claim age 67"
    # Spouse (4 years younger) not yet claiming at self age 70 (spouse 66)
    at_67 = ss_by_age[67]
    assert ss_by_age[70] == at_67, "flat benefit until spouse claims"
    # Sanity: annualized monthly benefit at FRA for PIA 3500 = 42,000/yr
    assert at_67 == D("3500") * 12


def test_social_security_spouse_activates_independently():
    """Spouse benefit starts in the year the SPOUSE reaches claim age."""
    engines, settings = _engines(), _ss_settings()
    s = _young_state()
    for _ in range(12):  # through self age 74 / spouse 70
        result = simulate_year(s, D("0"), engines, settings, Constraints())
        assert result is not None
        s, _ledger = result
        if s.age_spouse == 67:
            break
    # Spouse just reached 67: household benefit = self + spouse
    assert s.social_security == (D("3500") + D("2000")) * 12


def test_no_ss_config_preserves_legacy_carry_forward():
    """Without claiming config in Settings, State.social_security is carried
    forward unchanged (pre-existing behavior, golden tests depend on it)."""
    engines = _engines()
    s = _state()  # 68/66, social_security=40000, Settings without SS config
    result = simulate_year(s, D("0"), engines, _settings(), Constraints())
    assert result is not None
    s2, _ledger = result
    assert s2.social_security == D("40000")


# ---------------------------------------------------------------------------
# Tax audit worksheet — per-year derivation for independent verification
# ---------------------------------------------------------------------------


def test_ledger_carries_tax_audit_worksheet():
    """Every simulated year carries a raw audit dict whose worksheet lines
    tie to the ledger's reported numbers (within cent quantisation — the
    exact-identity finalisation happens in run_optimization for winner rows,
    outside the simulation hot path)."""
    out = simulate_year(_state(), D("20000"), _engines(), _settings(), Constraints())
    assert out is not None
    _, ledger = out
    audit = ledger.audit
    assert audit is not None

    cent = D("0.011")
    assert abs(audit["federal_tax"] - ledger.federal_tax) <= cent
    assert abs(audit["state_tax"] - ledger.state_tax) <= cent
    assert abs(audit["irmaa"] - ledger.irmaa) <= cent
    assert abs(audit["total_tax"] - ledger.total_tax) <= cent
    assert abs(audit["agi"] - ledger.agi) <= cent
    # Federal components decompose the federal tax
    assert abs(
        audit["federal_tax"]
        - (audit["ordinary_tax"] + audit["ltcg_tax"] + audit["niit"])
    ) <= D("0.02")
    # SS worksheet bound: taxable portion never exceeds 85% of gross
    assert audit["taxable_social_security"] <= D("0.85") * audit["gross_social_security"]
    # IRMAA look-back is the two-years-prior MAGI
    assert audit["irmaa_magi_lookback"] == D("80000")
    assert audit["deduction_type"] in ("standard", "itemized")


def test_audit_reacts_to_conversion_size():
    """Sensitivity: a bigger conversion must raise the taxable traditional
    portion and taxable income in the audit — guards against a stale dict."""
    small = simulate_year(_state(), D("10000"), _engines(), _settings(), Constraints())
    big = simulate_year(_state(), D("60000"), _engines(), _settings(), Constraints())
    a_small, a_big = small[1].audit, big[1].audit
    assert a_big["traditional_taxable_portion"] > a_small["traditional_taxable_portion"]
    assert a_big["taxable_income"] > a_small["taxable_income"]


def test_state_engine_receives_simulated_year_and_inflation():
    """The state tables must be asked for THE SIMULATED YEAR, at the plan's
    inflation, so years past the last published CSV are projected rather than
    silently defaulting to the latest one."""
    import dataclasses as dc

    engines = _engines()
    calls = []
    real = engines.rules.state_brackets

    def spy(state, filing_status, year=None, inflation=None):
        calls.append((year, inflation))
        return real(state, filing_status, year, inflation)

    engines.rules.state_brackets = spy
    state_2026 = dc.replace(_state(), year=2026)
    settings = _settings()
    simulate_year(state_2026, D("0"), engines, settings, Constraints())
    assert calls and set(calls) == {(2026, settings.inflation)}


# ---------------------------------------------------------------------------
# SECURE 2.0 applicable age flows through the simulation
# ---------------------------------------------------------------------------


def test_rmd_respects_secure_2_applicable_age():
    """REGRESSION (found 2026-08-23 verifying against IRS Pub 590-B): the
    simulation charged RMDs from age 73 for everyone. SECURE 2.0 §107 sets the
    applicable age to 75 for anyone born 1960 or later — most of the pre-RMD
    conversion-planning audience — so two years of distributions were forced
    that the law does not require.
    """
    engines = _engines()
    s = _state()
    s.year, s.age_self, s.age_spouse = 2037, 73, 72
    s.balance_traditional = D("1000000")

    born_1964 = Settings(
        start_year=2037, required_spending=D("80000"), birth_year_self=1964,
        income_schedule=[IncomeEntry("pension", D("20000"), None, None)],
    )
    out = simulate_year(s, D("0"), engines, born_1964, Constraints())
    assert out is not None
    assert out[1].rmd == D("0"), "born 1964 must have no RMD at 73"

    # ...and the older cohort is unaffected.
    born_1955 = dataclasses.replace(born_1964, birth_year_self=1955)
    out_old = simulate_year(s, D("0"), engines, born_1955, Constraints())
    assert out_old is not None
    assert out_old[1].rmd > D("0"), "born 1955 must still take an RMD at 73"


def test_rmd_starts_at_75_for_the_1960_plus_cohort():
    engines = _engines()
    s = _state()
    s.year, s.age_self, s.age_spouse = 2039, 75, 74
    s.balance_traditional = D("1000000")
    settings = Settings(
        start_year=2039, required_spending=D("80000"), birth_year_self=1964,
        income_schedule=[IncomeEntry("pension", D("20000"), None, None)],
    )
    out = simulate_year(s, D("0"), engines, settings, Constraints())
    assert out is not None
    # 1,000,000 / 24.6 (IRS Pub 590-B Table III, age 75)
    assert out[1].rmd == D("40650.41")


# ---------------------------------------------------------------------------
# Spousal benefit
# ---------------------------------------------------------------------------
#
# SocialSecurityCalculator.spousal_benefit() was implemented, correct, and
# never called from anywhere. Each person's benefit was computed in isolation,
# so a lower-earning spouse entitled to half the higher earner's PIA received
# only their own — for the whole horizon.


def _couple_settings(pia_self, pia_spouse, claim_self=67, claim_spouse=67):
    return Settings(
        start_year=2026,
        required_spending=D("80000"),
        ss_pia_self=D(pia_self),
        ss_claim_age_self=claim_self,
        ss_pia_spouse=D(pia_spouse),
        ss_claim_age_spouse=claim_spouse,
    )


def _ss_at(settings, age_self, age_spouse):
    """Household annual SS at the given ages."""
    return _annual_social_security(_engines(), settings, age_self, age_spouse)


def test_low_earning_spouse_is_topped_up_to_half_the_primary_pia():
    """$1,200 of their own vs $2,000 (half of $4,000) — they get the $2,000."""
    settings = _couple_settings("4000", "1200")
    total = _ss_at(settings, 67, 67)

    # Primary takes their own full PIA at FRA; spouse takes the 50% floor.
    assert total == (D("4000") + D("2000")) * 12
    # And that is strictly more than computing each in isolation used to give.
    assert total > (D("4000") + D("1200")) * 12


def test_spouse_above_half_the_primary_pia_is_unaffected():
    """REGRESSION: the top-up must never reduce anyone's benefit."""
    settings = _couple_settings("4000", "2500")  # 2500 > half of 4000
    assert _ss_at(settings, 67, 67) == (D("4000") + D("2500")) * 12


def test_no_spousal_top_up_before_the_primary_files():
    """SSA: you cannot draw on a record the worker has not claimed.

    'File and suspend' died with the Bipartisan Budget Act of 2015, so a spouse
    who claims at 62 while the higher earner waits until 70 gets their OWN
    reduced benefit for those eight years — not the spousal floor.
    """
    settings = _couple_settings("4000", "1200", claim_self=70, claim_spouse=62)
    engines = _engines()

    # Spouse is 62 and claiming; primary is 65 and has NOT filed yet.
    own_reduced = engines.ss.monthly_benefit(D("1200"), 62)
    assert _ss_at(settings, 65, 62) == own_reduced * 12
    assert own_reduced < D("2000"), "fixture sanity: the floor would be higher"

    # Primary turns 70 and files — now the spouse is topped up.
    after = _ss_at(settings, 70, 67)
    assert after > engines.ss.monthly_benefit(D("4000"), 70) * 12 + own_reduced * 12


def test_single_filer_is_untouched_by_the_spousal_path():
    settings = Settings(
        start_year=2026, required_spending=D("80000"),
        ss_pia_self=D("3000"), ss_claim_age_self=67,
    )
    expected = _engines().ss.monthly_benefit(D("3000"), 67) * 12
    assert _ss_at(settings, 67, None) == expected


def test_top_up_applies_when_the_SPOUSE_is_the_higher_earner():
    """Do not assume 'self' is the primary — the roles are by PIA, not label."""
    settings = _couple_settings("1200", "4000")
    assert _ss_at(settings, 67, 67) == (D("2000") + D("4000")) * 12


# ---------------------------------------------------------------------------
# Death transition
# ---------------------------------------------------------------------------
#
# The widow's penalty: the survivor files SINGLE — roughly half the bracket
# widths and half the standard deduction — while keeping the larger benefit and
# all of the RMDs. Modelling it is the point; nothing else in the plan changes
# what a couple should convert while both are alive.


def _widow_settings(**over):
    base = dict(
        start_year=2026,
        required_spending=D("90000"),
        ss_pia_self=D("3600"),
        ss_claim_age_self=67,
        ss_pia_spouse=D("1800"),
        ss_claim_age_spouse=67,
        birth_year_self=1959,
        birth_year_spouse=1961,
        first_death_year=2030,
        first_death_is_spouse=True,
    )
    base.update(over)
    return Settings(**base)


def _couple_at(year, age_self, age_spouse):
    return State(
        year=year, age_self=age_self, age_spouse=age_spouse,
        balance_taxable=D("300000"), basis_taxable=D("150000"),
        balance_traditional=D("900000"), balance_roth=D("100000"),
        filing_status="joint", state_code="CA",
        medicare_self=True, medicare_spouse=True,
        magi_two_years_ago=D("100000"), magi_last_year=D("100000"),
    )


def test_year_of_death_still_files_jointly():
    """IRS lets you file a joint return for the year your spouse dies.

    The transition builds NEXT year's state, so this falls out rather than
    needing a special case — but it is exactly the kind of off-by-one that
    would quietly overtax every widowed plan by a year.
    """
    s = _couple_at(2030, 71, 69)
    next_state, ledger = simulate_year(
        s, D("0"), _engines(), _widow_settings(), Constraints()
    )
    assert s.filing_status == "joint", "the death year itself is joint"
    assert next_state.filing_status == "single", "the year after is not"


def test_spouse_death_switches_the_household_to_a_single_filer():
    engines, settings = _engines(), _widow_settings()
    s = _couple_at(2030, 71, 69)
    s, _ = simulate_year(s, D("0"), engines, settings, Constraints())

    assert s.filing_status == "single"
    assert s.age_spouse is None
    assert s.medicare_spouse is False, "IRMAA must stop counting two people"
    assert s.age_self == 72, "the survivor is self, one year older"


def test_the_survivor_keeps_the_larger_benefit_not_the_sum():
    engines, settings = _engines(), _widow_settings()
    both_alive = _annual_social_security(engines, settings, 71, 69)
    widowed = _annual_social_security(engines, settings, 72, None, widowed=True)

    # Higher earner survives: they keep their own $3,600 PIA, losing the
    # $1,800. Born 1959, their FRA is 66 and 10 months, so claiming at 67 earns
    # two months of delayed credit; this used to assume FRA 67 for everyone.
    assert widowed == engines.ss.monthly_benefit(D("3600"), 67, full_retirement_age(1959)) * 12
    assert widowed < both_alive, "household income must FALL"
    assert widowed > both_alive / 2, "but not by half — it is the larger benefit"


def test_low_earning_survivor_is_lifted_to_the_deceased_benefit():
    """The survivor benefit floor: $1,800 of their own becomes $3,600."""
    engines = _engines()
    settings = _widow_settings(first_death_is_spouse=False)  # the EARNER dies
    widowed = _annual_social_security(engines, settings, 72, None, widowed=True)
    # The deceased earner's benefit, on THEIR FRA (born 1959: 66 and 10 months).
    assert widowed == engines.ss.monthly_benefit(D("3600"), 67, full_retirement_age(1959)) * 12


def test_self_dying_first_hands_the_plan_to_the_spouse():
    """REGRESSION GUARD: never assume self outlives spouse.

    Ages, Medicare status and the RMD birth cohort all have to follow the
    person who is actually still alive.
    """
    engines = _engines()
    settings = _widow_settings(first_death_is_spouse=False)
    s = _couple_at(2030, 71, 69)
    s, _ = simulate_year(s, D("0"), engines, settings, Constraints())

    assert s.filing_status == "single"
    assert s.age_spouse is None
    assert s.age_self == 70, "the SPOUSE survives — 69 + 1, not 71 + 1"


def test_rmd_age_follows_the_survivor_birth_cohort():
    """The gap the original plan missed.

    SECURE 2.0 sets the applicable age at 73 for 1951-1959 and 75 for 1960+.
    Self is born 1959 (73), the spouse 1961 (75). If self dies, RMDs must
    follow the survivor — otherwise the plan forces two years of distributions
    that the law does not require.
    """
    from src.optimization.transition import _rmd_birth_year

    spouse_dies = _widow_settings(first_death_is_spouse=True)
    self_dies = _widow_settings(first_death_is_spouse=False)

    before = _couple_at(2029, 70, 68)
    after = _couple_at(2031, 72, 70)

    assert _rmd_birth_year(before, self_dies) == 1959, "both alive: the owner's"
    assert _rmd_birth_year(after, self_dies) == 1961, "self died: the survivor's"
    assert _rmd_birth_year(after, spouse_dies) == 1959, "spouse died: unchanged"


def test_the_deceased_income_stops_but_joint_income_continues():
    engines = _engines()
    settings = _widow_settings(
        income_schedule=[
            IncomeEntry("pension", D("40000"), None, None, "spouse"),
            IncomeEntry("pension", D("10000"), None, None, "self"),
            IncomeEntry("rental", D("12000"), None, None, "joint"),
        ]
    )
    s = _couple_at(2030, 71, 69)
    s, _ = simulate_year(s, D("0"), engines, settings, Constraints())

    assert s.pension == D("10000"), "the spouse's $40k pension dies with them"
    assert s.rental == D("12000"), "joint income survives"


def test_the_transition_is_idempotent_years_later():
    engines, settings = _engines(), _widow_settings()
    s = _couple_at(2030, 71, 69)
    for _ in range(6):
        s, _ = simulate_year(s, D("0"), engines, settings, Constraints())
        if s.year > 2030:
            assert s.filing_status == "single"
            assert s.age_spouse is None
    assert s.year == 2036


def test_no_death_year_leaves_everything_alone():
    """The default must be byte-identical to before this feature existed."""
    engines = _engines()
    alive = _widow_settings(first_death_year=None)
    s = _couple_at(2030, 71, 69)
    nxt, ledger = simulate_year(s, D("0"), engines, alive, Constraints())
    assert nxt.filing_status == "joint"
    assert nxt.age_spouse == 70
    assert nxt.medicare_spouse is True


# ---------------------------------------------------------------------------
# Funding fixed point — convergence
# ---------------------------------------------------------------------------


def _big_conversion_state():
    """63/63 MFJ in CA, mid-plan: taxable nearly spent, a large IRA behind it.

    The shape that breaks the fixed point. Funding a large conversion's tax
    exhausts the taxable account part-way through the solve, so the marginal
    funding dollar switches from capital-gains rates to ordinary rates and the
    iteration's contraction factor jumps to ~0.44 — each pass closes less than
    half the remaining gap.
    """
    return State(
        year=2026,
        age_self=63,
        age_spouse=63,
        balance_taxable=D("175000"),
        balance_traditional=D("2100000"),
        balance_roth=D("575000"),
        basis_taxable=D("0"),
        filing_status="joint",
        state_code="CA",
        pension=D("30000"),
    )


def _big_conversion_settings():
    return Settings(
        start_year=2026,
        required_spending=D("90000"),
        income_schedule=[IncomeEntry("pension", D("30000"), None, None)],
    )


def test_large_conversion_year_still_funds_its_spending():
    """A $515k conversion must not leave the year reporting a shortfall.

    The money is plainly there — over $2.6m remains across the IRA and Roth
    after the year settles. Any gap here is the tax<->withdrawal iteration
    stopping before it converged, and it is reported as an unfunded retirement
    year: one such year flips `feasible` for the whole path, which drives
    `success_probability` to zero for an otherwise sound policy.
    """
    _, ledger = simulate_year(
        _big_conversion_state(), D("515000"), _engines(),
        _big_conversion_settings(), Constraints(),
    )

    remaining = ledger.end_traditional + ledger.end_roth
    assert remaining > D("1000000"), "fixture no longer exercises the solver"
    assert ledger.shortfall == D("0"), (
        f"reported ${ledger.shortfall} short with ${remaining:,.0f} still "
        f"available — the solve stopped early, the household did not run out"
    )
    assert ledger.net_spendable >= ledger.required_spending - D("1")


@given(conv=st.integers(min_value=0, max_value=800000))
@hyp_settings(max_examples=25, deadline=None)
def test_property_money_remaining_implies_no_shortfall(conv):
    """A shortfall may only be reported when the accounts actually ran dry.

    This is the invariant the cap protects. `shortfall` is meant to mean "the
    household could not reach the money"; while any balance remains, a gap can
    only be arithmetic residue from the fixed point, and reporting it as an
    unfunded year is a numerical failure wearing an economic costume.
    """
    _, ledger = simulate_year(
        _big_conversion_state(), D(conv), _engines(),
        _big_conversion_settings(), Constraints(),
    )

    liquid_left = ledger.end_taxable + ledger.end_traditional + ledger.end_roth
    if liquid_left > D("1"):
        assert ledger.shortfall == D("0"), (
            f"conversion ${conv:,}: reported ${ledger.shortfall} short while "
            f"${liquid_left:,.0f} remained unspent"
        )


# ── Surplus cash is saved, not lost ─────────────────────────────────────────
# Cash income beyond what the year spends and pays in tax has to land
# somewhere. It used to land nowhere: the solver stopped withdrawing once cash
# covered spending, and the balance update never deposited the rest, so a
# working year's surplus — or an RMD bigger than the spending — vanished.
# With zero growth every number below is hand-checkable.

def _flat(settings):
    return dataclasses.replace(settings, nominal_return=D("0"), dividend_yield=D("0"))


def test_salary_surplus_is_deposited_in_the_taxable_account_at_full_basis():
    state = State(
        year=2026, age_self=70, age_spouse=70,
        balance_taxable=D("100000"), balance_traditional=D("0"), balance_roth=D("0"),
        basis_taxable=D("100000"), filing_status="joint", state_code="TX",
        salary=D("100000"), medicare_self=True, medicare_spouse=True,
    )
    settings = _flat(Settings(
        start_year=2026, required_spending=D("50000"),
        birth_year_self=1956, birth_year_spouse=1956,
        income_schedule=[IncomeEntry("salary", D("100000"), None, None)],
    ))
    s2, ledger = simulate_year(state, D("0"), _engines(), settings, Constraints())
    surplus = ledger.net_spendable - ledger.required_spending
    assert surplus > D("40000")  # $100k salary, $50k spent, a few $k of tax
    assert s2.balance_taxable == D("100000") + surplus
    # Saved cash is all basis: selling it later realizes no gain.
    assert s2.basis_taxable == D("100000") + surplus
    assert ledger.audit["surplus_saved"] == surplus


def test_rmd_beyond_spending_is_reinvested_not_discarded():
    state = State(
        year=2026, age_self=80, age_spouse=None,
        balance_taxable=D("0"), balance_traditional=D("1000000"), balance_roth=D("0"),
        basis_taxable=D("0"), filing_status="single", state_code="TX",
        medicare_self=True,
    )
    settings = _flat(Settings(start_year=2026, required_spending=D("10000"),
                              birth_year_self=1946))
    s2, ledger = simulate_year(state, D("0"), _engines(), settings, Constraints())
    assert ledger.rmd > D("40000")  # age-80 divisor ~20
    surplus = ledger.net_spendable - ledger.required_spending
    assert s2.balance_taxable == surplus
    assert s2.basis_taxable == surplus
    # Nothing leaves the household except the spending and the tax.
    assert s2.balance_traditional + s2.balance_taxable == (
        D("1000000") - ledger.total_tax - ledger.required_spending
    )


@given(
    conv=st.decimals(min_value=0, max_value=300000, places=0),
    spending=st.decimals(min_value=0, max_value=250000, places=0),
)
@hyp_settings(max_examples=60, deadline=None)
def test_property_household_wealth_is_conserved(conv, spending):
    """With zero growth, wealth changes only by cash income, tax and spending.

    end = start + cash income − tax − spent, where `spent` is what the year
    actually consumed: the full requirement when funded, and only what could
    be raised when not. A conversion moves money between accounts and must not
    appear in the identity at all. The $1 tolerance is the funding solve's own.
    """
    state = _state()
    settings = _flat(dataclasses.replace(_settings(), required_spending=spending))
    s2, ledger = simulate_year(state, conv, _engines(), settings, Constraints())
    cash_income = state.social_security + state.pension
    start = state.balance_taxable + state.balance_traditional + state.balance_roth
    end = s2.balance_taxable + s2.balance_traditional + s2.balance_roth
    spent = min(ledger.required_spending, ledger.net_spendable)
    assert abs(end - (start + cash_income - ledger.total_tax - spent)) <= D("1")


# ── Early spousal claims in the household ledger ────────────────────────────

def test_household_pays_own_plus_reduced_excess_on_an_early_spousal_claim():
    # Primary (born 1960, FRA 67) files at 67 this year; the spouse (born 1965,
    # FRA 67) files at 62 the same year, so both entitlements start at 62:
    # 700 own + 650 reduced excess = 1,350 a month.
    settings = dataclasses.replace(
        _couple_settings("4000", "1000", claim_self=67, claim_spouse=62),
        birth_year_self=1960, birth_year_spouse=1965,
    )
    assert _ss_at(settings, 67, 62) == (D("4000") + D("1350")) * 12


def test_spousal_excess_is_reduced_by_the_spouse_age_when_the_primary_filed():
    # Spouse files at 62 (own 700); the primary, three years older, waits to
    # 68 — when the spouse is 65, 24 months before FRA. The excess is reduced
    # for those 24 months, not the 60 of the spouse's own claim:
    # 1,000 x (1 - 24 x 25/36%) = 833.33. Primary at 68: 4,000 x 1.08 = 4,320.
    settings = dataclasses.replace(
        _couple_settings("4000", "1000", claim_self=68, claim_spouse=62),
        birth_year_self=1960, birth_year_spouse=1963,
    )
    assert _ss_at(settings, 65, 62) == D("700") * 12  # primary has not filed
    assert _ss_at(settings, 69, 66) == (D("4320") + D("1533.33")) * 12


# ── The survivor benefit lasts past the first year ──────────────────────────
# The death transition put the survivor benefit in next year's State, and the
# start of that year recomputed Social Security as if both were alive —
# discarding it. Invisible when the survivor is the higher earner (their own
# benefit IS the larger one), so the fixture makes the DECEASED the higher
# earner in one case. Both born 1956 (FRA 66 + 4 months); claimed at 67, the
# $4,000 PIA carries 8 months of 2/3% credits: 4,213.33 a month, 50,559.96 a
# year — what the survivor keeps whichever spouse dies.

_SURVIVOR_ANNUAL = D("4213.33") * 12


def _death_settings(spouse_dies):
    return Settings(
        start_year=2026, required_spending=D("60000"),
        ss_pia_self=D("1000"), ss_claim_age_self=67,
        ss_pia_spouse=D("4000"), ss_claim_age_spouse=67,
        birth_year_self=1956, birth_year_spouse=1956,
        first_death_year=2026, first_death_is_spouse=spouse_dies,
        ss_cola=D("0"),  # survivor routing, not COLA (see the COLA tests below)
    )


def _ledgers_after_death(spouse_dies, years=3):
    state, settings = _couple_at(2026, 70, 70), _death_settings(spouse_dies)
    ledgers = []
    for _ in range(years):
        state, ledger = simulate_year(state, D("0"), _engines(), settings, Constraints())
        ledgers.append(ledger)
    return ledgers


def test_survivor_benefit_is_paid_every_year_after_the_higher_earner_dies():
    ledgers = _ledgers_after_death(spouse_dies=True)
    for ledger in ledgers[1:]:  # 2027 onward: widowed
        assert ledger.audit["gross_social_security"] == _SURVIVOR_ANNUAL, ledger.year


def test_survivor_benefit_is_paid_every_year_after_the_lower_earner_dies():
    # Self ($1,000) dies; the spouse moves into the self slot and must keep
    # THEIR $4,000-based benefit, not be paid off self's record.
    ledgers = _ledgers_after_death(spouse_dies=False)
    for ledger in ledgers[1:]:
        assert ledger.audit["gross_social_security"] == _SURVIVOR_ANNUAL, ledger.year


def test_both_benefits_are_paid_in_the_year_of_death():
    # 2026 is still a joint year, both past FRA: the $1,000 PIA earns 8 months
    # of credits (1,053.33) plus the unreduced spousal excess, 2,000 - 1,000;
    # the $4,000 PIA earns 4,213.33.
    ledger = _ledgers_after_death(spouse_dies=True, years=1)[0]
    assert ledger.audit["gross_social_security"] == (
        D("1053.33") + D("1000") + D("4213.33")
    ) * 12


# --- RMDs per account owner ---------------------------------------------------
# Each spouse's IRA has its own RMD: that owner's balance divided by the factor
# for THAT owner's age, starting at THAT owner's SECURE 2.0 applicable age.

def _owners_state(trad_self, trad_spouse, age_self, age_spouse):
    return State(
        year=2025, age_self=age_self, age_spouse=age_spouse,
        # Ample cash at full basis: spending never touches the IRAs, so the
        # only traditional distribution is the RMD.
        balance_taxable=D("2000000"), basis_taxable=D("2000000"),
        balance_traditional=trad_self + trad_spouse,
        balance_traditional_spouse=trad_spouse,
        balance_roth=D("0"),
        filing_status="joint", state_code="TX",
        medicare_self=True, medicare_spouse=True,
    )


def _owners_settings(birth_self, birth_spouse):
    return Settings(
        start_year=2025, required_spending=D("60000"),
        birth_year_self=birth_self, birth_year_spouse=birth_spouse,
    )


def test_rmd_is_each_owners_balance_over_their_own_factor():
    # Self 75 (factor 24.6) owns $600k; spouse 70 owns $400k, no RMD yet.
    # $600,000 / 24.6 = $24,390.24 — not $1,000,000 / 24.6 = $40,650.41.
    s = _owners_state(D("600000"), D("400000"), 75, 70)
    _, ledger = simulate_year(s, D("0"), _engines(), _owners_settings(1950, 1955),
                              Constraints())
    assert ledger.rmd == D("24390.24")


def test_an_older_spouse_owes_an_rmd_on_their_own_ira():
    # Self 70, spouse 75 owns all $500k: $500,000 / 24.6 = $20,325.20.
    # Reading self's age, the household took none.
    s = _owners_state(D("0"), D("500000"), 70, 75)
    _, ledger = simulate_year(s, D("0"), _engines(), _owners_settings(1955, 1950),
                              Constraints())
    assert ledger.rmd == D("20325.20")


def test_each_rmd_comes_out_of_its_owners_ira():
    # Only self's IRA paid an RMD, so the spouse's grows untouched.
    s = _owners_state(D("600000"), D("400000"), 75, 70)
    nxt, ledger = simulate_year(s, D("0"), _engines(), _owners_settings(1950, 1955),
                                Constraints())
    assert ledger.withdrawal_traditional == D("0")
    assert nxt.balance_traditional_spouse == D("424000.00")  # 400,000 x 1.06
    assert nxt.balance_traditional == ((D("1000000") - D("24390.24")) * D("1.06")).quantize(
        D("0.01")
    )


def test_a_conversion_draws_on_both_iras_in_proportion():
    # After self's $24,390.24 RMD the IRAs hold $575,609.76 and $400,000.
    # A $97,560.98 conversion takes 40.96...% of it from the spouse's.
    s = _owners_state(D("600000"), D("400000"), 75, 70)
    nxt, _ = simulate_year(s, D("97560.98"), _engines(), _owners_settings(1950, 1955),
                           Constraints())
    after_rmd = D("975609.76")
    spouse_share = D("400000") - D("97560.98") * D("400000") / after_rmd
    assert abs(nxt.balance_traditional_spouse - spouse_share * D("1.06")) < D("0.02")


def test_the_survivor_owns_every_ira_after_the_first_death():
    # The surviving spouse rolls the deceased's IRA into their own; the
    # survivor sits in the `self` slot, so no balance is the spouse's any more.
    s = _owners_state(D("600000"), D("400000"), 75, 70)
    settings = dataclasses.replace(
        _owners_settings(1950, 1955), first_death_year=2025, first_death_is_spouse=False
    )
    nxt, _ = simulate_year(s, D("0"), _engines(), settings, Constraints())
    assert nxt.balance_traditional_spouse == D("0")
    # Next year the survivor (born 1955, 71) has no RMD on the whole balance.
    _, ledger = simulate_year(nxt, D("0"), _engines(), settings, Constraints())
    assert ledger.rmd == D("0")


# --- IRMAA: a real cost, whatever the conversion preference -------------------
# $300k joint look-back MAGI is the third 2026 tier: Part B $405.80 less the
# $202.90 standard, plus $37.50 Part D = $240.40 a month, $2,884.80 a year for
# each person on Medicare.

def _irmaa_couple(medicare_self, medicare_spouse, age_self=70, age_spouse=70):
    return State(
        year=2026, age_self=age_self, age_spouse=age_spouse,
        balance_taxable=D("2000000"), basis_taxable=D("2000000"),
        balance_traditional=D("0"), balance_roth=D("0"),
        filing_status="joint", state_code="TX",
        medicare_self=medicare_self, medicare_spouse=medicare_spouse,
        magi_two_years_ago=D("300000"), magi_last_year=D("300000"),
    )


def test_ignore_still_charges_the_surcharge():
    # Ignore drops IRMAA as a constraint on conversions, not as a cost: the
    # premiums are owed either way.
    settings = Settings(start_year=2026, required_spending=D("60000"))
    for policy in ("ignore", "soft", "strict", "avoid"):
        _, ledger = simulate_year(_irmaa_couple(True, True), D("0"), _engines(),
                                  settings, Constraints(irmaa_policy=policy))
        assert ledger.irmaa == D("5769.60"), policy


def test_a_spouse_on_medicare_pays_the_surcharge_when_self_is_not():
    settings = Settings(start_year=2026, required_spending=D("60000"))
    s = _irmaa_couple(False, True, age_self=60, age_spouse=70)
    _, ledger = simulate_year(s, D("0"), _engines(), settings, Constraints())
    assert ledger.irmaa == D("2884.80")


def test_selling_from_a_taxable_account_at_a_loss_realizes_no_gain():
    """Basis above market value: a sale realizes a loss. Capital losses are
    not modelled as deductions (the $3,000 ordinary offset and carryforward),
    so the gain is zero rather than negative -- conservative -- and the basis
    falls by the sale's own pro-rata share, not by the cash raised."""
    s = State(
        year=2026, age_self=67, age_spouse=None,
        balance_taxable=D("100000"), basis_taxable=D("150000"),
        balance_traditional=D("0"), balance_roth=D("0"),
        filing_status="single", state_code="TX",
    )
    settings = Settings(start_year=2026, required_spending=D("20000"),
                        nominal_return=D("0"), dividend_yield=D("0"))
    nxt, ledger = simulate_year(s, D("0"), _engines(), settings, Constraints())

    assert ledger.withdrawal_taxable == D("20000")
    assert ledger.realized_gains == D("0")
    # $20,000 is a fifth of the account, so a fifth of the $150,000 basis.
    assert nxt.basis_taxable == D("120000")
    assert nxt.balance_taxable == D("80000.00")


# ---------------------------------------------------------------------------
# Social Security COLA. PIAs are start-year dollars; every PIA is indexed by
# the cumulative COLA from start_year BEFORE the calculator applies its
# reductions, credits and cent rounding. Expected values are therefore the
# calculator applied to the indexed PIA — never an already-rounded benefit
# scaled up afterwards.
# ---------------------------------------------------------------------------



def _cola_settings(**kw):
    base = dict(start_year=2026, required_spending=D("80000"), inflation=D("0.03"),
                ss_pia_self=D("3000"), ss_claim_age_self=62, birth_year_self=1964)
    base.update(kw)
    return Settings(**base)


def test_ss_cola_defaults_to_inflation_from_the_start_year():
    s = _cola_settings()
    assert ss_cola_factor(s, 2026) == D("1")
    assert ss_cola_factor(s, 2036) == D("1.03") ** 10
    engines = _engines()
    got = _annual_social_security(engines, s, 72, None, year=2036)
    pia = D("3000") * D("1.03") ** 10
    assert got == engines.ss.monthly_benefit(pia, 62, full_retirement_age(1964)) * 12


def test_ss_cola_indexes_the_pia_before_claiming():
    """A benefit first claimed in year 6 starts from a PIA that has already
    grown for six years — the unclaimed PIA is indexed too."""
    s = _cola_settings(ss_claim_age_self=68)
    engines = _engines()
    got = _annual_social_security(engines, s, 68, None, year=2032)
    want = engines.ss.monthly_benefit(D("3000") * D("1.03") ** 6, 68, full_retirement_age(1964))
    assert got == want * 12


def test_ss_cola_zero_holds_benefits_flat():
    s = _cola_settings(ss_cola=D("0"))
    engines = _engines()
    assert _annual_social_security(engines, s, 72, None, year=2036) == (
        _annual_social_security(engines, s, 62, None, year=2026)
    )


def test_ss_cola_never_negative_under_deflation():
    """SSA pays no COLA when the price index falls."""
    s = _cola_settings(inflation=D("-0.02"))
    assert ss_cola_factor(s, 2040) == D("1")


def test_ss_cola_explicit_rate_overrides_inflation():
    s = _cola_settings(ss_cola=D("0.025"))
    assert ss_cola_factor(s, 2030) == D("1.025") ** 4


def test_spousal_top_up_uses_the_indexed_primary_pia():
    s = _couple_settings("4000", "1200")
    s = dataclasses.replace(s, inflation=D("0.03"))
    engines = _engines()
    got = _annual_social_security(engines, s, 67, 67, year=2031)
    f = D("1.03") ** 5
    # Both claim at FRA 67 (default): own PIA + half-primary excess, all indexed.
    want = (engines.ss.monthly_benefit(D("4000") * f, 67, D("67"))
            + engines.ss.spousal_benefit(D("1200") * f, D("4000") * f, 67, D("67"),
                                         spousal_start_age=67)) * 12
    assert got == want
    assert got > (D("4000") + D("2000")) * 12


def test_survivor_benefit_is_cola_indexed():
    engines, settings = _engines(), _widow_settings()
    settings = dataclasses.replace(settings, inflation=D("0.03"), ss_cola=None)
    year = 2031
    widowed = _annual_social_security(engines, settings, 72, None, widowed=True, year=year)
    f = D("1.03") ** (year - settings.start_year)
    assert widowed == engines.ss.monthly_benefit(
        D("3600") * f, 67, full_retirement_age(1959)) * 12


def test_simulated_benefit_grows_with_cola_year_over_year():
    """End to end through simulate_year: next year's state carries next year's COLA."""
    engines = _engines()
    s = _cola_settings(ss_claim_age_self=62)
    st = State(year=2026, age_self=62, age_spouse=None, balance_taxable=D("500000"),
               balance_traditional=D("0"), balance_roth=D("0"), basis_taxable=D("500000"),
               filing_status="single", state_code="TX")
    st, _ = simulate_year(st, D("0"), engines, s, Constraints())
    year0 = engines.ss.monthly_benefit(D("3000"), 62, full_retirement_age(1964)) * 12
    year1 = engines.ss.monthly_benefit(D("3000") * D("1.03"), 62, full_retirement_age(1964)) * 12
    assert st.social_security == year1
    assert year1 > year0
