"""Tests for state income tax data loader — TDD (write RED first).

Brief-required tests (verbatim):
  test_no_tax_states, test_california_is_progressive, test_ss_taxing_states_is_small_and_current

Additional parsing tests added for confidence in the CSV parser.
"""
from decimal import Decimal

from src.data.tax_rules.state import (
    NO_TAX_STATES,
    STATES_TAXING_SS,
    state_brackets,
    state_standard_deduction,
)

# ── Brief's three required tests (verbatim) ─────────────────────────────────


def test_no_tax_states():
    assert {"FL", "TX", "WA", "NV", "WY", "SD", "AK", "TN", "NH"} <= NO_TAX_STATES
    assert state_brackets("TX", "single") == []


def test_california_is_progressive():
    ca = state_brackets("CA", "joint")
    assert len(ca) >= 5
    assert ca[-1].rate > ca[0].rate


def test_ss_taxing_states_is_small_and_current():
    # 2026: most states exempt SS. WV fully exempt from 2026; MO, NE, KS stopped 2024.
    assert "MO" not in STATES_TAXING_SS and "KS" not in STATES_TAXING_SS
    assert set(STATES_TAXING_SS) <= {"CO", "CT", "MN", "MT", "NM", "RI", "UT", "VT", "WV"}
    assert "MN" in STATES_TAXING_SS


# ── Parsing correctness tests ────────────────────────────────────────────────


def test_alabama_first_bracket():
    """Alabama 3-bracket: 2% to $500, 4% to $3000, 5% above."""
    al = state_brackets("AL", "single")
    assert len(al) == 3
    assert al[0].upper == Decimal("500")
    assert al[0].rate == Decimal("0.02")
    assert al[1].upper == Decimal("3000")
    assert al[1].rate == Decimal("0.04")
    assert al[-1].upper is None
    assert al[-1].rate == Decimal("0.05")


def test_california_bracket_count_and_rate():
    """Ordinary schedule only: 1% .. 12.3%. The 1% Mental Health Services Tax
    is a separate surcharge (STATE_SURCHARGES), not a 13.3% bracket."""
    ca_single = state_brackets("CA", "single")
    assert len(ca_single) == 9
    assert ca_single[-1].rate == Decimal("0.123")


def test_california_2025_matches_ftb_schedules():
    """FTB 2025 Schedules X and Y (2025-540-tax-rate-schedules.pdf)."""
    single = [b.upper for b in state_brackets("CA", "single")]
    joint = [b.upper for b in state_brackets("CA", "joint")]
    assert single == [Decimal(v) for v in (
        "11079", "26264", "41452", "57542", "72724", "371479", "445771", "742953")] + [None]
    assert joint == [Decimal(v) for v in (
        "22158", "52528", "82904", "115084", "145448", "742958", "891542", "1485906")] + [None]


def test_california_surcharge_is_separate_and_fixed():
    from src.data.tax_rules.state import STATE_SURCHARGES
    assert STATE_SURCHARGES["CA"] == (Decimal("1000000"), Decimal("0.01"))


def test_no_tax_state_empty_brackets():
    for state in ("WA", "AK", "FL", "NV", "WY", "SD", "TN", "TX", "NH"):
        assert state_brackets(state, "single") == [], f"{state} should have no brackets"
        assert state_brackets(state, "joint") == [], f"{state} should have no brackets"


def test_standard_deduction_california():
    assert state_standard_deduction("CA", "single") == Decimal("5706")
    assert state_standard_deduction("CA", "joint") == Decimal("11412")


def test_standard_deduction_no_deduction_state():
    """Illinois: n.a. deduction → 0."""
    assert state_standard_deduction("IL", "single") == Decimal("0")
    assert state_standard_deduction("IL", "joint") == Decimal("0")


def test_standard_deduction_no_tax_state_returns_zero():
    assert state_standard_deduction("TX", "single") == Decimal("0")
    assert state_standard_deduction("TX", "joint") == Decimal("0")


def test_utah_credit_not_deduction():
    """Utah has a credit, not a deduction — standard_deduction should return 0."""
    assert state_standard_deduction("UT", "single") == Decimal("0")
    assert state_standard_deduction("UT", "joint") == Decimal("0")


def test_north_dakota_implicit_zero_bracket():
    """ND brackets start at $48,475 for single — parser must prepend 0% bracket."""
    nd = state_brackets("ND", "single")
    assert nd[0].rate == Decimal("0")
    assert nd[0].upper == Decimal("48475")
    assert len(nd) == 3  # 0%, 1.95%, 2.50%


