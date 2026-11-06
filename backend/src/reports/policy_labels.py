"""Human-readable names for optimizer policy ids.

Mirror of the frontend map in
frontend/src/components/results/AlternativesTable.tsx — keep in sync.
"""

from __future__ import annotations

import re

_THRU_RE = re.compile(r"^fill_(?P<rate>\d+)_thru_(?P<year>\d{4})$")
_LEVEL_RE = re.compile(r"^level_(?P<pct>\d+)pct_(?:annual|thru_(?P<year>\d{4}))$")

POLICY_LABELS: dict[str, str] = {
    "none": "No conversions",
    # Consistent-rule policies: fill the bracket EVERY year across the horizon.
    # These were missing here, so an exported "every year" winner showed its
    # raw id while the Results page showed its name.
    "fill_10_annual": "Fill the 10% bracket every year",
    "fill_12_annual": "Fill the 12% bracket every year",
    "fill_22_annual": "Fill the 22% bracket every year",
    "fill_24_annual": "Fill the 24% bracket every year",
    "fill_32_annual": "Fill the 32% bracket every year",
}

# Greedy-rollout policies, removed from the search in October 2026. Runs saved
# before then still carry these ids, and their exports must still read.
LEGACY_POLICY_LABELS: dict[str, str] = {
    "defer_1yr": "Skip year 1, then convert (greedy)",
    "fill_10": "Fill the 10% bracket (greedy)",
    "fill_12": "Fill the 12% bracket (greedy)",
    "fill_22": "Fill the 22% bracket (greedy)",
    "fill_24": "Fill the 24% bracket (greedy)",
    "fill_irmaa_tier": "Fill to next IRMAA tier (greedy)",
    "level_25": "Convert ~5% of the IRA (greedy)",
    "level_50": "Convert ~10% of the IRA (greedy)",
    "level_100": "Convert ~20% of the IRA (greedy)",
    "max_pre_rmd": "Spread IRA evenly before RMDs (greedy)",
}


def level_amount(policy_id: str, start_traditional: float | None) -> float | None:
    """The yearly amount a level-dollar rule asks for: its share of the
    traditional balance at the start, computed once (search._LEVEL_RULES)."""
    m = _LEVEL_RE.match(policy_id)
    if not m or start_traditional is None:
        return None
    return int(m.group("pct")) / 100 * start_traditional


def policy_label(policy_id: str, start_traditional: float | None = None) -> str:
    """Return the display name for a policy id (id itself when unknown).

    Limited-duration rules (``fill_22_thru_2031``) and level-dollar rules
    (``level_5pct_annual``, ``level_5pct_thru_2029``) are named from the id,
    since their years depend on the household. With the starting traditional
    balance (``result["starting_traditional_balance"]``) a level-dollar rule
    is named by its dollar amount; runs saved before that field keep the
    percentage.
    """
    m = _THRU_RE.match(policy_id)
    if m:
        return f"Fill the {m.group('rate')}% bracket through {m.group('year')}"
    m = _LEVEL_RE.match(policy_id)
    if m:
        amount = level_amount(policy_id, start_traditional)
        if amount is not None:
            when = f" through {m.group('year')}" if m.group("year") else ""
            return f"Convert up to ${amount:,.0f} annually{when}"
        when = f"each year through {m.group('year')}" if m.group("year") else "every year"
        return f"Convert up to {m.group('pct')}% of the starting IRA {when}"
    return POLICY_LABELS.get(policy_id) or LEGACY_POLICY_LABELS.get(policy_id, policy_id)
