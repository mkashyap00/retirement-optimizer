from decimal import Decimal

from src.data.tax_rules.rmd import RMD_START_AGE, UNIFORM_LIFETIME


def test_start_age_and_key_factors():
    assert RMD_START_AGE == 73
    assert UNIFORM_LIFETIME[73] == Decimal("26.5")
    assert UNIFORM_LIFETIME[75] == Decimal("24.6")
    assert UNIFORM_LIFETIME[120] == Decimal("2.0")


def test_factors_strictly_decrease():
    ages = sorted(UNIFORM_LIFETIME)
    pairs = zip(ages, ages[1:], strict=False)
    assert all(UNIFORM_LIFETIME[a] > UNIFORM_LIFETIME[b] for a, b in pairs)
