"""Tests for the deterministic full-horizon path evaluation (simulate_path).

TDD: tests written BEFORE implementation. All three tests use real engines —
no fake math, no mocked tax results.
"""

from decimal import Decimal as D

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.evaluate import objective_value, simulate_path
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State


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


def _all_roth_state():
    """Retired single, age 65, TX — only Roth balance, zero taxable income."""
    return State(
        year=2025,
        age_self=65,
        age_spouse=None,
        balance_taxable=D("0"),
        balance_traditional=D("0"),
        balance_roth=D("500000"),
        basis_taxable=D("0"),
        filing_status="single",
        state_code="TX",
    )


def _all_roth_settings():
    return Settings(
        start_year=2025,
        required_spending=D("20000"),
        simulation_years=5,
       
    )


def _normal_state():
    """Retired MFJ couple, 68/66, CA — same fixture as transition tests."""
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


def _normal_settings():
    return Settings(
        start_year=2025,
        required_spending=D("80000"),
        simulation_years=5,
       
        income_schedule=[IncomeEntry("pension", D("20000"), None, None)],
    )


# ---------------------------------------------------------------------------
# Test (a): All-Roth household → path_value ≈ discounted terminal estate
# ---------------------------------------------------------------------------


def test_all_roth_path_value_equals_discounted_terminal_estate():
    """With zero taxable income and all-Roth spending, path_value == PV(terminal estate).

    Roth withdrawals are never taxable, TX has no state income tax, the person
    has no Medicare surcharge, no salary/SS/pension.  Every year's total_tax is
    $0, so path_value = PV(-0) + PV(estate) = PV(estate).  Tolerance: $1.
    """
    result = simulate_path(
        _all_roth_state(), [], _engines(), _all_roth_settings(), Constraints()
    )

    assert result.feasible is True, "500k Roth should fund 5 years of $20k spending"
    assert len(result.ledgers) == 5

    n = len(result.ledgers)
    d = _all_roth_settings().discount_rate
    discounted_estate = result.terminal_estate / (D("1") + d) ** n

    assert abs(result.path_value - discounted_estate) < D("1"), (
        f"path_value={result.path_value} should be within $1 of "
        f"discounted_estate={discounted_estate} "
        f"(lifetime_taxes_nominal={result.lifetime_taxes_nominal})"
    )


# ---------------------------------------------------------------------------
# Test (b): lifetime_taxes_nominal == sum(ledger.total_tax)
# ---------------------------------------------------------------------------


def test_lifetime_taxes_nominal_equals_sum_of_ledger_taxes():
    """lifetime_taxes_nominal is the simple sum of total_tax from every ledger."""
    result = simulate_path(
        _normal_state(), [], _engines(), _normal_settings(), Constraints()
    )

    expected = sum((entry.total_tax for entry in result.ledgers), D("0"))
    assert result.lifetime_taxes_nominal == expected, (
        f"lifetime_taxes_nominal={result.lifetime_taxes_nominal} "
        f"!= sum(ledger.total_tax)={expected}"
    )


# ---------------------------------------------------------------------------
# Test (c): Tiny portfolio vs. large spending → infeasible with depletion_year
# ---------------------------------------------------------------------------


def test_tiny_portfolio_big_spending_is_infeasible():
    """A $1 000 Roth portfolio cannot fund $50 000/yr: feasible=False, depletion_year set."""
    state = State(
        year=2025,
        age_self=65,
        age_spouse=None,
        balance_taxable=D("0"),
        balance_traditional=D("0"),
        balance_roth=D("1000"),
        basis_taxable=D("0"),
        filing_status="single",
        state_code="TX",
    )
    settings = Settings(
        start_year=2025,
        required_spending=D("50000"),
        simulation_years=5,
       
    )
    result = simulate_path(state, [], _engines(), settings, Constraints())

    assert result.feasible is False
    assert result.depletion_year is not None
    assert result.depletion_year == 2025  # fails on the very first simulated year


# ---------------------------------------------------------------------------
# The objective: PV(heir-adjusted estate) less the weighted consumption gap
# ---------------------------------------------------------------------------


def test_path_value_is_pv_estate_less_the_weighted_gap():
    """Taxes are reported, not scored: the estate is already net of them."""
    state = _normal_state()
    settings = _normal_settings()
    res = simulate_path(state, [], _engines(), settings, Constraints())

    n = len(res.ledgers)
    assert res.terminal_estate_pv == res.terminal_estate / (1 + settings.discount_rate) ** n
    assert res.economic_value == res.terminal_estate_pv
    assert res.path_value == (
        res.terminal_estate_pv
        - settings.shortfall_weight * res.shortfall_pv
        - settings.discretionary_shortfall_weight * res.discretionary_shortfall_pv
    )
    assert res.lifetime_taxes_pv > D("0"), "taxes are still reported"


