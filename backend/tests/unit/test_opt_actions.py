"""Tests for generate_conversions — bracket/IRMAA-boundary action generation.

TDD RED phase: write all 5 failing tests from p04-task-3-brief before any
implementation exists.

Scenarios from brief §p04-task-3:
  1. ("none", 0) always present and first.
  2. MFJ age-60 taxable-income $60k in 2025 → fill_12 == 96950 − 60000.
  3. conversion_window="pre_rmd" + age_self=75 → only ("none", 0).
  4. irmaa_policy="avoid" $1k below tier-1 threshold → no conversion > $1k.
  5. all non-none amounts ≤ balance_traditional (clamping).
"""
from decimal import Decimal as D

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalIncome, FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.actions import generate_conversions
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State
from src.optimization.transition import simulate_year

# ─── Shared helpers ───────────────────────────────────────────────────────────


def _engines():
    rules = TaxRules()
    return Engines(
        federal=FederalTaxEngine(rules),
        state=StateTaxEngine(rules),
        irmaa=IRMAACalculator(rules),
        rmd=RMDCalculator(rules),
        ss=SocialSecurityCalculator(),
        rules=rules,
    )


def _settings(**kw):
    defaults = dict(start_year=2025, required_spending=D("50000"))
    defaults.update(kw)
    return Settings(**defaults)


def _state(**kw):
    """Minimal State: MFJ age-60/58, TX (no state income tax), no income by default."""
    defaults = dict(
        year=2025,
        age_self=60,
        age_spouse=58,
        balance_taxable=D("0"),
        balance_traditional=D("500000"),
        balance_roth=D("0"),
        basis_taxable=D("0"),
        filing_status="joint",
        state_code="TX",
    )
    defaults.update(kw)
    return State(**defaults)


# ─── Test 1: none always first ────────────────────────────────────────────────


def test_none_action_always_present_and_first():
    """("none", D("0")) must be the first element regardless of state."""
    result = generate_conversions(_state(), _engines(), _settings(), Constraints())
    assert result[0] == ("none", D("0"))


# ─── Test 2: fill_12 boundary for MFJ 2025 ───────────────────────────────────


def test_fill_12_amount_equals_bracket_room_for_mfj_2025():
    """MFJ age-60 salary $91,500 → taxable_income $60k; fill_12 = 96950 − 60000.

    The test computes the baseline taxable_income via the same engine to stay
    resilient against future deduction changes.
    """
    eng = _engines()
    state = _state(salary=D("91500"))

    # Compute baseline the same way generate_conversions will
    baseline_result = eng.federal.calculate(
        FederalIncome(ordinary=D("91500"), ltcg=D("0"), qualified_dividends=D("0")),
        "joint",
        2025,
        60,
        58,
    )
    # 2025 MFJ 12% bracket upper = 96,950; standard deduction = 31,500
    # → baseline taxable_income = 91,500 − 31,500 = 60,000
    # → fill_12 = 96,950 − 60,000 = 36,950
    expected_fill_12 = D("96950") - baseline_result.taxable_income

    conversions = generate_conversions(state, eng, _settings(), Constraints())
    amounts_by_id = dict(conversions)
    assert "fill_12" in amounts_by_id
    assert amounts_by_id["fill_12"] == expected_fill_12


# ─── Test 3: pre_rmd window + age ≥ 73 ───────────────────────────────────────


def test_pre_rmd_window_with_age_75_returns_only_none():
    """conversion_window='pre_rmd' + age_self=75 must drop all non-none actions."""
    result = generate_conversions(
        _state(age_self=75, age_spouse=73, balance_traditional=D("500000")),
        _engines(),
        _settings(),
        Constraints(conversion_window="pre_rmd"),
    )
    assert result == [("none", D("0"))]


# ─── Test 4: irmaa_policy="avoid" drops conversions crossing next tier ────────


