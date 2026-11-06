"""Tests for income schedule (start/end year) support.

Validates that:
  - resolve_income correctly sums by category within year bounds
  - simulate_year picks up per-year income from the schedule (not carry-forward)
  - salary that ends in 2028 produces zero salary in 2029+
"""

from decimal import Decimal as D

from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.state import (
    Constraints,
    Engines,
    IncomeEntry,
    Settings,
    State,
    resolve_income,
)
from src.optimization.transition import simulate_year

# ---------------------------------------------------------------------------
# resolve_income unit tests
# ---------------------------------------------------------------------------

class TestResolveIncome:
    def test_active_within_range(self):
        schedule = [IncomeEntry("salary", D("100000"), 2026, 2028)]
        assert resolve_income(schedule, 2026)["salary"] == D("100000")
        assert resolve_income(schedule, 2027)["salary"] == D("100000")
        assert resolve_income(schedule, 2028)["salary"] == D("100000")

    def test_inactive_before_start(self):
        schedule = [IncomeEntry("salary", D("100000"), 2027, 2030)]
        assert resolve_income(schedule, 2026)["salary"] == D("0")

    def test_inactive_after_end(self):
        schedule = [IncomeEntry("salary", D("100000"), 2026, 2028)]
        assert resolve_income(schedule, 2029)["salary"] == D("0")
        assert resolve_income(schedule, 2050)["salary"] == D("0")

    def test_no_bounds_always_active(self):
        schedule = [IncomeEntry("pension", D("30000"), None, None)]
        assert resolve_income(schedule, 2020)["pension"] == D("30000")
        assert resolve_income(schedule, 2050)["pension"] == D("30000")

    def test_start_only(self):
        schedule = [IncomeEntry("rental", D("12000"), 2030, None)]
        assert resolve_income(schedule, 2029)["rental"] == D("0")
        assert resolve_income(schedule, 2030)["rental"] == D("12000")
        assert resolve_income(schedule, 2060)["rental"] == D("12000")

    def test_end_only(self):
        schedule = [IncomeEntry("salary", D("80000"), None, 2028)]
        assert resolve_income(schedule, 2026)["salary"] == D("80000")
        assert resolve_income(schedule, 2028)["salary"] == D("80000")
        assert resolve_income(schedule, 2029)["salary"] == D("0")

    def test_multiple_sources_same_category(self):
        schedule = [
            IncomeEntry("salary", D("100000"), 2026, 2028),
            IncomeEntry("salary", D("50000"), 2026, 2027),
        ]
        assert resolve_income(schedule, 2026)["salary"] == D("150000")
        assert resolve_income(schedule, 2027)["salary"] == D("150000")
        assert resolve_income(schedule, 2028)["salary"] == D("100000")
        assert resolve_income(schedule, 2029)["salary"] == D("0")

    def test_dividend_category_mapping(self):
        schedule = [
            IncomeEntry("qualified_dividend", D("2000"), 2026, 2050),
            IncomeEntry("nonqualified_dividend", D("10000"), 2026, 2050),
        ]
        result = resolve_income(schedule, 2030)
        assert result["dividends_qualified"] == D("2000")
        assert result["dividends_ordinary"] == D("10000")

    def test_interest_category(self):
        schedule = [IncomeEntry("interest", D("5000"), 2026, 2035)]
        assert resolve_income(schedule, 2030)["interest"] == D("5000")
        assert resolve_income(schedule, 2036)["interest"] == D("0")

    def test_empty_schedule(self):
        result = resolve_income([], 2026)
        assert all(v == D("0") for v in result.values())

    def test_all_categories_together(self):
        schedule = [
            IncomeEntry("salary", D("100000"), 2026, 2028),
            IncomeEntry("pension", D("30000"), 2030, None),
            IncomeEntry("rental", D("12000"), None, None),
            IncomeEntry("interest", D("5000"), 2026, 2040),
            IncomeEntry("qualified_dividend", D("2000"), 2026, 2050),
            IncomeEntry("nonqualified_dividend", D("8000"), 2026, 2050),
        ]
        y2027 = resolve_income(schedule, 2027)
        assert y2027["salary"] == D("100000")
        assert y2027["pension"] == D("0")
        assert y2027["rental"] == D("12000")
        assert y2027["interest"] == D("5000")

        y2031 = resolve_income(schedule, 2031)
        assert y2031["salary"] == D("0")
        assert y2031["pension"] == D("30000")
        assert y2031["rental"] == D("12000")