def test_deterministic_and_monte_carlo_objectives_agree_on_one_path():
    """Search and Monte Carlo score a path with the SAME function and weights —
    including guardrail cuts and non-default weights. path_value used to charge
    the discretionary tier at 1.0 while Monte Carlo charged it at 0.5."""
    import dataclasses

    from src.optimization.montecarlo import _objective

    state, _fixed, guard, returns = _guardrail_fixtures()
    odd = dataclasses.replace(guard, shortfall_weight=D("1.7"),
                              discretionary_shortfall_weight=D("0.3"))
    res = simulate_path(state, [], _engines(), odd, Constraints(), returns)
    assert res.discretionary_shortfall_pv > D("0"), "fixture must exercise the cut tier"
    assert res.path_value == _objective(res, odd) == objective_value(res, odd)


def test_infeasible_path_never_outranks_feasible():
    """REGRESSION (run 7d83f4e4, 2026-07-17): under the old taxes-only priority
    a path that depleted early paid less tax and scored ABOVE a fully funded
    one. A household with no money pays no tax and leaves no estate; only the
    shortfall charge separates it from a funded household, and it must rank
    below it."""
    import dataclasses

    engines = _engines()
    rich = _normal_state()
    broke = dataclasses.replace(
        _normal_state(),
        balance_taxable=D("0"), balance_traditional=D("0"),
        balance_roth=D("1000"), basis_taxable=D("0"),
        social_security=D("0"), pension=D("0"),
    )
    settings = _normal_settings()
    ok = simulate_path(rich, [], engines, settings, Constraints())
    lethal = simulate_path(broke, [], engines, settings, Constraints())
    assert ok.feasible and not lethal.feasible, "fixture sanity"
    assert lethal.lifetime_taxes_pv < ok.lifetime_taxes_pv, (
        "fixture sanity: the broke household pays less tax, so a taxes-based "
        "objective would have preferred it"
    )
    assert ok.path_value > lethal.path_value


# ---------------------------------------------------------------------------
# Economic value and the spending shortfall are reported separately
# ---------------------------------------------------------------------------
#
# The infeasibility penalty is the PV of unmet retirement spending — a real
# economic quantity, not an arbitrary constant. But folding it into
# `path_value` before computing statistics meant `std(path_value)` was partly
# measuring the penalty function's shape rather than any economic risk. The two
# are now returned separately so scoring can weight them explicitly.
#
# Step 4 made it a TRUE shortfall. It was called `unfunded_spending_proxy_pv`
# while simulate_year returned None rather than reporting partial funding, so a
# year funding $135k of a $150k need was charged as a complete failure and so
# was every year after it.


def test_feasible_path_has_zero_shortfall():
    result = simulate_path(
        _normal_state(), [], _engines(), _normal_settings(), Constraints()
    )
    assert result.feasible is True
    assert result.shortfall_pv == D("0")
    # With nothing unfunded, the two views coincide.
    assert result.path_value == result.economic_value


def _broke_at_65():
    """$1,000 of assets against $50,000/yr — short from the first year."""
    state = State(
        year=2025, age_self=65, age_spouse=None,
        balance_taxable=D("0"), balance_traditional=D("0"),
        balance_roth=D("1000"), basis_taxable=D("0"),
        filing_status="single", state_code="TX",
    )
    settings = Settings(
        start_year=2025, required_spending=D("50000"),
        simulation_years=5,
    )
    return state, settings


def test_infeasible_path_separates_economics_from_the_penalty():
    """The shortfall must be positive and must NOT be baked into economic_value."""
    state, settings = _broke_at_65()
    result = simulate_path(state, [], _engines(), settings, Constraints())

    assert result.feasible is False
    assert result.shortfall_pv > D("0")
    # economic_value is the estate only — no penalty inside it.
    assert result.economic_value > result.path_value
    # And the identity that defines the search ranking still holds exactly.
    assert result.path_value == (result.economic_value - result.shortfall_pv)


def test_short_years_run_to_the_horizon_and_charge_only_the_gap():
    """Step 4: a path that runs out of money keeps simulating.

    The old proxy stopped at the first bad year and charged every remaining
    year's FULL inflated spending. Now each year funds what it can, so the
    charge is the residual after income — and the ledgers cover the whole
    horizon instead of stopping at depletion.
    """
    state, settings = _broke_at_65()
    result = simulate_path(state, [], _engines(), settings, Constraints())

    # Every year is simulated, not just the ones before the money ran out.
    assert len(result.ledgers) == settings.simulation_years
    assert result.depletion_year == 2025

    # Year 0 spends the $1,000 it has: $49,000 short of $50,000, not $50,000.
    assert result.ledgers[0].shortfall == D("49000")

    # And the total is exactly the discounted sum of the per-year gaps.
    expected = sum(
        (lg.shortfall / (D("1") + settings.discount_rate) ** y
         for y, lg in enumerate(result.ledgers)),
        D("0"),
    )
    assert abs(result.shortfall_pv - expected) < D("0.01")


