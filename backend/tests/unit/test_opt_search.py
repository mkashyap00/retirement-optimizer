"""Tests for the rule search over Roth-conversion policies.

TDD RED phase: tests written BEFORE implementation.

Test 1 (economic-sanity): 62yo MFJ, $2.5M traditional, low income, CA.
  Without conversions RMDs at 73 land deep in 24%+ brackets;
  converting in the 12-22% window must beat doing nothing.

Test 2 (no-traditional): zero balance_traditional → only baseline ["none"].
"""

from decimal import Decimal as D

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.search import rule_of, search, thru_year_of
from src.optimization.state import Constraints, Engines, IncomeEntry, Settings, State

_PENSION_SCHEDULE = [IncomeEntry("pension", D("20000"), None, None)]
_PENSION_30K_SCHEDULE = [IncomeEntry("pension", D("30000"), None, None)]


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


def _state():
    """Retired single, age 65, CA — basic mutable fixture."""
    return State(
        year=2025,
        age_self=65,
        age_spouse=None,
        balance_taxable=D("200000"),
        balance_traditional=D("500000"),
        balance_roth=D("100000"),
        basis_taxable=D("150000"),
        filing_status="single",
        state_code="CA",
        pension=D("20000"),
        medicare_self=True,
    )


# ---------------------------------------------------------------------------
# Test 1: Economic sanity — converting beats doing nothing before RMDs spike
# ---------------------------------------------------------------------------


def test_conversion_beats_none_when_rmds_would_spike_brackets():
    # 62-year-old MFJ couple, $2.5M traditional, low current income, CA.
    # Without conversions RMDs at 73 land deep in the 24%+ brackets;
    # converting in the 12-22% window must beat doing nothing.
    s = State(
        year=2025,
        age_self=62,
        age_spouse=62,
        balance_taxable=D("400000"),
        basis_taxable=D("300000"),
        balance_traditional=D("2500000"),
        balance_roth=D("50000"),
        filing_status="joint",
        state_code="CA",
        pension=D("30000"),
    )
    policies = search(
        s,
        _engines(),
        Settings(
            start_year=2025,
            required_spending=D("90000"),
            income_schedule=_PENSION_30K_SCHEDULE,
        ),
        Constraints(),
    )
    assert policies[0].policy_id != "none"
    assert policies[0].result.path_value > next(
        p for p in policies if p.policy_id == "none"
    ).result.path_value


# ---------------------------------------------------------------------------
# Test 2: No traditional balance → only the "none" baseline is returned
# ---------------------------------------------------------------------------


def test_no_traditional_balance_yields_baseline_only():
    s = _state()
    s.balance_traditional = D("0")
    policies = search(
        s,
        _engines(),
        Settings(start_year=2025, required_spending=D("60000"), income_schedule=_PENSION_SCHEDULE),
        Constraints(),
    )
    # No traditional balance → no rule policies (every rule builder yields an
    # all-zero schedule, skipped).
    assert [p.policy_id for p in policies] == ["none"]


# ---------------------------------------------------------------------------
# The "none" baseline must never convert
# ---------------------------------------------------------------------------


def test_none_policy_never_converts():
    """REGRESSION (run 76ee6420, 2026-08-21): "none" was the year-0 ACTION fed
    into the (since removed) greedy rollout, so the resulting policy converted in years 1+ —
    a plan the UI labelled "No conversions" while the year table showed
    $179k of them.  Worse, run_optimization uses this policy as the
    counterfactual baseline for BETR, marginal-cost rate, and
    projected_future_marginal_rate, so a converting "baseline" corrupted all
    three.  The "none" policy must be an all-zero schedule.
    """
    s = _state()
    s.balance_traditional = D("1500000")  # ample room to tempt the rollout
    policies = search(
        s,
        _engines(),
        Settings(start_year=2025, required_spending=D("60000"), income_schedule=_PENSION_SCHEDULE),
        Constraints(),
    )
    none_policy = next(p for p in policies if p.policy_id == "none")
    assert sum(none_policy.conversions, D("0")) == D("0"), (
        f'"none" must never convert, got {none_policy.conversions}'
    )
    # Every ledger in the baseline path must also be conversion-free.
    assert all(lg.conversion == D("0") for lg in none_policy.result.ledgers)


# ---------------------------------------------------------------------------
# Consistent-rule (full-horizon "fill R every year") policies
# ---------------------------------------------------------------------------


def test_consistent_rule_policies_are_generated():
    """With a traditional balance and bracket room, the search offers at least
    one interpretable `<rule>_annual` policy."""
    policies = search(
        _state(),
        _engines(),
        Settings(start_year=2025, required_spending=D("60000"), income_schedule=_PENSION_SCHEDULE),
        Constraints(),
    )
    ids = [p.policy_id for p in policies]
    assert any(pid.endswith("_annual") for pid in ids), ids


def test_annual_rule_converts_across_the_full_horizon():
    """A consistent-rule policy converts across the full horizon — it has
    non-zero conversions past year 5, the old greedy lookahead cap."""
    s = _state()
    s.balance_traditional = D("1500000")  # large enough to convert for many years
    policies = search(
        s,
        _engines(),
        Settings(start_year=2025, required_spending=D("60000"), income_schedule=_PENSION_SCHEDULE),
        Constraints(),
    )
    # fill_22_annual, not "the first _annual": from 2029 this household's
    # taxable account is empty and its IRA spending withdrawal plus pension
    # already fill the 12% bracket, so fill_12_annual correctly stops after
    # year 4. It used to keep converting into 22% because bracket room
    # ignored that withdrawal.
    annual = next(p for p in policies if p.policy_id == "fill_22_annual")
    assert any(amt > D("0") for amt in annual.conversions[5:]), annual.conversions

    # Every policy is a named rule or the baseline.
    assert all(rule_of(p.policy_id) or p.policy_id == "none" for p in policies)


