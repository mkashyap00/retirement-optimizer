"""Decision rationale dataclasses.

Structures for articulating the reasoning behind specific tax optimization decisions:
- BracketFacts: summarizes the bracket situation in the year
- ThresholdWarning: detects proximity to phase-down thresholds
- ConversionRationale: justifies Roth conversion decisions with break-even analysis
- WithdrawalRationale: documents the withdrawal order and its justification
- DecisionRationale: the complete decision package for a single year
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BracketFacts:
    """Summary of marginal bracket position for a given year."""

    bracket_rate: Decimal  # marginal bracket the year ended in
    bracket_top: Decimal | None  # bracket ceiling (None if top bracket)
    headroom_used: Decimal  # conversion amount
    headroom_remaining: Decimal  # bracket_top - taxable_income (0 if top bracket)


@dataclass(frozen=True)
class ThresholdWarning:
    """Alert for proximity to or crossing of a phase-down or tax threshold."""

    kind: str  # "irmaa_tier" | "niit" | "ltcg_0_to_15" | "salt_phase_down"
    threshold: Decimal
    distance: Decimal  # threshold - magi (negative = crossed)
    consequence: str  # e.g. "Part B/D surcharge of $2,104.80/yr for this couple"


@dataclass(frozen=True)
class ConversionRationale:
    """Justification for a Roth conversion decision."""

    action_id: str  # "fill_22" etc.
    amount: Decimal
    target_description: str  # "fills the 22% bracket to $206,700"
    counterfactual_none_tax: Decimal  # this year's tax with zero conversion
    marginal_cost_rate: Decimal  # (tax_with - tax_without) / amount
    betr: Decimal  # break-even future tax rate (Plan 04 Task 8 compute_betr)
    projected_future_marginal_rate: Decimal  # max marginal rate on baseline path
    betr_verdict: str  # "favorable" | "marginal" (within 2pts) | "unfavorable"


@dataclass(frozen=True)
class WithdrawalRationale:
    """Justification for the withdrawal order."""

    order_used: list[str]  # e.g. ["rmd", "taxable", "traditional"]
    reason: str  # "taxable first: gains taxed at 0-15% vs 22% ordinary"
    rmd_amount: Decimal = Decimal("0")  # RMD taken this year (0 when no RMD)


@dataclass(frozen=True)
class DecisionRationale:
    """Complete decision package for a single year."""

    year: int
    age_self: int
    bracket: BracketFacts
    conversion: ConversionRationale | None  # None when conversion == 0
    withdrawal: WithdrawalRationale
    warnings: list[ThresholdWarning]
    narrative: str