def test_guaranteed_income_reduces_the_shortfall_net_of_its_own_tax():
    """A broke household with Social Security is charged less than one without.

    This is what makes λ = 1 readable as "a PV dollar of unfunded retirement
    costs one dollar": the charge is measured after income and after the tax on
    that income, because the post-depletion years are really simulated rather
    than extrapolated.
    """
    state, settings = _broke_at_65()
    engines = _engines()

    broke = simulate_path(state, [], engines, settings, Constraints())

    import dataclasses
    with_ss = simulate_path(
        dataclasses.replace(state, social_security=D("30000")),
        [], engines, settings, Constraints(),
    )

    assert not broke.feasible and not with_ss.feasible
    assert with_ss.shortfall_pv < broke.shortfall_pv
    # Net, not gross: some of the $30,000 benefit is taxable, so the shortfall
    # falls by less than the full benefit in the first year.
    relief = broke.ledgers[0].shortfall - with_ss.ledgers[0].shortfall
    assert D("0") < relief <= D("30000")


# ---------------------------------------------------------------------------
# Step 5 — dynamic spending (Guyton-Klinger guardrails, two-tier pricing)
# ---------------------------------------------------------------------------
#
# The whole design turns on one point: a voluntary cut is NOT free. If the
# objective only charged hard shortfalls, guardrails would read as costless
# safety and every plan's score would improve for a reason no retiree would
# call good news. So the consumption gap is charged in both tiers, split at the
# essential floor — by LEVEL, not by cause, because a guardrail cut and a year
# the money ran out are the same loss to the person living it.


def _guardrail_fixtures(**overrides):
    """A household with a rough first decade, fixed vs guardrails."""
    import dataclasses

    state = State(
        year=2025, age_self=65, age_spouse=63,
        balance_taxable=D("300000"), balance_traditional=D("850000"),
        balance_roth=D("50000"), basis_taxable=D("150000"),
        filing_status="joint", state_code="CA",
        social_security=D("40000"),
    )
    fixed = Settings(
        start_year=2025, required_spending=D("120000"),
        simulation_years=25,
    )
    guard = dataclasses.replace(
        fixed, spending_rule="guardrails", spending_floor=D("90000"), **overrides
    )
    # Poor early returns are what make guardrails do anything at all.
    returns = [D("-0.10")] * 8 + [D("0.07")] * 17
    return state, fixed, guard, returns


def test_guardrails_cut_spending_and_the_cut_is_charged():
    state, fixed, guard, returns = _guardrail_fixtures()
    engines, cons = _engines(), Constraints()

    f = simulate_path(state, [], engines, fixed, cons, returns)
    g = simulate_path(state, [], engines, guard, cons, returns)

    # The rule actually fired, and only in the guardrails run.
    assert all(lg.discretionary_cut == D("0") for lg in f.ledgers)
    assert any(lg.discretionary_cut > D("0") for lg in g.ledgers)

    # The cut is charged, not waved through: a discretionary tier appears
    # where the fixed run has none.
    assert f.discretionary_shortfall_pv == D("0")
    assert g.discretionary_shortfall_pv > D("0")

    # Spending it gave up is real, so it survives into the ledger arithmetic.
    for lg in g.ledgers:
        assert lg.discretionary_cut == lg.target_spending - lg.required_spending
        assert lg.discretionary_cut >= D("0")


def test_guardrail_cuts_never_breach_the_essential_floor():
    state, _fixed, guard, returns = _guardrail_fixtures()
    res = simulate_path(state, [], _engines(), guard, Constraints(), returns)

    for y, lg in enumerate(res.ledgers):
        floor_now = D("90000") * (D("1") + guard.inflation) ** y
        # The PLAN never aims below the floor. (What it can actually FUND may
        # still fall short once the portfolio is gone — that is the essential
        # tier, and it is charged at full weight.)
        assert lg.required_spending >= floor_now - D("0.01"), (
            f"{lg.year}: planned {lg.required_spending} below floor {floor_now}"
        )


def test_guardrails_never_spend_above_the_stated_target():
    """Guyton-Klinger's prosperity rule is deliberately truncated.

    The user told us what they need, not what they would enjoy. Letting a bull
    market push spending past the target would make discretionary_cut negative
    — paying the objective a bonus it did not earn.
    """
    state, _fixed, guard, _returns = _guardrail_fixtures()
    boom = [D("0.25")] * 25
    res = simulate_path(state, [], _engines(), guard, Constraints(), boom)
    for lg in res.ledgers:
        assert lg.required_spending <= lg.target_spending + D("0.01")
        assert lg.discretionary_cut >= D("0")