def test_marginal_rate_limit_caps_annual_rule():
    """A 12% marginal-rate ceiling removes the 22%/24% fill-every-year policies
    (they would cross the ceiling), proving the constraint composes with the
    consistent-rule builder — a sensitivity guard on the exposed knob."""
    s = _state()
    s.balance_traditional = D("1500000")
    engines = _engines()
    settings = Settings(
        start_year=2025, required_spending=D("60000"), income_schedule=_PENSION_SCHEDULE
    )

    uncapped = [p.policy_id for p in search(s, engines, settings, Constraints())]
    capped = [
        p.policy_id
        for p in search(s, engines, settings, Constraints(marginal_rate_limit=D("0.12")))
    ]

    assert "fill_22_annual" in uncapped, uncapped
    assert "fill_22_annual" not in capped, capped
    assert "fill_24_annual" not in capped, capped


# ---------------------------------------------------------------------------
# Annual rules keep their own amount when a cap makes two rules coincide
# ---------------------------------------------------------------------------


def test_a_capped_annual_rule_converts_the_cap_every_year():
    """Under a $5,000 cap fill_10 and fill_22 both size to $5,000. The year's
    candidate list kept only the first id for that amount, so the fill_22
    builder found no entry of its own and converted nothing at all."""
    from src.optimization.search import _build_rule_schedule

    s = State(
        year=2025, age_self=62, age_spouse=62,
        balance_taxable=D("400000"), basis_taxable=D("400000"),
        balance_traditional=D("1000000"), balance_roth=D("0"),
        filing_status="joint", state_code="TX",
    )
    settings = Settings(start_year=2025, required_spending=D("40000"),
                        simulation_years=3)
    capped = Constraints(max_conversion_per_year=D("5000"))

    schedule, feasible = _build_rule_schedule(s, "fill_22", _engines(), settings, capped)

    assert feasible
    assert schedule == [D("5000")] * 3


# ---------------------------------------------------------------------------
# Limited-duration rules ("<rule>_thru_<YYYY>")
# ---------------------------------------------------------------------------


def _big_ira_policies():
    s = _state()
    s.balance_traditional = D("1500000")
    settings = Settings(
        start_year=2025, required_spending=D("60000"), income_schedule=_PENSION_SCHEDULE
    )
    return search(s, _engines(), settings, Constraints())


def test_rule_of_parses_every_family():
    assert rule_of("fill_22_annual") == "fill_22"
    assert rule_of("fill_22_thru_2031") == "fill_22"
    assert thru_year_of("fill_22_thru_2031") == 2031
    assert thru_year_of("fill_22_annual") is None
    for pid in ("none", "defer_1yr", "fill_22", "level_50", "max_pre_rmd"):
        assert rule_of(pid) is None, pid


def test_duration_variants_are_prefixes_of_their_annual_rule():
    """`fill_22_thru_2028` converts exactly what fill_22_annual converts in
    2025-2028 and nothing afterwards."""
    policies = _big_ira_policies()
    by_id = {p.policy_id: p for p in policies}
    variants = [p for p in policies if thru_year_of(p.policy_id) is not None]
    assert variants, sorted(by_id)
    for v in variants:
        annual = by_id.get(f"{rule_of(v.policy_id)}_annual")
        n = thru_year_of(v.policy_id) - 2025 + 1
        assert v.conversions[n - 1] > D("0"), v.policy_id
        assert all(a == D("0") for a in v.conversions[n:]), v.policy_id
        if annual is not None:
            assert v.conversions[:n] == annual.conversions[:n], v.policy_id
            assert annual.conversions[n:] != v.conversions[n:], v.policy_id


def test_duration_variants_are_deduplicated():
    """Every schedule appears once: a variant equal to an `_annual` rule (or to
    another variant) keeps the first name it was registered under."""
    from src.optimization.search import _dedup_key

    keys = [_dedup_key(list(p.conversions)) for p in _big_ira_policies()]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Level-dollar rules ("level_<N>pct_annual" / "_thru_<YYYY>")
# ---------------------------------------------------------------------------


def test_level_rule_converts_one_fixed_amount_sized_from_the_start_balance():
    """level_5pct converts 5% of the STARTING IRA every year it is allowed --
    the same dollars each year, not 5% of a shrinking balance."""
    by_id = {p.policy_id: p for p in _big_ira_policies()}
    assert rule_of("level_5pct_thru_2027") == "level_5pct"
    level = by_id["level_5pct_annual"]
    amount = D("0.05") * D("1500000")
    assert level.conversions[0] == amount
    assert level.conversions[1] == amount
    assert all(c <= amount for c in level.conversions)
    assert any(thru_year_of(pid) for pid in by_id if pid.startswith("level_5pct")), sorted(by_id)


def test_level_amount_is_a_requested_maximum():
    """The year's cap still applies: under a $5,000 cap level_20pct converts
    $5,000, not 20% of the IRA."""
    from src.optimization.search import _build_rule_schedule

    s = State(
        year=2025, age_self=62, age_spouse=62,
        balance_taxable=D("400000"), basis_taxable=D("400000"),
        balance_traditional=D("1000000"), balance_roth=D("0"),
        filing_status="joint", state_code="TX",
    )
    settings = Settings(start_year=2025, required_spending=D("40000"), simulation_years=3)
    schedule, feasible = _build_rule_schedule(
        s, "level_20pct", _engines(), settings,
        Constraints(max_conversion_per_year=D("5000")),
        requested={"level_20pct": D("200000")},
    )
    assert feasible
    assert schedule == [D("5000")] * 3