def _first_joint_tier(premium_year, settings):
    """First joint IRMAA threshold for a premium year, projected at the plan's rate."""
    return _engines().rules.irmaa(premium_year, settings.inflation).tiers["joint"][0].magi_upper


def test_irmaa_avoid_drops_all_conversions_crossing_next_tier():
    """State $1k below the IRMAA tier that 2025 MAGI is judged against → only none.

    2025 MAGI sets the 2027 premium, so the tier is 2027's (projected from the
    2026 table at the plan's inflation).
    salary = tier − $1,000  →  baseline_magi ≈ tier − $1,000.
    fill_irmaa_tier ≈ $999 < min_conversion ($1,000) → dropped.
    All other candidates are > $1,000 → cross the tier → IRMAA-dropped.
    """
    tier = _first_joint_tier(2027, _settings())
    state = _state(
        salary=tier - D("1000"),
        medicare_self=True,  # activate fill_irmaa_tier candidate
        balance_traditional=D("1000000"),
    )
    result = generate_conversions(
        state,
        _engines(),
        _settings(),
        Constraints(irmaa_policy="avoid", min_conversion=D("1000")),
    )
    assert result == [("none", D("0"))]


def test_fill_irmaa_tier_accounts_for_spending_driven_gains():
    """`fill_irmaa_tier` must land MAGI at/below the next tier even when spending
    is funded by selling taxable assets (realizing capital gains).

    The gain-free baseline used to size the conversion against income only, so
    the spending-driven gains pushed the actual MAGI far past the tier (a real
    run crossed by ~$60k). The conversion must now be sized so the *simulated*
    year — gains and all — stays under the threshold.
    """
    from src.optimization.transition import simulate_year

    st = _state(
        year=2026,
        age_self=63,          # ≥ 63 activates the IRMAA-tier candidate
        age_spouse=60,
        state_code="CA",
        balance_taxable=D("3000000"),
        basis_taxable=D("1800000"),   # ~40% gain fraction on every sale
        balance_traditional=D("1100000"),
        dividends_qualified=D("35000"),
        dividends_ordinary=D("25000"),
    )
    eng = _engines()
    settings = _settings(
        start_year=2026, required_spending=D("150000"),
        income_schedule=[
            IncomeEntry("qualified_dividend", D("35000"), None, None),
            IncomeEntry("nonqualified_dividend", D("25000"), None, None),
        ],
    )
    cons = Constraints()

    cands = dict(generate_conversions(st, eng, settings, cons))
    assert "fill_irmaa_tier" in cands
    amount = cands["fill_irmaa_tier"]

    sim = simulate_year(st, amount, eng, settings, cons)
    assert sim is not None
    magi = sim[1].magi
    # 2026 MAGI is judged against the 2028 premium year's first joint tier. The
    # conversion must not push the simulated MAGI over it.
    tier = _first_joint_tier(2028, settings)
    assert magi <= tier, (
        f"fill_irmaa_tier overshot the tier: simulated MAGI {magi} > {tier} "
        f"(conversion {amount})"
    )


# ─── Test 5: amounts clamped to balance_traditional ──────────────────────────


def test_all_amounts_clamped_to_balance_traditional():
    """Candidates that exceed balance_traditional are clamped, not dropped.

    With a $50k balance, all level_x and max_pre_rmd amounts are clamped
    to $50k (not zero or missing) and therefore all non-none amounts ≤ $50k.
    """
    small_balance = D("50000")
    # salary=$30k → taxable_income low enough to generate fill_22/24/32 with big rooms
    result = generate_conversions(
        _state(balance_traditional=small_balance, salary=D("30000")),
        _engines(),
        _settings(),
        Constraints(),
    )
    # ("none", 0) always first
    assert result[0] == ("none", D("0"))
    # All non-none amounts must be ≤ balance_traditional
    for action_id, amount in result:
        if action_id != "none":
            assert amount <= small_balance, (
                f"{action_id} amount {amount} exceeds balance_traditional {small_balance}"
            )


