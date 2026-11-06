"""Tests for narrative template rendering of decision rationales."""

from decimal import Decimal

from src.rationale.models import (
    BracketFacts,
    ConversionRationale,
    DecisionRationale,
    ThresholdWarning,
    WithdrawalRationale,
)
from src.rationale.narrative import render_narrative


class TestConversionYearNarrative:
    """Test narrative rendering for conversion year scenarios."""

    def test_conversion_year_template_renders(self):
        """Conversion year produces narrative with all interpolated values."""
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
            counterfactual_none_tax=Decimal("0"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.24"),
            projected_future_marginal_rate=Decimal("0.26"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth", "traditional"],
            reason="standard order",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[],
            narrative="",
        )

        narrative = render_narrative(rationale)

        # Check key values are present
        assert "50,000" in narrative  # amount
        assert "22%" in narrative  # rate
        assert "206,700" in narrative  # top
        assert "10,000" in narrative  # remaining
        assert "22.0%" in narrative  # marginal
        assert "24.0%" in narrative  # betr (formatted as .1%)
        assert "26%" in narrative  # projected
        # Neutral single-year framing — no favorable/unfavorable verdict word.
        assert "break-even" in narrative.lower()
        assert "lifetime totals" in narrative
        assert "favorable" not in narrative

    def test_conversion_year_sentence_count(self):
        """Conversion year narrative has 2-4 sentences."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        conversion = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills the 22% bracket",
            counterfactual_none_tax=Decimal("11000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.24"),
            projected_future_marginal_rate=Decimal("0.26"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth"],
            reason="standard",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[],
            narrative="",
        )

        narrative = render_narrative(rationale)
        sentence_count = narrative.count(". ")

        # Should be 2-4 sentences (3 sentences for conversion + 1 for BETR phrasing)
        assert 2 <= sentence_count <= 4, f"Got {sentence_count} sentences: {narrative}"

    def test_conversion_year_top_bracket_graceful_degradation(self):
        """Conversion year with None bracket_top uses top bracket phrasing."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.37"),
            bracket_top=None,  # top bracket
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("0"),
        )
        conversion = ConversionRationale(
            action_id="fill_37",
            amount=Decimal("50000"),
            target_description="fills the 37% bracket",
            counterfactual_none_tax=Decimal("18500"),
            marginal_cost_rate=Decimal("0.37"),
            betr=Decimal("0.38"),
            projected_future_marginal_rate=Decimal("0.40"),
            betr_verdict="marginal",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth"],
            reason="standard",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[],
            narrative="",
        )

        narrative = render_narrative(rationale)

        # Should mention "top bracket" and not try to format None as currency
        assert "37%" in narrative
        assert "top bracket" in narrative or "37% bracket" in narrative
        # Make sure it doesn't crash and produces a valid narrative
        assert len(narrative) > 50


