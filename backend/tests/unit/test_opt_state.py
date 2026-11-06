"""Test optimizer state/action/ledger dataclasses."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest
from src.data.tax_rules.rules import TaxRules
from src.engines.irmaa import IRMAACalculator
from src.engines.rmd import RMDCalculator
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.federal import FederalTaxEngine
from src.engines.tax.state import StateTaxEngine
from src.optimization.state import (
    Action,
    Constraints,
    Engines,
    Settings,
    State,
    YearLedger,
)


class TestState:
    """Test State dataclass (mutable)."""

    def test_state_construction_minimal(self):
        """Construct State with minimal required args."""
        state = State(
            year=2025,
            age_self=65,
            age_spouse=None,
            balance_taxable=Decimal("100000"),
            balance_traditional=Decimal("500000"),
            balance_roth=Decimal("200000"),
            basis_taxable=Decimal("50000"),
            filing_status="single",
            state_code="CA",
        )
        assert state.year == 2025
        assert state.age_self == 65
        assert state.age_spouse is None
        assert state.balance_taxable == Decimal("100000")
        assert state.filing_status == "single"

    def test_state_defaults(self):
        """Test State default values."""
        state = State(
            year=2025,
            age_self=65,
            age_spouse=None,
            balance_taxable=Decimal("100000"),
            balance_traditional=Decimal("500000"),
            balance_roth=Decimal("200000"),
            basis_taxable=Decimal("50000"),
            filing_status="single",
            state_code="CA",
        )
        assert state.basis_traditional == Decimal("0")
        assert state.salary == Decimal("0")
        assert state.pension == Decimal("0")
        assert state.medicare_self is False
        assert state.medicare_spouse is False

    def test_state_is_mutable(self):
        """State should be mutable (plain dataclass)."""
        state = State(
            year=2025,
            age_self=65,
            age_spouse=None,
            balance_taxable=Decimal("100000"),
            balance_traditional=Decimal("500000"),
            balance_roth=Decimal("200000"),
            basis_taxable=Decimal("50000"),
            filing_status="single",
            state_code="CA",
        )
        # Should be able to modify fields
        state.year = 2026
        state.balance_taxable = Decimal("150000")
        assert state.year == 2026
        assert state.balance_taxable == Decimal("150000")


class TestAction:
    """Test Action dataclass (frozen)."""

    def test_action_construction_minimal(self):
        """Construct Action with minimal required args."""
        action = Action(conversion=Decimal("50000"))
        assert action.conversion == Decimal("50000")
        assert action.withdrawal_taxable == Decimal("0")
        assert action.action_id == "none"

    def test_action_construction_full(self):
        """Construct Action with all args."""
        action = Action(
            conversion=Decimal("50000"),
            withdrawal_taxable=Decimal("10000"),
            withdrawal_traditional=Decimal("5000"),
            withdrawal_roth=Decimal("2000"),
            action_id="fill_12",
        )
        assert action.conversion == Decimal("50000")
        assert action.withdrawal_taxable == Decimal("10000")
        assert action.withdrawal_traditional == Decimal("5000")
        assert action.withdrawal_roth == Decimal("2000")
        assert action.action_id == "fill_12"

    def test_action_is_frozen(self):
        """Action should be frozen (immutable)."""
        action = Action(conversion=Decimal("50000"))
        with pytest.raises(FrozenInstanceError):
            action.conversion = Decimal("60000")

    def test_action_frozen_prevents_all_mutations(self):
        """Frozen Action prevents any field modification."""
        action = Action(conversion=Decimal("50000"), withdrawal_taxable=Decimal("0"))
        with pytest.raises(FrozenInstanceError):
            action.action_id = "fill_22"


class TestYearLedger:
    """Test YearLedger dataclass (frozen)."""

    def test_year_ledger_construction(self):
        """Construct YearLedger with all required args."""
        ledger = YearLedger(
            year=2025,
            age_self=65,
            age_spouse=63,
            rmd=Decimal("18000"),
            conversion=Decimal("50000"),
            withdrawal_taxable=Decimal("10000"),
            withdrawal_traditional=Decimal("5000"),
            withdrawal_roth=Decimal("2000"),
            realized_gains=Decimal("15000"),
            agi=Decimal("150000"),
            magi=Decimal("155000"),
            federal_tax=Decimal("25000"),
            state_tax=Decimal("3000"),
            irmaa=Decimal("500"),
            total_tax=Decimal("28500"),
            net_spendable=Decimal("75000"),
            required_spending=Decimal("80000"),
            shortfall=Decimal("5000"),
            marginal_rate=Decimal("0.24"),
            end_taxable=Decimal("80000"),
            end_traditional=Decimal("450000"),
            end_roth=Decimal("200000"),
        )
        assert ledger.year == 2025
        assert ledger.age_self == 65
        assert ledger.rmd == Decimal("18000")
        assert ledger.total_tax == Decimal("28500")

    def test_year_ledger_is_frozen(self):
        """YearLedger should be frozen (immutable)."""
        ledger = YearLedger(
            year=2025,
            age_self=65,
            age_spouse=None,
            rmd=Decimal("18000"),
            conversion=Decimal("50000"),
            withdrawal_taxable=Decimal("10000"),
            withdrawal_traditional=Decimal("5000"),
            withdrawal_roth=Decimal("2000"),
            realized_gains=Decimal("15000"),
            agi=Decimal("150000"),
            magi=Decimal("155000"),
            federal_tax=Decimal("25000"),
            state_tax=Decimal("3000"),
            irmaa=Decimal("500"),
            total_tax=Decimal("28500"),
            net_spendable=Decimal("75000"),
            required_spending=Decimal("80000"),
            shortfall=Decimal("5000"),
            marginal_rate=Decimal("0.24"),
            end_taxable=Decimal("80000"),
            end_traditional=Decimal("450000"),
            end_roth=Decimal("200000"),
        )
        with pytest.raises(FrozenInstanceError):
            ledger.year = 2026


class TestSettings:
    """Test Settings dataclass (frozen)."""

    def test_settings_construction_minimal(self):
        """Construct Settings with minimal required args."""
        settings = Settings(
            start_year=2025,
            required_spending=Decimal("80000"),
        )
        assert settings.start_year == 2025
        assert settings.required_spending == Decimal("80000")

    def test_settings_defaults(self):
        """Test Settings default values."""
        settings = Settings(
            start_year=2025,
            required_spending=Decimal("80000"),
        )
        assert settings.inflation == Decimal("0.03")
        assert settings.nominal_return == Decimal("0.06")
        assert settings.discount_rate == Decimal("0.02")
        assert settings.simulation_years == 30
        assert settings.heir_tax_rate == Decimal("0.25")
        assert settings.dividend_yield == Decimal("0.02")

    def test_settings_inflation_default_is_003(self):
        """Ensure inflation default is exactly 0.03."""
        settings = Settings(
            start_year=2025,
            required_spending=Decimal("80000"),
        )
        assert settings.inflation == Decimal("0.03")

    def test_settings_custom_values(self):
        """Construct Settings with custom values."""
        settings = Settings(
            start_year=2025,
            required_spending=Decimal("80000"),
            inflation=Decimal("0.04"),
            nominal_return=Decimal("0.07"),
            simulation_years=40,
        )
        assert settings.inflation == Decimal("0.04")
        assert settings.nominal_return == Decimal("0.07")
        assert settings.simulation_years == 40

    def test_settings_is_frozen(self):
        """Settings should be frozen (immutable)."""
        settings = Settings(
            start_year=2025,
            required_spending=Decimal("80000"),
        )
        with pytest.raises(FrozenInstanceError):
            settings.inflation = Decimal("0.04")


class TestConstraints:
    """Test Constraints dataclass (frozen)."""

    def test_constraints_construction_minimal(self):
        """Construct Constraints with all defaults."""
        constraints = Constraints()
        assert constraints.irmaa_policy == "soft"
        assert constraints.conversion_window == "anytime"
        assert constraints.marginal_rate_limit is None
        assert constraints.min_conversion == Decimal("1000")
        assert constraints.max_conversion_per_year is None
        assert constraints.target_estate is None
        assert constraints.preserve_taxable is False

    def test_constraints_custom_values(self):
        """Construct Constraints with custom values."""
        constraints = Constraints(
            irmaa_policy="strict",
            conversion_window="pre_medicare",
            marginal_rate_limit=Decimal("0.32"),
            min_conversion=Decimal("5000"),
            preserve_taxable=True,
        )
        assert constraints.irmaa_policy == "strict"
        assert constraints.conversion_window == "pre_medicare"
        assert constraints.marginal_rate_limit == Decimal("0.32")
        assert constraints.min_conversion == Decimal("5000")
        assert constraints.preserve_taxable is True

    def test_constraints_is_frozen(self):
        """Constraints should be frozen (immutable)."""
        constraints = Constraints()
        with pytest.raises(FrozenInstanceError):
            constraints.irmaa_policy = "avoid"


class TestEngines:
    """Test Engines dataclass (frozen)."""

    def test_engines_construction(self):
        """Construct Engines with engine instances."""
        rules = TaxRules()
        federal_engine = FederalTaxEngine(rules)
        state_engine = StateTaxEngine(rules)
        irmaa_calc = IRMAACalculator(rules)
        rmd_calc = RMDCalculator(rules)
        ss_calc = SocialSecurityCalculator()

        engines = Engines(
            federal=federal_engine,
            state=state_engine,
            irmaa=irmaa_calc,
            rmd=rmd_calc,
            ss=ss_calc,
            rules=rules,
        )
        assert engines.federal is federal_engine
        assert engines.state is state_engine
        assert engines.irmaa is irmaa_calc
        assert engines.rmd is rmd_calc
        assert engines.ss is ss_calc
        assert engines.rules is rules

    def test_engines_is_frozen(self):
        """Engines should be frozen (immutable)."""
        rules = TaxRules()
        federal_engine = FederalTaxEngine(rules)
        state_engine = StateTaxEngine(rules)
        irmaa_calc = IRMAACalculator(rules)
        rmd_calc = RMDCalculator(rules)
        ss_calc = SocialSecurityCalculator()

        engines = Engines(
            federal=federal_engine,
            state=state_engine,
            irmaa=irmaa_calc,
            rmd=rmd_calc,
            ss=ss_calc,
            rules=rules,
        )
        with pytest.raises(FrozenInstanceError):
            engines.federal = None
