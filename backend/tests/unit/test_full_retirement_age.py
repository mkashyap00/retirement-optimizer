"""Full retirement age by birth year, and the benefits that depend on it.

Every benefit used to assume FRA 67. That is right only for those born 1960 or
later; the 1955-1959 cohorts reach FRA at 66 plus 2 to 10 months (SSA), and
survivor benefits follow a separate table two years later.
"""
from decimal import Decimal as D

import pytest
from src.data.tax_rules.social_security import (
    full_retirement_age,
    survivor_full_retirement_age,
)
from src.engines.social_security import SocialSecurityCalculator
from src.optimization.state import Settings
from src.optimization.transition import _annual_social_security

_SS = SocialSecurityCalculator()


def _ym(y, m):
    return D(y) + D(m) / D(12)


@pytest.mark.parametrize(
    "born, fra",
    [(1937, _ym(65, 0)), (1940, _ym(65, 6)), (1950, _ym(66, 0)), (1955, _ym(66, 2)),
     (1958, _ym(66, 8)), (1959, _ym(66, 10)), (1960, _ym(67, 0)), (1975, _ym(67, 0))],
)
def test_retirement_fra_follows_the_ssa_table(born, fra):
    assert full_retirement_age(born) == fra


@pytest.mark.parametrize(
    "born, fra",
    [(1939, _ym(65, 0)), (1944, _ym(65, 10)), (1956, _ym(66, 0)), (1957, _ym(66, 2)),
     (1960, _ym(66, 8)), (1961, _ym(66, 10)), (1962, _ym(67, 0))],
)
def test_survivor_fra_follows_its_own_table(born, fra):
    assert survivor_full_retirement_age(born) == fra


def test_unknown_birth_year_keeps_the_old_default():
    assert full_retirement_age(None) == D(67)
    assert survivor_full_retirement_age(None) == D(67)


def test_claiming_at_67_with_an_fra_of_66_and_8_months_earns_delayed_credits():
    """4 months past FRA at 2/3 of 1% a month: +2.67%."""
    benefit = _SS.monthly_benefit(D("3000"), 67, full_retirement_age(1958))
    assert benefit == (D("3000") * (1 + 4 * D("2") / D("300"))).quantize(D("0.01"))


def test_claiming_at_66_with_an_fra_of_66_and_8_months_is_reduced_for_8_months():
    """8 months early at 5/9 of 1% a month: -4.44%, not the 12 months FRA 67 implied."""
    benefit = _SS.monthly_benefit(D("3000"), 66, full_retirement_age(1958))
    assert benefit == (D("3000") * (1 - 8 * D("5") / D("900"))).quantize(D("0.01"))


def test_a_year_uses_the_claimants_own_fra():
    """Born 1958, claiming at 67: the simulated household benefit carries the
    delayed credit, where FRA 67 gave the bare PIA."""
    settings = Settings(
        start_year=2025, required_spending=D("60000"),
        ss_pia_self=D("3000"), ss_claim_age_self=67, birth_year_self=1958,
    )
    annual = _annual_social_security(_engines(), settings, age_self=67, age_spouse=None)
    assert annual == _SS.monthly_benefit(D("3000"), 67, full_retirement_age(1958)) * 12
    assert annual > D("3000") * 12


def _engines():
    from src.data.tax_rules.rules import TaxRules
    from src.engines.irmaa import IRMAACalculator
    from src.engines.rmd import RMDCalculator
    from src.engines.tax.federal import FederalTaxEngine
    from src.engines.tax.state import StateTaxEngine
    from src.optimization.state import Engines

    rules = TaxRules()
    return Engines(federal=FederalTaxEngine(rules), state=StateTaxEngine(rules),
                   irmaa=IRMAACalculator(rules), rmd=RMDCalculator(rules),
                   ss=_SS, rules=rules)