class TestZeroConversionRmdNarrative:
    """Test narrative rendering for zero-conversion with RMD scenarios."""

    @staticmethod
    def _rmd_year(headroom_remaining: str) -> DecisionRationale:
        return DecisionRationale(
            year=2026,
            age_self=74,
            bracket=BracketFacts(
                bracket_rate=Decimal("0.22"),
                bracket_top=Decimal("206700"),
                headroom_used=Decimal("0"),
                headroom_remaining=Decimal(headroom_remaining),
            ),
            conversion=None,
            withdrawal=WithdrawalRationale(
                order_used=["rmd", "taxable"],
                reason="RMD required distribution",
                rmd_amount=Decimal("32000"),
            ),
            warnings=[],
            narrative="",
        )

    def test_rmd_that_fills_the_bracket_is_named_as_the_cause(self):
        """No room left in the bracket: the recorded sizing establishes the cause."""
        from src.rationale.narrative import RULE_FOUND_NO_ROOM

        for reason in (None, RULE_FOUND_NO_ROOM):
            narrative = render_narrative(self._rmd_year("0"), reason)
            assert "No conversion" in narrative
            assert "$32,000" in narrative  # verbatim dollar figure
            assert "already fills the 22% bracket" in narrative

    def test_rmd_year_with_bracket_room_left_invents_no_cause(self):
        """Regression: an RMD with $10,000 of bracket room left did not fill the
        bracket, so the narrative must not say it did."""
        from src.rationale.narrative import RULE_FOUND_NO_ROOM

        rationale = self._rmd_year("10000")
        for reason in (None, RULE_FOUND_NO_ROOM):
            narrative = render_narrative(rationale, reason)
            assert "fills" not in narrative
            assert "This year's required minimum distribution is $32,000." in narrative
        assert render_narrative(rationale, RULE_FOUND_NO_ROOM).startswith(
            f"No Roth conversion this year: {RULE_FOUND_NO_ROOM}.")
        # A reason known from the strategy wins even when the bracket is full.
        assert render_narrative(self._rmd_year("0"), "the recommended strategy "
                                "converts only through 2025").startswith(
            "No Roth conversion this year: the recommended strategy converts only through 2025.")


class TestZeroConversionWindowClosedNarrative:
    """Test narrative rendering for zero-conversion outside window."""

    def test_zero_conversion_window_closed_template_renders(self):
        """Zero-conversion outside window produces window-closed template."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("0"),
            headroom_remaining=Decimal("50000"),
        )
        withdrawal = WithdrawalRationale(
            order_used=["taxable"],
            reason="outside window",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=75,
            bracket=bracket,
            conversion=None,
            withdrawal=withdrawal,
            warnings=[],
            narrative="",
        )

        narrative = render_narrative(rationale)

        # Honest template: cannot claim window-closed when the optimizer may
        # simply have preferred $0 — text covers both, names the evidence.
        assert "No Roth conversion" in narrative
        assert "window" in narrative.lower()
        assert "evaluated" in narrative.lower()


class TestWarningAppending:
    """Test warning appending to narratives."""

    def test_below_threshold_warning_appended(self):
        """Below-threshold warning appends caution sentence."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        conversion = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills the 22% bracket",
            counterfactual_none_tax=Decimal("11000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.24"),
            projected_future_marginal_rate=Decimal("0.26"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth"],
            reason="standard",
        )
        warning = ThresholdWarning(
            kind="irmaa_tier",
            threshold=Decimal("194000"),
            distance=Decimal("5000"),  # positive = below threshold
            consequence="Part B/D surcharge of $2,104.80/yr",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[warning],
            narrative="",
        )

        narrative = render_narrative(rationale)

        # Should include caution and warning details
        assert "Caution" in narrative
        assert "5,000" in narrative  # distance
        assert "below" in narrative
        assert "IRMAA" in narrative  # humanized label

    def test_crossed_threshold_warning_appended(self):
        """Crossed-threshold warning appends different caution phrasing."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        conversion = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills the 22% bracket",
            counterfactual_none_tax=Decimal("11000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.24"),
            projected_future_marginal_rate=Decimal("0.26"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth"],
            reason="standard",
        )
        warning = ThresholdWarning(
            kind="niit",
            threshold=Decimal("194000"),
            distance=Decimal("-2000"),  # negative = crossed threshold
            consequence="3.8% NIIT on net investment income",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[warning],
            narrative="",
        )

        narrative = render_narrative(rationale)

        # New grammar: "MAGI crossed the <label> threshold by $<amount>."
        assert "Caution" in narrative
        assert "crossed" in narrative
        assert "NIIT" in narrative  # humanized label
        assert "by $2,000" in narrative  # distance appears after "by $"
        assert "MAGI is" not in narrative  # old grammar must not appear

    def test_multiple_warnings_appended(self):
        """Multiple warnings append multiple caution sentences."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("50000"),
            headroom_remaining=Decimal("10000"),
        )
        conversion = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("50000"),
            target_description="fills the 22% bracket",
            counterfactual_none_tax=Decimal("11000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.24"),
            projected_future_marginal_rate=Decimal("0.26"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth"],
            reason="standard",
        )
        warnings = [
            ThresholdWarning(
                kind="irmaa_tier",
                threshold=Decimal("194000"),
                distance=Decimal("5000"),
                consequence="Part B/D surcharge",
            ),
            ThresholdWarning(
                kind="niit",
                threshold=Decimal("194000"),
                distance=Decimal("-3000"),
                consequence="3.8% NIIT",
            ),
        ]
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=warnings,
            narrative="",
        )

        narrative = render_narrative(rationale)

        # Should include both cautions
        caution_count = narrative.count("Caution:")
        assert caution_count == 2


