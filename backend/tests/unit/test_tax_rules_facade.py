"""Tests for TaxRules facade — TDD RED phase first, then GREEN."""
import logging
from decimal import Decimal

import pytest
from src.data.tax_rules.rules import TaxRules
from src.data.tax_rules.types import IrmaaYear


@pytest.fixture
def rules() -> TaxRules:
    return TaxRules()


# ---------------------------------------------------------------------------
# federal()
# ---------------------------------------------------------------------------

class TestFederalLookup:
    def test_known_year_returns_correct_year(self, rules: TaxRules) -> None:
        assert rules.federal(2025).year == 2025

    def test_known_year_2026(self, rules: TaxRules) -> None:
        assert rules.federal(2026).year == 2026

    def test_future_year_clamps_to_latest(self, rules: TaxRules) -> None:
        latest = rules.latest_federal_year()
        assert rules.federal(2099).year == latest

    def test_future_year_logs_warning(self, rules: TaxRules, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            rules.federal(2099)
        assert any("2099" in r.message for r in caplog.records)

    def test_future_year_only_warns_once(self, rules: TaxRules, caplog) -> None:
        """Same unknown year should only produce one warning total."""
        with caplog.at_level(logging.WARNING):
            rules.federal(2050)
            rules.federal(2050)
        warnings = [r for r in caplog.records if "2050" in r.message]
        assert len(warnings) == 1

    def test_latest_federal_year_is_int(self, rules: TaxRules) -> None:
        assert isinstance(rules.latest_federal_year(), int)

    def test_latest_federal_year_value(self, rules: TaxRules) -> None:
        assert rules.latest_federal_year() >= 2026


# ---------------------------------------------------------------------------
# irmaa()
# ---------------------------------------------------------------------------

class TestIrmaaLookup:
    def test_known_year(self, rules: TaxRules) -> None:
        iy = rules.irmaa(2025)
        assert isinstance(iy, IrmaaYear)
        assert iy.year == 2025

    def test_known_year_2026(self, rules: TaxRules) -> None:
        assert rules.irmaa(2026).year == 2026

    def test_future_year_clamps(self, rules: TaxRules) -> None:
        latest_irmaa = max(rules._irmaa_data.keys())  # noqa: SLF001
        assert rules.irmaa(2099).year == latest_irmaa

    def test_future_year_logs_warning(self, rules: TaxRules, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            rules.irmaa(2099)
        assert any("2099" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# state_brackets() and state_standard_deduction()
# ---------------------------------------------------------------------------

class TestStateDelegation:
    def test_state_brackets_no_tax_state(self, rules: TaxRules) -> None:
        assert rules.state_brackets("TX", "single") == []

    def test_state_brackets_returns_list(self, rules: TaxRules) -> None:
        brackets = rules.state_brackets("CA", "single")
        assert isinstance(brackets, list)
        assert len(brackets) > 0

    def test_state_standard_deduction_no_tax_state(self, rules: TaxRules) -> None:
        assert rules.state_standard_deduction("TX", "single") == Decimal("0")

    def test_state_standard_deduction_returns_decimal(self, rules: TaxRules) -> None:
        result = rules.state_standard_deduction("CA", "single")
        assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# rmd_factor()
# ---------------------------------------------------------------------------

class TestRmdFactor:
    def test_below_rmd_start_age_returns_zero(self, rules: TaxRules) -> None:
        assert rules.rmd_factor(72) == Decimal("0")

    def test_age_zero_returns_zero(self, rules: TaxRules) -> None:
        assert rules.rmd_factor(0) == Decimal("0")

    def test_rmd_start_age(self, rules: TaxRules) -> None:
        assert rules.rmd_factor(73) == Decimal("26.5")

    def test_age_74(self, rules: TaxRules) -> None:
        assert rules.rmd_factor(74) == Decimal("25.5")

    def test_age_120(self, rules: TaxRules) -> None:
        assert rules.rmd_factor(120) == Decimal("2.0")

    def test_age_above_120_clamps_to_120(self, rules: TaxRules) -> None:
        """Ages beyond table max use age 120's factor."""
        assert rules.rmd_factor(121) == rules.rmd_factor(120)

    def test_age_150_clamps_to_120(self, rules: TaxRules) -> None:
        assert rules.rmd_factor(150) == Decimal("2.0")


class TestStateYearClamping:
    def test_unknown_state_year_warns_once(self, rules: TaxRules, caplog) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            rules.state_brackets("CA", "single", year=2031)
            rules.state_brackets("CA", "single", year=2031)  # same year again
        msgs = [r.message for r in caplog.records if "State tax data" in r.message]
        assert len(msgs) == 1, msgs
        assert "2031" in msgs[0]

    def test_known_state_year_no_warning(self, rules: TaxRules, caplog) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            rules.state_brackets("CA", "single", year=2025)
        assert not [r for r in caplog.records if "State tax data" in r.message]
