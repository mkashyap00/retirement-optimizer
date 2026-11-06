"""Unit tests for decision rationale dataclasses.

TDD RED phase: tests written per p06-task-1-brief.md before implementation.
"""
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest
from src.rationale.models import (
    BracketFacts,
    ConversionRationale,
    DecisionRationale,
    ThresholdWarning,
    WithdrawalRationale,
)


class TestBracketFacts:
    """Tests for BracketFacts dataclass."""

    def test_bracket_facts_construction(self):
        """Construct BracketFacts with all fields."""
        bf = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        assert bf.bracket_rate == Decimal("0.22")
        assert bf.bracket_top == Decimal("206700")
        assert bf.headroom_used == Decimal("50000")
        assert bf.headroom_remaining == Decimal("10000")

    def test_bracket_facts_with_none_bracket_top(self):
        """BracketFacts allows None for bracket_top (top bracket case)."""
        bf = BracketFacts(
            bracket_rate=Decimal("0.37"),
            bracket_top=None,
            headroom_used=Decimal("100000"),
            headroom_remaining=Decimal("0"),
        )
        assert bf.bracket_top is None
        assert bf.headroom_remaining == Decimal("0")

    def test_bracket_facts_is_frozen(self):
        """BracketFacts is frozen (immutable)."""
        bf = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        with pytest.raises(FrozenInstanceError):
            bf.bracket_rate = Decimal("0.24")


class TestThresholdWarning:
    """Tests for ThresholdWarning dataclass."""

    def test_threshold_warning_construction(self):
        """Construct ThresholdWarning with all fields."""
        tw = ThresholdWarning(
            kind="irmaa_tier",
            threshold=Decimal("200000"),
            distance=Decimal("5000"),
            consequence="Part B/D surcharge of $2,104.80/yr for this couple",
        )
        assert tw.kind == "irmaa_tier"
        assert tw.threshold == Decimal("200000")
        assert tw.distance == Decimal("5000")
        assert tw.consequence == "Part B/D surcharge of $2,104.80/yr for this couple"

    def test_threshold_warning_with_negative_distance(self):
        """ThresholdWarning distance can be negative (threshold crossed)."""
        tw = ThresholdWarning(
            kind="niit",
            threshold=Decimal("250000"),
            distance=Decimal("-3000"),
            consequence="NIIT applies",
        )
        assert tw.distance == Decimal("-3000")

    def test_threshold_warning_is_frozen(self):
        """ThresholdWarning is frozen (immutable)."""
        tw = ThresholdWarning(
            kind="irmaa_tier",
            threshold=Decimal("200000"),
            distance=Decimal("5000"),
            consequence="test",
        )
        with pytest.raises(FrozenInstanceError):
            tw.kind = "niit"


class TestConversionRationale:
    """Tests for ConversionRationale dataclass."""

    def test_conversion_rationale_construction(self):
        """Construct ConversionRationale with all fields."""
        cr = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills the 22% bracket to $206,700",
            counterfactual_none_tax=Decimal("50000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.18"),
            projected_future_marginal_rate=Decimal("0.32"),
            betr_verdict="favorable",
        )
        assert cr.action_id == "fill_22"
        assert cr.amount == Decimal("50000")
        assert cr.target_description == "fills the 22% bracket to $206,700"
        assert cr.counterfactual_none_tax == Decimal("50000")
        assert cr.marginal_cost_rate == Decimal("0.22")
        assert cr.betr == Decimal("0.18")
        assert cr.projected_future_marginal_rate == Decimal("0.32")
        assert cr.betr_verdict == "favorable"

    def test_conversion_rationale_marginal_verdict(self):
        """ConversionRationale handles 'marginal' verdict."""
        cr = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills",
            counterfactual_none_tax=Decimal("50000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.28"),
            projected_future_marginal_rate=Decimal("0.30"),
            betr_verdict="marginal",
        )
        assert cr.betr_verdict == "marginal"

    def test_conversion_rationale_unfavorable_verdict(self):
        """ConversionRationale handles 'unfavorable' verdict."""
        cr = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills",
            counterfactual_none_tax=Decimal("50000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.35"),
            projected_future_marginal_rate=Decimal("0.20"),
            betr_verdict="unfavorable",
        )
        assert cr.betr_verdict == "unfavorable"

    def test_conversion_rationale_is_frozen(self):
        """ConversionRationale is frozen (immutable)."""
        cr = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills",
            counterfactual_none_tax=Decimal("50000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.18"),
            projected_future_marginal_rate=Decimal("0.32"),
            betr_verdict="favorable",
        )
        with pytest.raises(FrozenInstanceError):
            cr.action_id = "fill_24"


