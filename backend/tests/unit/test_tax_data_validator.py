"""Tests for tax data validator — TDD RED phase first, then GREEN."""
import dataclasses
from decimal import Decimal

from src.data.tax_rules.federal import FEDERAL
from src.data.tax_rules.irmaa import IRMAA
from src.data.tax_rules.types import (
    Bracket,
    FederalTaxYear,
    IrmaaTier,
    IrmaaYear,
)
from src.data.tax_rules.validator import validate_all, validate_federal_year

# ---------------------------------------------------------------------------
# Healthy data — shipped data should have zero issues
# ---------------------------------------------------------------------------

class TestHealthyData:
    def test_validate_all_returns_empty_for_shipped_data(self) -> None:
        issues = validate_all()
        assert issues == [], f"Unexpected validator issues: {issues}"

    def test_validate_federal_year_clean_for_2025(self) -> None:
        issues = validate_federal_year(FEDERAL[2025])
        assert issues == []

    def test_validate_federal_year_clean_for_2026(self) -> None:
        issues = validate_federal_year(FEDERAL[2026])
        assert issues == []


# ---------------------------------------------------------------------------
# Corruption detection — validator must catch bad data
# ---------------------------------------------------------------------------

def _make_bad_federal_year() -> FederalTaxYear:
    """Construct a FederalTaxYear with descending bracket uppers (invalid)."""
    good = FEDERAL[2025]
    # Reverse the non-top brackets so uppers descend instead of ascending
    bad_brackets_single = [
        Bracket(upper=Decimal("626350"), rate=Decimal("0.10")),  # huge upper first
        Bracket(upper=Decimal("250525"), rate=Decimal("0.12")),
        Bracket(upper=Decimal("197300"), rate=Decimal("0.22")),
        Bracket(upper=Decimal("103350"), rate=Decimal("0.24")),
        Bracket(upper=Decimal("48475"),  rate=Decimal("0.32")),
        Bracket(upper=Decimal("11925"),  rate=Decimal("0.35")),
        Bracket(upper=None,              rate=Decimal("0.37")),
    ]
    bad_brackets = {"single": bad_brackets_single, "joint": good.brackets["joint"]}
    return FederalTaxYear(
        year=good.year,
        source=good.source,
        brackets=bad_brackets,
        ltcg_brackets=good.ltcg_brackets,
        standard_deduction=good.standard_deduction,
        aged_addition=good.aged_addition,
        senior_bonus=good.senior_bonus,
        salt=good.salt,
        niit=good.niit,
    )