# ─── Tests 6-8: bracket-fill headroom sizing ─────────────────────────────────
#
# "Fill the 12% bracket" means one thing: after the conversion, TAXABLE ORDINARY
# income sits at the top of the 12% bracket. Each test below states that
# property for a case where `bracket.upper − baseline_taxable_income` gets it
# wrong, and they fail for three independent reasons.

_ORDINARY_AUDIT_LINES = (
    "salary",
    "pension",
    "rental",
    "interest",
    "ordinary_dividends",
    "traditional_taxable_portion",
    "short_term_gain",
    "capital_loss_deduction",
    "taxable_social_security",
)


def _bracket_top(engines, year, filing_status, rate):
    """The upper edge of the bracket taxed at *rate*, from the tax data itself."""
    brackets = engines.rules.federal(year).brackets[filing_status]
    return next(b.upper for b in brackets if b.rate == rate)


def _total_deduction(engines, ordinary, filing_status, year, age_self, age_spouse):
    """The deduction the federal engine actually grants this household.

    ``deduction_used`` already includes the senior bonus; ``senior_deduction``
    is the same money reported separately, so adding it would double-count.
    """
    result = engines.federal.calculate(
        FederalIncome(ordinary=ordinary),
        filing_status,
        year,
        age_self,
        age_spouse,
    )
    return result.deduction_used


# Spending funded from a taxable account held at full basis: withdrawals realize
# no gain and draw nothing from the IRA, so a conversion moves taxable ordinary
# income dollar for dollar and the closed-form bracket room is exact. Without
# it, _state()'s empty taxable account sends _settings()'s $50,000 of spending
# to the traditional IRA -- ordinary income the closed form does not see.
_CASH_FUNDED = dict(balance_taxable=D("400000"), basis_taxable=D("400000"))


def _taxable_ordinary_income(ledger):
    """Taxable ordinary income from a simulated year's audit lines."""
    audit = ledger.audit
    ordinary = sum(audit[line] for line in _ORDINARY_AUDIT_LINES)
    return max(D("0"), ordinary - audit["deduction"])


def test_fill_12_does_not_spend_bracket_room_on_qualified_dividends():
    """Qualified dividends stack ABOVE ordinary income, so they must not consume
    12%-bracket room.

    $100,000 salary plus $2,000 of qualified dividends. The qualified dividends
    are taxed at capital-gains rates on top of ordinary income; they do not push
    ordinary income up the bracket ladder, so the conversion that fills the 12%
    bracket is unchanged by their presence.
    """
    eng = _engines()
    state = _state(year=2026, salary=D("100000"), dividends_qualified=D("2000"), **_CASH_FUNDED)

    top = _bracket_top(eng, 2026, "joint", D("0.12"))
    deduction = _total_deduction(eng, D("100000"), "joint", 2026, 60, 58)
    expected = top + deduction - D("100000")

    amounts = dict(generate_conversions(state, eng, _settings(start_year=2026), Constraints()))

    assert amounts["fill_12"] == expected, (
        f"fill_12 was {amounts['fill_12']}, expected {expected}. The $2,000 of "
        f"qualified dividends consumed ordinary-bracket room they cannot occupy."
    )


def test_fill_12_offers_the_unused_standard_deduction():
    """Deduction left unused by a small baseline income is room for a conversion.

    $10,000 of ordinary dividends against a standard deduction several times
    larger. Taxable income is zero, but the conversion can absorb the whole
    unused deduction before any of it is taxed at all — so the room runs from
    the deduction, not from zero.
    """
    eng = _engines()
    state = _state(year=2026, dividends_ordinary=D("10000"), **_CASH_FUNDED)

    top = _bracket_top(eng, 2026, "joint", D("0.12"))
    deduction = _total_deduction(eng, D("10000"), "joint", 2026, 60, 58)
    expected = top + deduction - D("10000")

    amounts = dict(generate_conversions(state, eng, _settings(start_year=2026), Constraints()))

    assert amounts["fill_12"] == expected, (
        f"fill_12 was {amounts['fill_12']}, expected {expected}. The "
        f"{deduction} deduction was discarded instead of sheltering the conversion."
    )