class TestWithdrawalRationale:
    """Tests for WithdrawalRationale dataclass."""

    def test_withdrawal_rationale_construction(self):
        """Construct WithdrawalRationale with all fields."""
        wr = WithdrawalRationale(
            order_used=["rmd", "taxable", "traditional"],
            reason="taxable first: gains taxed at 0-15% vs 22% ordinary",
        )
        assert wr.order_used == ["rmd", "taxable", "traditional"]
        assert wr.reason == "taxable first: gains taxed at 0-15% vs 22% ordinary"

    def test_withdrawal_rationale_different_order(self):
        """WithdrawalRationale supports different withdrawal orders."""
        wr = WithdrawalRationale(
            order_used=["traditional", "roth"],
            reason="minimize irmaa impact",
        )
        assert wr.order_used == ["traditional", "roth"]

    def test_withdrawal_rationale_is_frozen(self):
        """WithdrawalRationale is frozen (immutable)."""
        wr = WithdrawalRationale(
            order_used=["rmd", "taxable"],
            reason="test",
        )
        with pytest.raises(FrozenInstanceError):
            wr.reason = "modified"


class TestDecisionRationale:
    """Tests for DecisionRationale dataclass."""

    def test_decision_rationale_full_construction(self):
        """Construct a full DecisionRationale with nested pieces."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        conversion = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills the 22% bracket to $206,700",
            counterfactual_none_tax=Decimal("50000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.18"),
            projected_future_marginal_rate=Decimal("0.32"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["rmd", "taxable", "traditional"],
            reason="taxable first: gains taxed at 0-15% vs 22% ordinary",
        )
        warning = ThresholdWarning(
            kind="irmaa_tier",
            threshold=Decimal("200000"),
            distance=Decimal("5000"),
            consequence="Part B/D surcharge of $2,104.80/yr for this couple",
        )

        dr = DecisionRationale(
            year=2025,
            age_self=62,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[warning],
            narrative="Convert $50k to fill the 22% bracket; withdraw taxable first for LTCG.",
        )

        assert dr.year == 2025
        assert dr.age_self == 62
        assert dr.bracket == bracket
        assert dr.conversion == conversion
        assert dr.withdrawal == withdrawal
        assert len(dr.warnings) == 1
        assert dr.warnings[0] == warning
        assert (
            dr.narrative
            == "Convert $50k to fill the 22% bracket; withdraw taxable first for LTCG."
        )

    def test_decision_rationale_with_none_conversion(self):
        """DecisionRationale allows None conversion when no conversion occurs."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("0"),
            headroom_remaining=Decimal("50000"),
        )
        withdrawal = WithdrawalRationale(
            order_used=["rmd"],
            reason="only rmd required",
        )

        dr = DecisionRationale(
            year=2025,
            age_self=72,
            bracket=bracket,
            conversion=None,
            withdrawal=withdrawal,
            warnings=[],
            narrative="No conversion warranted; RMD only.",
        )

        assert dr.conversion is None
        assert len(dr.warnings) == 0

    def test_decision_rationale_multiple_warnings(self):
        """DecisionRationale can hold multiple threshold warnings."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.32"),
            bracket_top=Decimal("578125"),
            headroom_used=Decimal("100000"),
            headroom_remaining=Decimal("10000"),
        )
        withdrawal = WithdrawalRationale(
            order_used=["traditional"],
            reason="minimize irmaa",
        )
        warning1 = ThresholdWarning(
            kind="irmaa_tier",
            threshold=Decimal("200000"),
            distance=Decimal("-5000"),
            consequence="Part B/D surcharge triggered",
        )
        warning2 = ThresholdWarning(
            kind="niit",
            threshold=Decimal("250000"),
            distance=Decimal("-10000"),
            consequence="NIIT 3.8% applies",
        )

        dr = DecisionRationale(
            year=2025,
            age_self=70,
            bracket=bracket,
            conversion=None,
            withdrawal=withdrawal,
            warnings=[warning1, warning2],
            narrative="High income year; IRMAA and NIIT both triggered.",
        )

        assert len(dr.warnings) == 2
        assert dr.warnings[0].kind == "irmaa_tier"
        assert dr.warnings[1].kind == "niit"

    def test_decision_rationale_is_frozen(self):
        """DecisionRationale is frozen (immutable)."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        withdrawal = WithdrawalRationale(
            order_used=["rmd", "taxable"],
            reason="test",
        )

        dr = DecisionRationale(
            year=2025,
            age_self=62,
            bracket=bracket,
            conversion=None,
            withdrawal=withdrawal,
            warnings=[],
            narrative="test",
        )

        with pytest.raises(FrozenInstanceError):
            dr.year = 2026

    def test_decision_rationale_field_access(self):
        """DecisionRationale fields are accessible and correct."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        withdrawal = WithdrawalRationale(
            order_used=["rmd", "taxable"],
            reason="test reason",
        )

        dr = DecisionRationale(
            year=2025,
            age_self=62,
            bracket=bracket,
            conversion=None,
            withdrawal=withdrawal,
            warnings=[],
            narrative="test narrative",
        )

        # Verify all fields are accessible
        assert dr.year == 2025
        assert dr.age_self == 62
        assert isinstance(dr.bracket, BracketFacts)
        assert dr.bracket.bracket_rate == Decimal("0.22")
        assert isinstance(dr.withdrawal, WithdrawalRationale)
        assert dr.withdrawal.order_used == ["rmd", "taxable"]
        assert dr.narrative == "test narrative"
