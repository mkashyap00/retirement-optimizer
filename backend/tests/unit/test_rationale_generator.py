"""Unit tests for rationale generator — TDD RED phase.

Tests written before implementation per p06-task-2-brief.md:
  (a) Conversion year: marginal_cost_rate in (0.10, 0.45); target_description contains bracket top.
  (b) Zero-conversion year: conversion is None.
  (c) MAGI $2k below IRMAA tier → exactly one irmaa_tier warning, distance == 2000.
  (d) BETR verdict favorable when projected > betr + 0.02.
"""
from decimal import Decimal

from src.data.tax_rules.rules import TaxRules
from src.optimization.state import Settings, YearLedger
from src.rationale.generator import build_rationale

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(**kwargs) -> YearLedger:
    """Build a YearLedger with safe defaults; override via kwargs."""
    defaults = dict(
        year=2025,
        age_self=63,
        age_spouse=None,
        rmd=Decimal("0"),
        conversion=Decimal("0"),
        withdrawal_taxable=Decimal("0"),
        withdrawal_traditional=Decimal("0"),
        withdrawal_roth=Decimal("0"),
        realized_gains=Decimal("0"),
        agi=Decimal("150000"),
        magi=Decimal("150000"),
        federal_tax=Decimal("25000"),
        state_tax=Decimal("5000"),
        irmaa=Decimal("0"),
        total_tax=Decimal("30000"),
        net_spendable=Decimal("80000"),
        required_spending=Decimal("80000"),
        shortfall=Decimal("0"),
        marginal_rate=Decimal("0.22"),
        end_taxable=Decimal("500000"),
        end_traditional=Decimal("800000"),
        end_roth=Decimal("100000"),
    )
    defaults.update(kwargs)
    return YearLedger(**defaults)


def _make_settings(**kwargs) -> Settings:
    defaults = dict(
        start_year=2025,
        required_spending=Decimal("80000"),
        nominal_return=Decimal("0.06"),
        dividend_yield=Decimal("0.02"),
    )
    defaults.update(kwargs)
    return Settings(**defaults)


# Ledgers shared across test (a) and (d) — 22 % bracket, $40k conversion
def _conversion_ledger() -> YearLedger:
    """Ledger with 22% marginal rate, $40k conversion, total_tax $32,000."""
    return _make_ledger(
        age_self=63,
        conversion=Decimal("40000"),
        agi=Decimal("170000"),
        magi=Decimal("170000"),
        total_tax=Decimal("32000"),
        marginal_rate=Decimal("0.22"),
        withdrawal_roth=Decimal("0"),  # paid_from_taxable=True
    )


def _zero_conversion_ledger() -> YearLedger:
    """Counterfactual: same year, zero conversion, total_tax $23,200."""
    return _make_ledger(
        age_self=63,
        conversion=Decimal("0"),
        agi=Decimal("130000"),
        magi=Decimal("130000"),
        total_tax=Decimal("23200"),
        marginal_rate=Decimal("0.22"),
    )


# ---------------------------------------------------------------------------
# (a) Conversion year
# ---------------------------------------------------------------------------