def test_fill_12_does_not_overshoot_when_conversion_makes_social_security_taxable():
    """The conversion must be sized against the income the year actually has.

    A retired couple on Social Security funds spending by selling from a taxable
    account with no basis. Those realised gains raise provisional income, which
    makes more of the Social Security taxable — and the conversion itself raises
    it further. Sizing off a baseline that assumes no gains understates ordinary
    income, so the "12% fill" lands well inside the 22% bracket.
    """
    eng = _engines()
    settings = _settings(start_year=2026, required_spending=D("150000"))
    state = _state(
        year=2026,
        age_self=70,
        age_spouse=70,
        social_security=D("99600"),
        dividends_ordinary=D("10000"),
        dividends_qualified=D("2000"),
        balance_taxable=D("600000"),
        basis_taxable=D("0"),
        balance_traditional=D("900000"),
    )

    top = _bracket_top(eng, 2026, "joint", D("0.12"))
    amounts = dict(generate_conversions(state, eng, settings, Constraints()))

    _, ledger = simulate_year(state, amounts["fill_12"], eng, settings, Constraints())
    landed = _taxable_ordinary_income(ledger)

    assert landed <= top, (
        f"fill_12 of {amounts['fill_12']} left taxable ordinary income at "
        f"{landed}, above the 12% top of {top} — a 12% fill landed in the "
        f"{ledger.marginal_rate:.0%} bracket."
    )


def test_fill_12_survives_a_12_percent_marginal_rate_limit():
    """Filling the 12% bracket exactly must not be dropped by a 12% rate limit.

    Every dollar of such a conversion is taxed at 12% or less — that is what
    filling the bracket means. ``marginal_rate`` reports the rate on the NEXT
    dollar, which for a bracket filled to its edge is the next bracket's rate;
    that is a fact about the dollar after the conversion, not about any dollar
    in it. Screening on it forbids the very conversion the rule exists to make.
    """
    eng = _engines()
    state = _state(year=2026, dividends_ordinary=D("10000"), **_CASH_FUNDED)

    top = _bracket_top(eng, 2026, "joint", D("0.12"))
    deduction = _total_deduction(eng, D("10000"), "joint", 2026, 60, 58)
    expected = top + deduction - D("10000")

    amounts = dict(
        generate_conversions(
            state,
            eng,
            _settings(start_year=2026),
            Constraints(marginal_rate_limit=D("0.12")),
        )
    )

    assert amounts.get("fill_12") == expected, (
        f"fill_12 was {amounts.get('fill_12')}, expected {expected} — a 12% "
        f"limit dropped a conversion taxed entirely at 12%."
    )


# ─── SECURE 2.0 applicable age: 73 for 1951-1959, 75 for 1960+ ────────────────
#
# The RMD engine has applied the cohort rule since 7ca2f8f, but the pre_rmd
# window and max_pre_rmd hardcoded 73, so for anyone born 1960 or later both
# stopped two years before distributions actually begin.


def test_pre_rmd_window_stays_open_at_73_for_the_1960_cohort():
    """Born 1962: RMDs start at 75, so at 73 the window is still open."""
    result = generate_conversions(
        _state(age_self=73, age_spouse=71),
        _engines(),
        _settings(birth_year_self=1962),
        Constraints(conversion_window="pre_rmd"),
    )
    assert len(result) > 1


def test_pre_rmd_window_closes_at_75_for_the_1960_cohort():
    result = generate_conversions(
        _state(age_self=75, age_spouse=73),
        _engines(),
        _settings(birth_year_self=1962),
        Constraints(conversion_window="pre_rmd"),
    )
    assert result == [("none", D("0"))]