def test_ohio_implicit_zero_bracket():
    """Ohio starts at $26,050 — parser must prepend 0% bracket."""
    oh = state_brackets("OH", "single")
    assert oh[0].rate == Decimal("0")
    assert oh[0].upper == Decimal("26050")


def test_mississippi_implicit_zero_bracket():
    """Mississippi starts at $10,000 — parser must prepend 0% bracket."""
    ms = state_brackets("MS", "single")
    assert ms[0].rate == Decimal("0")
    assert ms[0].upper == Decimal("10000")


def test_new_jersey_asymmetric_brackets():
    """NJ has 7 single brackets and 8 joint brackets (CSV asymmetry)."""
    nj_s = state_brackets("NJ", "single")
    nj_j = state_brackets("NJ", "joint")
    assert len(nj_j) > len(nj_s)


def test_last_bracket_has_no_upper():
    """Every taxing state's last bracket has upper=None."""
    for state in ("CA", "NY", "TX", "AL", "MN", "OR"):
        for status in ("single", "joint"):
            brackets = state_brackets(state, status)
            if brackets:
                assert brackets[-1].upper is None, (
                    f"{state}/{status}: last bracket upper should be None"
                )


def test_upper_bounds_strictly_increasing():
    """All non-None upper bounds are strictly increasing."""
    from src.data.tax_rules.state import _NAME_TO_CODE
    all_codes = set(_NAME_TO_CODE.values())
    for code in all_codes:
        for status in ("single", "joint"):
            brackets = state_brackets(code, status)
            if len(brackets) < 2:
                continue
            uppers = [b.upper for b in brackets[:-1]]  # exclude last (None)
            for i in range(len(uppers) - 1):
                assert uppers[i] < uppers[i + 1], (  # type: ignore[operator]
                    f"{code}/{status}: upper bounds not strictly increasing at bracket {i}"
                )


def test_bracket_rates_non_decreasing():
    """Bracket rates never decrease from one bracket to the next."""
    from src.data.tax_rules.state import _NAME_TO_CODE
    all_codes = set(_NAME_TO_CODE.values())
    for code in all_codes:
        for status in ("single", "joint"):
            brackets = state_brackets(code, status)
            for i in range(len(brackets) - 1):
                assert brackets[i].rate <= brackets[i + 1].rate, (
                    f"{code}/{status}: rate decreases at bracket {i}: "
                    f"{brackets[i].rate} > {brackets[i + 1].rate}"
                )


def test_unknown_state_returns_empty():
    assert state_brackets("ZZ", "single") == []
    assert state_brackets("ZZ", "joint") == []
    assert state_standard_deduction("ZZ", "single") == Decimal("0")
    assert state_standard_deduction("ZZ", "joint") == Decimal("0")


def test_louisiana_typo_handled():
    """CSV has 'Lousiana' (typo) — must still parse to 'LA'."""
    la = state_brackets("LA", "single")
    assert len(la) >= 1
    assert la[-1].upper is None


def test_dc_included():
    """District of Columbia maps to DC and has multiple brackets."""
    dc = state_brackets("DC", "single")
    assert len(dc) >= 5


# ---------------------------------------------------------------------------
# Year dimension — state data is year-keyed with clamp-to-latest (like federal)
# ---------------------------------------------------------------------------


class TestStateYearDimension:
    def test_known_years_includes_2025(self):
        from src.data.tax_rules import state as state_mod

        assert 2025 in state_mod.known_state_years()
        assert state_mod.latest_state_year() >= 2025

    def test_explicit_year_matches_default(self):
        assert state_brackets("CA", "joint", year=2025) == state_brackets("CA", "joint")
        assert state_standard_deduction("CA", "joint", year=2025) == (
            state_standard_deduction("CA", "joint")
        )

    def test_future_year_clamps_to_latest(self):
        assert state_brackets("CA", "joint", year=2035) == state_brackets("CA", "joint")

    def test_year_routing_selects_that_years_data(self, monkeypatch):
        """When a year's CSV exists, its data must be served — guards against
        an accepted-but-ignored year parameter."""
        from decimal import Decimal as D

        from src.data.tax_rules import state as state_mod
        from src.data.tax_rules.types import Bracket

        synthetic = (
            {("CA", "single"): [Bracket(upper=None, rate=D("0.99"))]},
            {("CA", "single"): D("12345")},
        )
        monkeypatch.setitem(state_mod._BY_YEAR, 2099, synthetic)
        assert state_brackets("CA", "single", year=2099)[0].rate == D("0.99")
        assert state_standard_deduction("CA", "single", year=2099) == D("12345")
        # Other years untouched
        assert state_brackets("CA", "single", year=2025)[0].rate != D("0.99")