# ---------------------------------------------------------------------------
# Integration: simulate_year respects income schedule
# ---------------------------------------------------------------------------

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


def test_salary_ends_after_specified_year():
    """Salary ending in 2027 must produce zero salary in the 2028 state."""
    schedule = [
        IncomeEntry("salary", D("100000"), 2026, 2027),
        IncomeEntry("nonqualified_dividend", D("10000"), 2026, 2050),
    ]
    state = State(
        year=2027,
        age_self=63,
        age_spouse=None,
        balance_taxable=D("500000"),
        balance_traditional=D("500000"),
        balance_roth=D("200000"),
        basis_taxable=D("300000"),
        filing_status="single",
        state_code="CA",
        salary=D("100000"),
        dividends_ordinary=D("10000"),
    )
    settings = Settings(
        start_year=2026,
        required_spending=D("80000"),
        income_schedule=schedule,
    )
    next_state, ledger = simulate_year(
        state, D("0"), _engines(), settings, Constraints()
    )
    assert next_state.salary == D("0"), (
        f"Salary should be 0 after end_year 2027, got {next_state.salary}"
    )
    assert next_state.dividends_ordinary == D("10000")


def test_salary_active_before_end_year():
    """Salary ending in 2028 must still be active in the 2027→2028 transition."""
    schedule = [IncomeEntry("salary", D("100000"), 2026, 2028)]
    state = State(
        year=2027,
        age_self=63,
        age_spouse=None,
        balance_taxable=D("500000"),
        balance_traditional=D("500000"),
        balance_roth=D("200000"),
        basis_taxable=D("300000"),
        filing_status="single",
        state_code="CA",
        salary=D("100000"),
    )
    settings = Settings(
        start_year=2026,
        required_spending=D("80000"),
        income_schedule=schedule,
    )
    next_state, _ = simulate_year(
        state, D("0"), _engines(), settings, Constraints()
    )
    assert next_state.salary == D("100000")


def test_interest_income_flows_through():
    """Interest income from the schedule must appear in the next state."""
    schedule = [IncomeEntry("interest", D("5000"), 2026, 2030)]
    state = State(
        year=2026,
        age_self=63,
        age_spouse=None,
        balance_taxable=D("500000"),
        balance_traditional=D("500000"),
        balance_roth=D("200000"),
        basis_taxable=D("300000"),
        filing_status="single",
        state_code="CA",
        interest=D("5000"),
    )
    settings = Settings(
        start_year=2026,
        required_spending=D("80000"),
        income_schedule=schedule,
    )
    next_state, _ = simulate_year(
        state, D("0"), _engines(), settings, Constraints()
    )
    assert next_state.interest == D("5000")

    # Now simulate year 2030 → 2031 (interest should stop)
    state_2030 = State(
        year=2030,
        age_self=67,
        age_spouse=None,
        balance_taxable=D("500000"),
        balance_traditional=D("500000"),
        balance_roth=D("200000"),
        basis_taxable=D("300000"),
        filing_status="single",
        state_code="CA",
        interest=D("5000"),
    )
    next_state_2031, _ = simulate_year(
        state_2030, D("0"), _engines(), settings, Constraints()
    )
    assert next_state_2031.interest == D("0"), (
        f"Interest should be 0 after end_year 2030, got {next_state_2031.interest}"
    )