def test_pre_rmd_window_closes_at_73_for_the_1950s_cohort():
    result = generate_conversions(
        _state(age_self=73, age_spouse=71),
        _engines(),
        _settings(birth_year_self=1955),
        Constraints(conversion_window="pre_rmd"),
    )
    assert result == [("none", D("0"))]


def test_max_pre_rmd_spreads_to_75_for_the_1960_cohort():
    """Born 1961, age 65: ten years to RMDs at 75, not eight to 73."""
    amounts = dict(
        generate_conversions(
            _state(age_self=65, age_spouse=63, balance_traditional=D("500000")),
            _engines(),
            _settings(birth_year_self=1961),
            Constraints(),
            # level_50 is also bal/10; the duplicate-amount filter would keep
            # only the first id for it.
            dedupe=False,
        )
    )
    assert amounts["max_pre_rmd"] == D("500000") / 10


def test_max_pre_rmd_spreads_to_73_for_the_1950s_cohort():
    amounts = dict(
        generate_conversions(
            _state(age_self=65, age_spouse=63, balance_traditional=D("500000")),
            _engines(),
            _settings(birth_year_self=1959),
            Constraints(),
            dedupe=False,
        )
    )
    assert amounts["max_pre_rmd"] == D("500000") / 8



# ─── Spending drawn from the traditional IRA is ordinary income too ──────────
#
# Once the taxable account is empty, the year's spending comes out of the IRA,
# and that withdrawal (grossed up for its own tax, and for the conversion's) is
# ordinary income in the same year. It is only known once the year is solved,
# so the closed-form room never saw it: on the standard household "Fill the 12%
# bracket every year" landed in the 24% bracket from 2030, and a 12% cap let
# those years through.


def _ira_funded_state(**kw):
    """Retired 60/58, no taxable account, no Social Security: every dollar of
    spending above $10k of dividends is an IRA withdrawal."""
    return _state(year=2026, dividends_ordinary=D("10000"),
                  balance_traditional=D("2000000"), **kw)


def test_fill_12_lands_on_the_bracket_top_when_spending_comes_from_the_ira():
    eng = _engines()
    settings = _settings(start_year=2026, required_spending=D("60000"))
    state = _ira_funded_state()
    top = _bracket_top(eng, 2026, "joint", D("0.12"))

    amounts = dict(generate_conversions(state, eng, settings, Constraints()))
    _, ledger = simulate_year(state, amounts["fill_12"], eng, settings, Constraints())
    landed = _taxable_ordinary_income(ledger)

    assert ledger.withdrawal_traditional > 0, "fixture must draw spending from the IRA"
    assert landed <= top, (
        f"fill_12 of {amounts['fill_12']} left taxable ordinary income at {landed}, "
        f"above the 12% top of {top}: the spending withdrawal was not counted."
    )
    # ...and it still fills the bracket, rather than stopping short.
    assert landed > top - D("10"), f"fill_12 stopped at {landed}, short of {top}"


def test_a_12_percent_cap_counts_spending_drawn_from_the_ira():
    """Every candidate a 12% cap lets through must keep the year's last dollar of
    ordinary income at or below the 12% top -- spending withdrawal included."""
    eng = _engines()
    settings = _settings(start_year=2026, required_spending=D("60000"))
    state = _ira_funded_state()
    constraints = Constraints(marginal_rate_limit=D("0.12"))
    top = _bracket_top(eng, 2026, "joint", D("0.12"))

    survivors = generate_conversions(state, eng, settings, constraints)[1:]
    assert survivors, "fixture leaves 12% room, so something should survive"
    for action_id, amount in survivors:
        _, ledger = simulate_year(state, amount, eng, settings, constraints)
        landed = _taxable_ordinary_income(ledger)
        assert landed <= top, (
            f"{action_id} ({amount}) passed a 12% cap but landed at {landed}, "
            f"above the 12% top of {top}."
        )


