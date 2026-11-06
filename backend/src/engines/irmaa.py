"""IRMAA (Income-Related Monthly Adjustment Amount) calculator engine.

Calculates Medicare Part B and Part D premium surcharges based on Modified
Adjusted Gross Income (MAGI). The caller is responsible for providing the
2-year MAGI lookback (i.e., MAGI from premium_year - 2).
"""

from decimal import Decimal

from src.data.tax_rules.rules import TaxRules


class IRMAACalculator:
    """Calculate annual IRMAA surcharges above the standard Medicare premium.

    The surcharge is (Part B excess + Part D add-on) × 12 months × persons,
    quantized to cents. Tier selection uses <= comparison on magi_upper,
    creating a cliff effect at threshold boundaries.
    """

    def __init__(self, rules: TaxRules) -> None:
        """Initialize with TaxRules facade.

        Args:
            rules: TaxRules instance providing irmaa(premium_year) access.
        """
        self.rules = rules

    def annual_surcharge(
        self,
        magi: Decimal,
        filing_status: str,
        premium_year: int,
        persons_on_medicare: int,
        inflation: Decimal | None = None,
    ) -> Decimal:
        """Calculate annual IRMAA surcharge above the standard premium.

        Walks the IRMAA tiers for the given premium_year and filing_status,
        finding the FIRST tier where magi <= magi_upper (or the last tier
        if no tier matches). Computes the surcharge as:

            (tier.part_b_monthly - year.part_b_standard + tier.part_d_monthly)
            × 12 months × persons_on_medicare

        Args:
            magi: Modified Adjusted Gross Income (caller provides 2-year lookback).
            filing_status: 'single' or 'joint'.
            premium_year: Year for which premiums are being calculated.
            persons_on_medicare: Number of people on Medicare (typically 1 or 2).
            inflation: projects thresholds past the latest published premium
                year (see TaxRules.irmaa); None keeps the legacy clamp.

        Returns:
            Annual surcharge as Decimal, quantized to cents.
        """
        irmaa_year = self.rules.irmaa(premium_year, inflation)
        tiers = irmaa_year.tiers[filing_status]

        # Find the first tier where magi <= magi_upper (or use the last tier).
        selected_tier = tiers[-1]  # Default to the last tier
        for tier in tiers:
            if tier.magi_upper is None or magi <= tier.magi_upper:
                selected_tier = tier
                break

        # Calculate the monthly surcharge per person.
        part_b_excess = selected_tier.part_b_monthly - irmaa_year.part_b_standard
        monthly_surcharge_per_person = part_b_excess + selected_tier.part_d_monthly

        # Calculate annual surcharge for all persons and quantize to cents.
        annual_surcharge = (
            monthly_surcharge_per_person * 12 * persons_on_medicare
        ).quantize(Decimal("0.01"))

        return annual_surcharge