class TestConversionYear:
    """Conversion year: marginal_cost_rate and target_description."""

    def test_marginal_cost_rate_in_expected_range(self):
        """Marginal cost rate is in (0.10, 0.45) for a typical 22%-bracket conversion."""
        rationale = build_rationale(
            ledger=_conversion_ledger(),
            zero_ledger=_zero_conversion_ledger(),
            action_id="fill_22",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        assert rationale.conversion is not None
        # (32000 - 23200) / 40000 = 0.22, well within (0.10, 0.45)
        assert Decimal("0.10") < rationale.conversion.marginal_cost_rate < Decimal("0.45")

    def test_target_description_contains_formatted_bracket_top(self):
        """target_description contains the thousands-separated 22%-bracket ceiling."""
        rationale = build_rationale(
            ledger=_conversion_ledger(),
            zero_ledger=_zero_conversion_ledger(),
            action_id="fill_22",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        assert rationale.conversion is not None
        # 2025 joint 22% bracket top = $206,700
        assert "206,700" in rationale.conversion.target_description


# ---------------------------------------------------------------------------
# (b) Zero-conversion year
# ---------------------------------------------------------------------------

class TestZeroConversionYear:
    """Zero-conversion year: DecisionRationale.conversion must be None."""

    def test_conversion_is_none_when_no_conversion(self):
        """When ledger.conversion == 0, conversion rationale is None."""
        rationale = build_rationale(
            ledger=_make_ledger(conversion=Decimal("0")),
            zero_ledger=None,
            action_id="none",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        assert rationale.conversion is None

    def test_conversion_is_none_when_zero_ledger_unavailable(self):
        """When zero_ledger is None (even if conversion > 0), conversion rationale is None."""
        rationale = build_rationale(
            ledger=_conversion_ledger(),
            zero_ledger=None,
            action_id="fill_22",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        assert rationale.conversion is None


# ---------------------------------------------------------------------------
# (c) IRMAA warning — MAGI $2k below first joint threshold ($212,000)
# ---------------------------------------------------------------------------

class TestIrmaaWarning:
    """MAGI $2k below IRMAA tier → exactly one irmaa_tier warning with distance == 2000."""

    # 2023 MAGI sets the 2025 premium; 2025 joint IRMAA: tier-0 magi_upper =
    # $212,000; tier-1 at $266,000.
    # magi = $210,000 → distance = $2,000 ∈ (0, 10_000].
    # AGI = $210,000 → NIIT threshold ($250,000) is $40,000 away → no NIIT warning.

    def _build(self) -> object:
        ledger = _make_ledger(
            year=2023,
            agi=Decimal("210000"),
            magi=Decimal("210000"),
            marginal_rate=Decimal("0.22"),
            conversion=Decimal("0"),
        )
        return build_rationale(
            ledger=ledger,
            zero_ledger=None,
            action_id="none",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )

    def test_exactly_one_irmaa_tier_warning(self):
        """Exactly one irmaa_tier warning when MAGI is $2k below the first joint threshold."""
        rationale = self._build()
        irmaa_warnings = [w for w in rationale.warnings if w.kind == "irmaa_tier"]
        assert len(irmaa_warnings) == 1

    def test_irmaa_warning_distance_equals_2000(self):
        """The irmaa_tier warning distance is exactly 2000."""
        rationale = self._build()
        irmaa_warnings = [w for w in rationale.warnings if w.kind == "irmaa_tier"]
        assert irmaa_warnings[0].distance == Decimal("2000")


# ---------------------------------------------------------------------------
# (e) IRMAA single filer — per-person surcharge calculation
# ---------------------------------------------------------------------------


class TestIrmaaSingleFiler:
    """Single filer IRMAA surcharge is half the joint amount (1 person vs. 2)."""

    def test_single_filer_surcharge_is_half_of_joint(self):
        """Single filer MAGI at same proximity threshold yields surcharge / 2.

        2025 single IRMAA: tier-0 magi_upper = $106,000; tier-1 at $133,000.
        magi = $104,000 → distance = $2,000 ∈ (0, 10_000].
        Single filer surcharge should be exactly half the joint amount.
        """
        # Joint filer scenario
        # 2023 MAGI is judged against the published 2025 premium-year table.
        ledger_joint = _make_ledger(
            year=2023,
            agi=Decimal("210000"),
            magi=Decimal("210000"),
            marginal_rate=Decimal("0.22"),
            conversion=Decimal("0"),
        )
        rationale_joint = build_rationale(
            ledger=ledger_joint,
            zero_ledger=None,
            action_id="none",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        irmaa_joint = [w for w in rationale_joint.warnings if w.kind == "irmaa_tier"]
        assert len(irmaa_joint) == 1

        # Extract dollar amount from joint consequence (e.g. "$1,234.56/yr for this couple")
        import re
        match_joint = re.search(r"\$([0-9,]+\.[0-9]{2})", irmaa_joint[0].consequence)
        assert match_joint is not None
        joint_amount = Decimal(match_joint.group(1).replace(",", ""))

        # Single filer scenario at same proximity: 2025 single tier-0 upper = $106,000
        ledger_single = _make_ledger(
            year=2023,
            agi=Decimal("104000"),
            magi=Decimal("104000"),
            marginal_rate=Decimal("0.22"),
            conversion=Decimal("0"),
        )
        rationale_single = build_rationale(
            ledger=ledger_single,
            zero_ledger=None,
            action_id="none",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="single",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        irmaa_single = [w for w in rationale_single.warnings if w.kind == "irmaa_tier"]
        assert len(irmaa_single) == 1

        # Extract dollar amount from single consequence
        match_single = re.search(r"\$([0-9,]+\.[0-9]{2})", irmaa_single[0].consequence)
        assert match_single is not None
        single_amount = Decimal(match_single.group(1).replace(",", ""))

        # Single should be exactly half of joint
        assert single_amount == joint_amount / 2

    def test_single_filer_phrasing(self):
        """Single filer consequence uses 'for a single filer' not 'for this couple'."""
        ledger = _make_ledger(
            agi=Decimal("104000"),
            magi=Decimal("104000"),
            marginal_rate=Decimal("0.22"),
            conversion=Decimal("0"),
        )
        rationale = build_rationale(
            ledger=ledger,
            zero_ledger=None,
            action_id="none",
            rules=TaxRules(),
            settings=_make_settings(),
            filing_status="single",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        irmaa_single = [w for w in rationale.warnings if w.kind == "irmaa_tier"]
        assert len(irmaa_single) == 1
        assert "for a single filer" in irmaa_single[0].consequence
        assert "for this couple" not in irmaa_single[0].consequence


# ---------------------------------------------------------------------------
# (d) BETR verdict — favorable when projected_future_marginal_rate > betr + 0.02
# ---------------------------------------------------------------------------

class TestBetrVerdict:
    """betr_verdict is 'favorable' when projected substantially exceeds computed betr."""

    def test_betr_verdict_favorable(self):
        """With projected=0.24 and computed betr ≈ 0.214 (< 0.22), verdict is 'favorable'.

        Derivation:
          marginal_cost_rate = (32000 - 23200) / 40000 = 0.22
          years_to_drawdown  = max(1, 73 - 63) = 10
          taxable_drag       = 0.02 * 0.15 = 0.003
          paid_from_taxable  = True  (withdrawal_roth == 0)
          betr               ≈ 0.22 * (1.057^10 / 1.06^10) ≈ 0.214
          projected (0.24) > betr + 0.02 (≈ 0.234) → "favorable"
        """
        rationale = build_rationale(
            ledger=_conversion_ledger(),
            zero_ledger=_zero_conversion_ledger(),
            action_id="fill_22",
            rules=TaxRules(),
            settings=_make_settings(
                nominal_return=Decimal("0.06"),
                dividend_yield=Decimal("0.02"),
            ),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )
        assert rationale.conversion is not None
        assert rationale.conversion.betr_verdict == "favorable"

    def test_betr_verdict_marginal_at_boundary(self):
        """betr_verdict is 'marginal' when projected == betr + 0.02 exactly.

        Compute betr from a rationale, then re-call with projected = betr + 0.02.
        Should yield betr_verdict == 'marginal' at the exact boundary.
        """
        # First call: get the computed betr with any projected rate
        rationale_initial = build_rationale(
            ledger=_conversion_ledger(),
            zero_ledger=_zero_conversion_ledger(),
            action_id="fill_22",
            rules=TaxRules(),
            settings=_make_settings(
                nominal_return=Decimal("0.06"),
                dividend_yield=Decimal("0.02"),
            ),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.30"),  # arbitrary
        )
        assert rationale_initial.conversion is not None
        computed_betr = rationale_initial.conversion.betr

        # Second call: set projected exactly at betr + 0.02 boundary
        projected_at_boundary = computed_betr + Decimal("0.02")
        rationale_boundary = build_rationale(
            ledger=_conversion_ledger(),
            zero_ledger=_zero_conversion_ledger(),
            action_id="fill_22",
            rules=TaxRules(),
            settings=_make_settings(
                nominal_return=Decimal("0.06"),
                dividend_yield=Decimal("0.02"),
            ),
            filing_status="joint",
            projected_future_marginal_rate=projected_at_boundary,
        )
        assert rationale_boundary.conversion is not None
        assert rationale_boundary.conversion.betr_verdict == "marginal"


# ---------------------------------------------------------------------------
# Bracket location from the audit worksheet
# ---------------------------------------------------------------------------

def _audited_ledger(
    taxable_ordinary: str,
    marginal_rate: str,
    conversion: str = "57000",
    realized_ltcg: str = "0",
) -> YearLedger:
    """A 2026 joint ledger carrying the raw audit simulate_year attaches.

    The audit is the raw one — no ``ordinary_income`` key, which only
    ``run_optimization`` adds after the rationale has been built.
    """
    deduction = Decimal("32200")
    tord = Decimal(taxable_ordinary)
    ltcg = Decimal(realized_ltcg)
    agi = tord + deduction + ltcg
    return _make_ledger(
        year=2026,
        conversion=Decimal(conversion),
        agi=agi,
        magi=agi,
        marginal_rate=Decimal(marginal_rate),
        audit={
            "agi": agi,
            "deduction": deduction,
            "realized_ltcg": ltcg,
            "taxable_income": tord + ltcg,
            "taxable_ordinary_income": tord,
        },
    )


class TestBracketFromAudit:
    """The bracket is the one holding the LAST dollar of taxable ordinary income.

    ``ledger.marginal_rate`` is the rate on the NEXT dollar, so a conversion that
    fills the 10% bracket exactly to its $24,800 edge reports 12% — and the label
    used to say "fills the 12% bracket to $100,800" for a fill_10 year.
    """

    def _rationale(self, ledger: YearLedger):
        return build_rationale(
            ledger=ledger,
            zero_ledger=_make_ledger(year=2026, total_tax=Decimal("20000")),
            action_id="fill_10",
            rules=TaxRules(),
            settings=_make_settings(start_year=2026),
            filing_status="joint",
            projected_future_marginal_rate=Decimal("0.24"),
        )

    def test_fill_to_exact_edge_names_the_filled_bracket(self):
        r = self._rationale(_audited_ledger("24800", marginal_rate="0.12"))
        assert r.bracket.bracket_rate == Decimal("0.10")
        assert r.bracket.bracket_top == Decimal("24800")
        assert r.bracket.headroom_remaining == Decimal("0")
        assert r.conversion.target_description == "fills the 10% bracket to $24,800"

    def test_just_below_edge_agrees_with_exact_edge(self):
        r = self._rationale(_audited_ledger("24799.34", marginal_rate="0.10"))
        assert r.conversion.target_description == "fills the 10% bracket to $24,800"

    def test_headroom_ignores_capital_gains(self):
        # 2028 of the reported run: $67,800 of taxable ordinary income with $83k
        # of realized gains. Headroom was $0 because AGI (gains included) stood
        # in for ordinary income; the 12% bracket really has $33,000 left.
        ledger = _audited_ledger(
            "67800", marginal_rate="0.12", conversion="0", realized_ltcg="83827.53"
        )
        r = self._rationale(ledger)
        assert r.bracket.bracket_rate == Decimal("0.12")
        assert r.bracket.headroom_remaining == Decimal("33000")

    def test_no_taxable_ordinary_income_is_the_bottom_bracket(self):
        r = self._rationale(_audited_ledger("0", marginal_rate="0.10", conversion="0"))
        assert r.bracket.bracket_rate == Decimal("0.10")
        assert r.bracket.headroom_remaining == Decimal("24800")


# ─── BETR's drawdown horizon uses the owner's RMD age ────────────────────────
#
# Found by the hardcoded-values sweep: the horizon was max(1, 73 - age) for
# everyone, two years short for anyone born 1960 or later (RMDs at 75).


def test_betr_horizon_runs_to_75_for_the_1960_cohort():
    from decimal import Decimal as _D

    from src.optimization.state import Settings as _Settings
    from src.rationale.generator import _years_to_rmds

    born_1962 = _Settings(start_year=2026, required_spending=_D("1"), birth_year_self=1962)
    born_1955 = _Settings(start_year=2026, required_spending=_D("1"), birth_year_self=1955)
    unknown = _Settings(start_year=2026, required_spending=_D("1"))

    assert _years_to_rmds(64, born_1962) == 11
    assert _years_to_rmds(64, born_1955) == 9
    assert _years_to_rmds(64, unknown) == 9
    assert _years_to_rmds(80, born_1955) == 1