def test_a_12_percent_cap_forbids_converting_when_spending_alone_fills_it():
    """Spending withdrawals big enough to pass the 12% top on their own leave no
    conversion a 12% cap can allow."""
    eng = _engines()
    settings = _settings(start_year=2026, required_spending=D("160000"))
    state = _ira_funded_state()

    result = generate_conversions(
        state, eng, settings, Constraints(marginal_rate_limit=D("0.12"))
    )
    assert result == [("none", D("0"))]


# ─── A conversion must not spend the year's spending money ───────────────────
#
# Found by the random-household invariants: with no taxable account, "fill
# 22%" converted a whole $50k IRA that the year's $30k of spending needed. The
# engine funds spending from the Roth balance as it stood at the start of the
# year, so the year reported a $19k shortfall with $53k sitting in the Roth --
# a plan nobody could follow. A conversion is now capped so it never creates a
# shortfall the no-conversion year does not have.


def _cash_strapped():
    return _state(year=2026, age_self=55, age_spouse=None, filing_status="single",
                  state_code="CA", salary=D("20000"), balance_traditional=D("50000"))


def test_no_conversion_creates_a_shortfall_the_baseline_does_not_have():
    eng = _engines()
    settings = _settings(start_year=2026, required_spending=D("30000"),
                         birth_year_self=1971)
    state = _cash_strapped()
    _, baseline = simulate_year(state, D("0"), eng, settings, Constraints())
    assert baseline.shortfall == 0, "fixture: the year is fundable without converting"

    offered = generate_conversions(state, eng, settings, Constraints())[1:]
    assert offered, "some smaller conversion still fits"
    for action_id, amount in offered:
        _, ledger = simulate_year(state, amount, eng, settings, Constraints())
        assert ledger.shortfall <= D("1"), (
            f"{action_id} of {amount} left {ledger.shortfall} of spending unfunded."
        )


def test_a_conversion_shrinks_rather_than_disappearing():
    """Converting less is still a real option, so the candidate is cut back to
    the most the year can spare, not dropped."""
    eng = _engines()
    settings = _settings(start_year=2026, required_spending=D("30000"),
                         birth_year_self=1971)
    state = _cash_strapped()
    amounts = dict(generate_conversions(state, eng, settings, Constraints()))
    assert "fill_22" in amounts or "level_100" in amounts
    largest = max(amounts.values())
    _, ledger = simulate_year(state, largest + D("100"), eng, settings, Constraints())
    assert ledger.shortfall > 0, (
        f"{largest} is not the most the year can spare: {largest + 100} still funds it"
    )


# ---------------------------------------------------------------------------
# IRMAA Avoid / Strict: judged on the year as simulated
# ---------------------------------------------------------------------------


def _gain_heavy_retiree():
    """Single, 67, on Medicare, spending funded by selling appreciated stock.
    A conversion's tax is paid by selling more, which realizes more gains, so
    MAGI rises by more than the conversion itself."""
    s = State(
        year=2026, age_self=67, age_spouse=None,
        balance_taxable=D("1500000"), basis_taxable=D("900000"),
        balance_traditional=D("1500000"), balance_roth=D("0"),
        filing_status="single", state_code="CA", medicare_self=True,
    )
    return s, Settings(start_year=2026, required_spending=D("70000"))


def test_avoid_keeps_the_simulated_magi_below_the_next_tier():
    # Baseline MAGI is about $28k, so the next single-filer tier is the first
    # one. Baseline + conversion stayed under it for a $75,000 level_25
    # conversion while the simulated year landed above it. The tier is the one
    # 2026 MAGI is judged against: premium year 2028.
    s, settings = _gain_heavy_retiree()
    engines = _engines()
    tier = engines.rules.irmaa(s.year + 2, settings.inflation).tiers["single"][0].magi_upper
    avoid = Constraints(irmaa_policy="avoid")
    for action_id, amount in generate_conversions(s, engines, settings, avoid):
        _, ledger = simulate_year(s, amount, engines, settings, avoid)
        assert ledger.magi <= tier, (action_id, amount, ledger.magi)