class TestCorruptionDetection:
    def test_descending_bracket_uppers_detected(self) -> None:
        bad = _make_bad_federal_year()
        issues = validate_federal_year(bad)
        assert len(issues) > 0

    def test_validate_all_with_injected_bad_federal(self) -> None:
        bad = _make_bad_federal_year()
        issues = validate_all(federal={2025: bad, 2026: FEDERAL[2026]})
        assert len(issues) > 0

    def test_missing_none_top_bracket_detected(self) -> None:
        """Last bracket must have upper=None."""
        good = FEDERAL[2025]
        bad_brackets_single = list(good.brackets["single"])
        # Replace the last bracket (upper=None) with one that has an upper bound
        bad_brackets_single[-1] = Bracket(upper=Decimal("999999"), rate=Decimal("0.37"))
        bad_brackets = {"single": bad_brackets_single, "joint": good.brackets["joint"]}
        bad_fy = FederalTaxYear(
            year=good.year,
            source=good.source,
            brackets=bad_brackets,
            ltcg_brackets=good.ltcg_brackets,
            standard_deduction=good.standard_deduction,
            aged_addition=good.aged_addition,
            senior_bonus=good.senior_bonus,
            salt=good.salt,
            niit=good.niit,
        )
        issues = validate_federal_year(bad_fy)
        assert any("upper" in issue.lower() or "top" in issue.lower() or "none" in issue.lower()
                   for issue in issues)

    def test_descending_rates_detected(self) -> None:
        """Bracket rates must strictly ascend."""
        good = FEDERAL[2025]
        # Give single the same upper-bound order but swap rates so they descend
        bad_brackets_single = [
            Bracket(upper=Decimal("11925"),  rate=Decimal("0.37")),
            Bracket(upper=Decimal("48475"),  rate=Decimal("0.35")),
            Bracket(upper=Decimal("103350"), rate=Decimal("0.32")),
            Bracket(upper=Decimal("197300"), rate=Decimal("0.24")),
            Bracket(upper=Decimal("250525"), rate=Decimal("0.22")),
            Bracket(upper=Decimal("626350"), rate=Decimal("0.12")),
            Bracket(upper=None,              rate=Decimal("0.10")),
        ]
        bad_brackets = {"single": bad_brackets_single, "joint": good.brackets["joint"]}
        bad_fy = FederalTaxYear(
            year=good.year, source=good.source,
            brackets=bad_brackets,
            ltcg_brackets=good.ltcg_brackets,
            standard_deduction=good.standard_deduction,
            aged_addition=good.aged_addition,
            senior_bonus=good.senior_bonus, salt=good.salt, niit=good.niit,
        )
        issues = validate_federal_year(bad_fy)
        assert len(issues) > 0

    def test_pending_source_detected(self) -> None:
        """'PENDING' in source string should be flagged."""
        good = FEDERAL[2025]
        bad_fy = FederalTaxYear(
            year=good.year, source="PENDING Rev. Proc.",
            brackets=good.brackets,
            ltcg_brackets=good.ltcg_brackets,
            standard_deduction=good.standard_deduction,
            aged_addition=good.aged_addition,
            senior_bonus=good.senior_bonus, salt=good.salt, niit=good.niit,
        )
        issues = validate_federal_year(bad_fy)
        assert any("PENDING" in issue or "pending" in issue.lower() for issue in issues)

    def test_zero_standard_deduction_detected(self) -> None:
        """Standard deduction must be > 0 for all filing statuses."""
        good = FEDERAL[2025]
        bad_fy = FederalTaxYear(
            year=good.year, source=good.source,
            brackets=good.brackets,
            ltcg_brackets=good.ltcg_brackets,
            standard_deduction={"single": Decimal("0"), "joint": Decimal("31500")},
            aged_addition=good.aged_addition,
            senior_bonus=good.senior_bonus, salt=good.salt, niit=good.niit,
        )
        issues = validate_federal_year(bad_fy)
        assert len(issues) > 0

    def test_zero_aged_addition_detected(self) -> None:
        """The age-65 additional standard deduction must be > 0 when present."""
        good = FEDERAL[2025]
        bad_fy = dataclasses.replace(
            good, aged_addition={"single": Decimal("0"), "joint": Decimal("1600")}
        )
        issues = validate_federal_year(bad_fy)
        assert any("aged_addition" in issue for issue in issues)

    def test_ltcg_must_start_at_zero_rate(self) -> None:
        """LTCG first bracket rate must be 0."""
        good = FEDERAL[2025]
        bad_ltcg = {
            "single": [
                Bracket(upper=Decimal("48350"),  rate=Decimal("0.05")),  # non-zero
                Bracket(upper=Decimal("533400"), rate=Decimal("0.15")),
                Bracket(upper=None,              rate=Decimal("0.20")),
            ],
            "joint": good.ltcg_brackets["joint"],
        }
        bad_fy = FederalTaxYear(
            year=good.year, source=good.source,
            brackets=good.brackets,
            ltcg_brackets=bad_ltcg,
            standard_deduction=good.standard_deduction,
            aged_addition=good.aged_addition,
            senior_bonus=good.senior_bonus, salt=good.salt, niit=good.niit,
        )
        issues = validate_federal_year(bad_fy)
        assert len(issues) > 0

    def test_ltcg_must_have_exactly_3_brackets(self) -> None:
        """LTCG must have exactly 3 brackets (0%, 15%, 20%)."""
        good = FEDERAL[2025]
        bad_ltcg = {
            "single": [
                Bracket(upper=Decimal("48350"),  rate=Decimal("0")),
                Bracket(upper=None,              rate=Decimal("0.20")),
            ],
            "joint": good.ltcg_brackets["joint"],
        }
        bad_fy = FederalTaxYear(
            year=good.year, source=good.source,
            brackets=good.brackets,
            ltcg_brackets=bad_ltcg,
            standard_deduction=good.standard_deduction,
            aged_addition=good.aged_addition,
            senior_bonus=good.senior_bonus, salt=good.salt, niit=good.niit,
        )
        issues = validate_federal_year(bad_fy)
        assert len(issues) > 0


# ---------------------------------------------------------------------------
# IRMAA validation
# ---------------------------------------------------------------------------

class TestIrmaaValidation:
    def test_irmaa_clean_for_2025(self) -> None:
        from src.data.tax_rules.validator import validate_irmaa_year
        issues = validate_irmaa_year(IRMAA[2025])
        assert issues == []

    def test_irmaa_tier0_part_b_must_equal_standard(self) -> None:
        from src.data.tax_rules.validator import validate_irmaa_year
        good = IRMAA[2025]
        # Make tier 0 part_b != standard
        bad_tiers_single = list(good.tiers["single"])
        bad_tiers_single[0] = IrmaaTier(
            magi_upper=bad_tiers_single[0].magi_upper,
            part_b_monthly=Decimal("999.00"),  # doesn't match part_b_standard=185
            part_d_monthly=bad_tiers_single[0].part_d_monthly,
        )
        bad_iy = IrmaaYear(
            year=good.year, source=good.source,
            part_b_standard=good.part_b_standard,
            tiers={"single": bad_tiers_single, "joint": good.tiers["joint"]},
        )
        issues = validate_irmaa_year(bad_iy)
        assert len(issues) > 0

    def test_irmaa_tiers_must_ascend(self) -> None:
        from src.data.tax_rules.validator import validate_irmaa_year
        good = IRMAA[2025]
        # Reverse the tiers so magi_upper descends
        reversed_tiers = list(reversed(good.tiers["single"]))
        bad_iy = IrmaaYear(
            year=good.year, source=good.source,
            part_b_standard=good.part_b_standard,
            tiers={"single": reversed_tiers, "joint": good.tiers["joint"]},
        )
        issues = validate_irmaa_year(bad_iy)
        assert len(issues) > 0


# ---------------------------------------------------------------------------
# RMD validation
# ---------------------------------------------------------------------------

class TestRmdValidation:
    def test_rmd_factors_strictly_decrease(self) -> None:
        from src.data.tax_rules.rmd import UNIFORM_LIFETIME
        from src.data.tax_rules.validator import validate_rmd_table
        issues = validate_rmd_table(UNIFORM_LIFETIME)
        assert issues == []

    def test_rmd_ascending_factors_detected(self) -> None:
        from src.data.tax_rules.validator import validate_rmd_table
        bad_table = {73: Decimal("10.0"), 74: Decimal("20.0")}  # ascending = bad
        issues = validate_rmd_table(bad_table)
        assert len(issues) > 0
