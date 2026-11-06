"""Tests for RMD calculator engine."""
from decimal import Decimal as D

from src.data.tax_rules.rules import TaxRules
from src.engines.rmd import RMDCalculator


def test_no_rmd_before_73():
    """Test that no RMD is calculated before age 73 (B6 regression)."""
    calc = RMDCalculator(TaxRules())
    assert calc.calculate(D("1000000"), 72) == D("0")


def test_rmd_at_73():
    """Test RMD calculation at age 73 (factor 26.5)."""
    calc = RMDCalculator(TaxRules())
    # 500,000 / 26.5 = 18,867.92
    assert calc.calculate(D("500000"), 73) == D("18867.92")


def test_rmd_caps_at_120_factor():
    """Test that RMD calculation caps at age 120 factor (2.0)."""
    calc = RMDCalculator(TaxRules())
    # 100,000 / 2.0 = 50,000.00
    assert calc.calculate(D("100000"), 125) == D("50000.00")


# ---------------------------------------------------------------------------
# SECURE 2.0 applicable age (§107)
# ---------------------------------------------------------------------------
#
# REGRESSION (verified 2026-08-23 against IRS Pub 590-B p.67 + SECURE 2.0 §107):
# RMD_START_AGE was a flat 73, and rmd_factor() never received a birth year, so
# it could not apply the statutory "applicable age". Anyone born 1960 or later
# — most of the pre-RMD conversion-planning audience — was charged RMDs two
# years early. That understates the no-conversion baseline and inflates
# projected_future_marginal_rate, biasing the tool toward converting.


def test_applicable_age_by_birth_cohort():
    """SECURE 2.0 §107: 73 for those attaining 72 after 2022, 75 for those
    attaining 74 after 2032. The 1959 drafting ambiguity was resolved to 73 by
    the IRS proposed regs (REG-103529-23, July 2024)."""
    from src.data.tax_rules.rmd import applicable_rmd_age

    assert applicable_rmd_age(1950) == 72
    assert applicable_rmd_age(1951) == 73
    assert applicable_rmd_age(1955) == 73
    assert applicable_rmd_age(1959) == 73  # resolved ambiguity — not 75
    assert applicable_rmd_age(1960) == 75  # first cohort at 75
    assert applicable_rmd_age(1964) == 75
    assert applicable_rmd_age(1980) == 75


def test_born_1960_or_later_has_no_rmd_at_73_or_74():
    calc = RMDCalculator(TaxRules())
    assert calc.calculate(D("1000000"), 73, birth_year=1964) == D("0")
    assert calc.calculate(D("1000000"), 74, birth_year=1964) == D("0")
    # First RMD lands at 75 (factor 24.6)
    assert calc.calculate(D("1000000"), 75, birth_year=1964) == D("40650.41")


def test_born_before_1960_still_starts_at_73():
    """Guard the other direction — the older cohort must not be pushed to 75."""
    calc = RMDCalculator(TaxRules())
    assert calc.calculate(D("500000"), 73, birth_year=1955) == D("18867.92")


def test_birth_year_omitted_preserves_legacy_age_73():
    """Callers that do not supply a birth year keep the pre-existing behavior."""
    calc = RMDCalculator(TaxRules())
    assert calc.calculate(D("500000"), 73) == D("18867.92")