def test_strict_enforces_the_tier_like_avoid():
    # Strict promised to stay below a tier whenever possible. Converting
    # nothing is always possible, so it is the same rule as Avoid.
    s, settings = _gain_heavy_retiree()
    engines = _engines()
    assert generate_conversions(
        s, engines, settings, Constraints(irmaa_policy="strict")
    ) == generate_conversions(s, engines, settings, Constraints(irmaa_policy="avoid"))



# ─── Tax tables past the last published year ─────────────────────────────────


def test_irmaa_sizing_uses_the_premium_year_this_magi_sets():
    """This year's conversion raises this year's MAGI, which sets the premium
    two years out. Sizing against this year's thresholds sized against a table
    that would never apply to it."""
    from src.optimization.actions import _irmaa_tiers_for_this_years_magi

    eng, settings = _engines(), _settings(start_year=2030)
    st = _state(year=2030, age_self=66, age_spouse=64, medicare_self=True)
    assert _irmaa_tiers_for_this_years_magi(st, eng, settings) == (
        eng.rules.irmaa(2032, settings.inflation).tiers["joint"]
    )
    # A death year still files jointly, so that return's MAGI is judged on
    # joint thresholds; the following year's single return on single ones.
    widowed = _state(year=2031, age_self=67, age_spouse=None, filing_status="single",
                     medicare_self=True)
    assert _irmaa_tiers_for_this_years_magi(widowed, eng, settings) == (
        eng.rules.irmaa(2033, settings.inflation).tiers["single"]
    )


def test_future_year_bracket_fill_lands_on_the_projected_boundary():
    """A fill_22 candidate in 2035 is sized on the SAME projected bracket and
    deduction the simulated year is taxed with, so its taxable ordinary
    income lands on the indexed 22% edge, not the frozen 2026 one."""
    eng = _engines()
    settings = _settings(start_year=2035, inflation=D("0.03"))
    st = _state(year=2035, salary=D("40000"), balance_traditional=D("2000000"))
    cands = dict(generate_conversions(st, eng, settings, Constraints()))
    _, ledger = simulate_year(st, cands["fill_22"], eng, settings, Constraints())
    edge = eng.rules.federal(2035, settings.inflation).brackets["joint"][2].upper
    assert edge > D("211400"), "fixture must be past the published table"
    assert abs(ledger.audit["taxable_ordinary_income"] - edge) <= D("1")


# ---------------------------------------------------------------------------
# only=: sizing one named rule
# ---------------------------------------------------------------------------


def test_only_sizes_one_rule_to_its_amount_in_the_full_list():
    """A rule walk reads one id; sizing just that id must give the amount the
    undeduplicated full list gives it, under every filter that can cut it."""
    eng = _engines()
    cases = [
        (_cash_strapped(), _settings(start_year=2026, required_spending=D("30000"),
                                     birth_year_self=1971), Constraints()),
        (*_gain_heavy_retiree(), Constraints(irmaa_policy="avoid")),
        (_state(), _settings(), Constraints(marginal_rate_limit=D("0.12"),
                                            max_conversion_per_year=D("40000"))),
    ]
    requested = {"level_10pct": D("50000")}
    for state, settings, constraints in cases:
        full = dict(generate_conversions(state, eng, settings, constraints,
                                         dedupe=False, requested=requested))
        ids = set(full) | {"fill_10", "fill_12", "fill_22", "fill_24", "fill_irmaa_tier",
                           "level_10pct", "max_pre_rmd"}
        for rule in ids - {"none"}:
            one = generate_conversions(state, eng, settings, constraints, dedupe=False,
                                       requested=requested, only=rule)
            assert one[0] == ("none", D("0"))
            assert dict(one[1:]) == ({rule: full[rule]} if rule in full else {}), rule