class TestEdgeCases:
    """Test edge cases and formatting."""

    def test_decimal_formatting_with_currency(self):
        """Large amounts format with thousands separator."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("500000"),
            headroom_used=Decimal("250000"),
            headroom_remaining=Decimal("100000"),
        )
        conversion = ConversionRationale(
            action_id="fill_22",
            amount=Decimal("250000"),
            target_description="large conversion",
            counterfactual_none_tax=Decimal("55000"),
            marginal_cost_rate=Decimal("0.22"),
            betr=Decimal("0.25"),
            projected_future_marginal_rate=Decimal("0.28"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth"],
            reason="standard",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[],
            narrative="",
        )

        narrative = render_narrative(rationale)

        # Verify comma formatting
        assert "250,000" in narrative
        assert "500,000" in narrative
        assert "100,000" in narrative

    def test_conversion_narrative_uses_bracket_rate_not_marginal_cost(self):
        """'Filling the X% bracket' must use bracket_rate, not marginal_cost_rate."""
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
            counterfactual_none_tax=Decimal("0"),
            marginal_cost_rate=Decimal("0.31"),  # deliberately higher than bracket_rate
            betr=Decimal("0.24"),
            projected_future_marginal_rate=Decimal("0.26"),
            betr_verdict="favorable",
        )
        withdrawal = WithdrawalRationale(
            order_used=["roth"],
            reason="standard",
        )
        rationale = DecisionRationale(
            year=2026,
            age_self=72,
            bracket=bracket,
            conversion=conversion,
            withdrawal=withdrawal,
            warnings=[],
            narrative="",
        )

        narrative = render_narrative(rationale)

        # bracket label must show 22% (bracket_rate), not 31% (marginal_cost_rate)
        assert "22%" in narrative
        assert "31%" not in narrative.split("cost")[0]  # 31% only appears after "cost"
        assert "31.0%" in narrative  # marginal cost still appears in "cost X% in tax now"


class TestWarningsDoNotBreakSentenceGuarantee:
    """The base narrative sentence guarantee applies before warnings are appended."""

    def test_base_plus_two_warnings_renders_correctly(self):
        """With 2 warnings, both caution sentences appear and base narrative is intact."""
        bracket = BracketFacts(
            bracket_rate=Decimal("0.22"),
            bracket_top=Decimal("206700"),
            headroom_used=Decimal("0"),
            headroom_remaining=Decimal("50000"),
        )
        withdrawal = WithdrawalRationale(
            order_used=["taxable"],
            reason="outside window",
        )
        warnings = [
            ThresholdWarning(
                kind="irmaa_tier",
                threshold=Decimal("212000"),
                distance=Decimal("3000"),
                consequence="Part B/D surcharge of $1,000/yr for this couple",
            ),
            ThresholdWarning(
                kind="niit",
                threshold=Decimal("250000"),
                distance=Decimal("8000"),
                consequence="NIIT 3.8% will apply to net investment income",
            ),
        ]
        rationale = DecisionRationale(
            year=2026,
            age_self=68,
            bracket=bracket,
            conversion=None,
            withdrawal=withdrawal,
            warnings=warnings,
            narrative="",
        )

        narrative = render_narrative(rationale)

        # Base narrative is intact
        assert "No Roth conversion" in narrative
        assert "window" in narrative.lower()
        # Both caution sentences present
        assert narrative.count("Caution:") == 2
        assert "IRMAA" in narrative
        assert "NIIT" in narrative


class TestUnfavorableVerdictReconciliation:
    """An unfavorable single-year BETR on a chosen strategy must explain why
    it can still be the right call (user report: 'the explanation says
    unfavorable when in fact we are doing a Roth conversion')."""

    def _rationale(self, verdict: str):
        return DecisionRationale(
            year=2026,
            age_self=63,
            bracket=BracketFacts(
                bracket_rate=Decimal("0.24"),
                bracket_top=Decimal("403550"),
                headroom_used=Decimal("310750"),
                headroom_remaining=Decimal("0"),
            ),
            conversion=ConversionRationale(
                action_id="fill_24",
                amount=Decimal("310750"),
                target_description="fills the 24% bracket",
                counterfactual_none_tax=Decimal("18590"),
                marginal_cost_rate=Decimal("0.488"),
                betr=Decimal("0.474"),
                projected_future_marginal_rate=Decimal("0.22"),
                betr_verdict=verdict,
            ),
            withdrawal=WithdrawalRationale(order_used=["taxable"], reason="x"),
            warnings=[],
            narrative="",
        )

    def test_conversion_narrative_always_carries_reconciliation_clause(self):
        # The neutral single-year framing is shown regardless of the (retained)
        # verdict value — the per-year break-even is not the decision.
        for verdict in ("unfavorable", "favorable", "marginal"):
            narrative = render_narrative(self._rationale(verdict))
            assert "one year in isolation" in narrative
            assert "Close alternatives" in narrative
        # No favorable/unfavorable judgment word leaks into the prose. ("marginal"
        # is excluded here because it legitimately appears in "marginal rate".)
        assert "favorable" not in render_narrative(self._rationale("favorable"))
        assert "unfavorable" not in render_narrative(self._rationale("unfavorable"))


class TestZeroConversionReason:
    """A zero-conversion year in a stored plan states the known reason, not
    "either the window is closed, or ..."."""

    def test_reasons_follow_the_strategy(self):
        from decimal import Decimal

        from src.rationale.narrative import RULE_FOUND_NO_ROOM, zero_conversion_reason

        def reason(pid, year, first=2027, last=2030, trad=Decimal("100000")):
            return zero_conversion_reason(pid, year, first, last, trad)

        assert reason("none", 2026, None, None) == (
            "the recommended strategy makes no Roth conversions")
        assert reason("fill_22_annual", 2026) == (
            "the recommended strategy starts converting in 2027")
        assert reason("fill_22_thru_2030", 2031) == (
            "the recommended strategy converts only through 2030")
        assert reason("fill_22_annual", 2031) == (
            "the recommended strategy's last conversion is in 2030")
        assert reason("fill_22_annual", 2031, trad=Decimal("0")) == (
            "nothing is left in traditional accounts to convert")
        assert reason("fill_22_annual", 2028) == RULE_FOUND_NO_ROOM

    def test_a_stored_plan_never_uses_the_either_or_wording(self):
        from src.optimization.optimizer import run_optimization
        from tests.integration.test_joint import ENGINES, _couple

        state, settings, constraints = _couple()
        for forced in (None, "none"):
            result = run_optimization(state, ENGINES, settings, constraints,
                                      monte_carlo_runs=0, forced_policy=forced)
            narratives = [y["rationale"]["narrative"] for y in result["yearly_plan"]]
            assert not any("either the conversion window" in n for n in narratives)
        # The no-conversion plan says so, every year it has no RMD to name.
        assert any(n.startswith("No Roth conversion this year: the recommended strategy makes no")
                   for n in narratives)