def test_a_voluntary_cut_is_not_free():
    """The trap this design exists to avoid.

    Charging only hard shortfalls would let a plan buy success probability with
    spending cuts at no cost to its score. Compare the same guardrail path
    priced two ways: lambda_d = 0 (cuts free) must score strictly better than
    lambda_d = 0.5, which proves the cut is carrying weight in the objective.
    """
    import dataclasses

    from src.optimization.montecarlo import _objective

    state, _fixed, guard, returns = _guardrail_fixtures()
    res = simulate_path(state, [], _engines(), guard, Constraints(), returns)
    assert res.discretionary_shortfall_pv > D("0"), "fixture sanity"

    free = _objective(res, dataclasses.replace(guard, discretionary_shortfall_weight=D("0")))
    priced = _objective(res, guard)
    full = _objective(res, dataclasses.replace(guard, discretionary_shortfall_weight=D("1")))

    assert free > priced > full, (
        "the discretionary charge must sit strictly between free and full"
    )


def test_no_floor_means_every_gap_is_essential():
    """Backward compatibility: without a floor, pricing is exactly as before.

    A user who has not told us what is negotiable gets the strict reading, not
    a generous one — so the discretionary tier stays empty and the objective
    reduces to the single-tier form Step 4 shipped.
    """
    import dataclasses

    state, fixed, _guard, returns = _guardrail_fixtures()
    no_floor = dataclasses.replace(fixed, spending_floor=None)
    res = simulate_path(state, [], _engines(), no_floor, Constraints(), returns)

    assert res.discretionary_shortfall_pv == D("0")
    assert res.path_value == res.economic_value - res.shortfall_pv


def test_the_gap_is_split_by_level_not_by_cause():
    """A shortfall that leaves you above the floor is discretionary too.

    Being $5k short of a $120k target while still spending $100k against a
    $90k floor is a bad year, not a catastrophe. The split is by dollar level
    because that is what the retiree actually experiences.
    """
    import dataclasses

    state, fixed, _guard, _returns = _guardrail_fixtures()
    # Fixed rule (no voluntary cuts at all) but WITH a floor, so any gap the
    # market causes still gets tiered.
    cfg = dataclasses.replace(fixed, spending_floor=D("90000"))
    crash = [D("-0.35")] * 25
    res = simulate_path(state, [], _engines(), cfg, Constraints(), crash)

    assert all(lg.discretionary_cut == D("0") for lg in res.ledgers), (
        "fixture sanity: the fixed rule must not cut voluntarily"
    )
    # Yet both tiers are populated — purely from involuntary shortfalls.
    assert res.shortfall_pv > D("0")
    assert res.discretionary_shortfall_pv > D("0")


# ---------------------------------------------------------------------------
# A replayed schedule never converts money the year needs for spending
# ---------------------------------------------------------------------------


def _stranding_case():
    """Single, 60, Texas: $50k IRA, nothing else, $20k salary, $30k spending.
    The schedule is sized on 6% a year; replayed after a 20% fall, its third
    conversion takes the IRA dollars that year's spending needed.

    The schedule is the greedy `level_50` rollout, from the benchmark's
    reference copy now that the search no longer builds greedy policies."""
    from benchmarks.greedy_reference import greedy_policies

    state = State(
        year=2026, age_self=60, age_spouse=None,
        balance_taxable=D("0"), basis_taxable=D("0"),
        balance_traditional=D("50000"), balance_roth=D("0"),
        filing_status="single", state_code="TX",
        salary=D("20000"),
    )
    settings = Settings(
        start_year=2026, required_spending=D("30000"), simulation_years=3,
        birth_year_self=1966,
        income_schedule=[IncomeEntry("salary", D("20000"), None, None)],
    )
    policies = {
        p.policy_id: p for p in greedy_policies(state, _engines(), settings, Constraints())
    }
    schedule = list(policies["level_50"].conversions)
    return state, settings, schedule


def test_a_replayed_conversion_is_cut_back_rather_than_strand_spending():
    state, settings, schedule = _stranding_case()
    returns = [D("-0.20"), D("0.06"), D("0.06")]
    engines = _engines()

    result = simulate_path(state, schedule, engines, settings, Constraints(),
                           annual_returns=returns)

    # Rebuild each year's opening state from what was actually executed, and
    # compare every year with converting nothing from that same state.
    import dataclasses

    from src.optimization.transition import simulate_year

    s = state
    for ledger, r in zip(result.ledgers, returns, strict=True):
        year_settings = dataclasses.replace(settings, nominal_return=r)
        _, zero = simulate_year(s, D("0"), engines, year_settings, Constraints())
        assert ledger.shortfall <= zero.shortfall + D("1"), ledger.year
        s, _ = simulate_year(s, ledger.conversion, engines, year_settings, Constraints())
    assert result.feasible
