"""Plain-English narrative templates for decision rationales (Vanguard BETR framework)."""

from decimal import Decimal

from src.rationale.models import DecisionRationale

# Human-readable labels for ThresholdWarning.kind values.
# Fallback to raw kind when not in this map.
_WARNING_KIND_DISPLAY: dict[str, str] = {
    "irmaa_tier": "IRMAA",
    "niit": "NIIT (net investment income tax)",
    "ltcg_0_to_15": "LTCG 0%→15%",
    "salt_phase_down": "SALT phase-down",
}


def render_narrative(r: DecisionRationale, zero_reason: str | None = None) -> str:
    """Render a DecisionRationale as a plain-English narrative.

    The base narrative (before any warning sentences are appended) is
    guaranteed to be 2–4 sentences for a conversion year, or 1 sentence
    for a no-conversion year.  Warning sentences are appended after the base
    narrative, so the final string may exceed 4 sentences when warnings exist.

    Branch logic:
    1. If conversion year (r.conversion is not None): render conversion template
    2. Elif an RMD left no room in its bracket: render RMD template
    3. Elif the caller knows the reason: state it (and any RMD, as a fact)
    4. Else: render window/no-conversion template
    5. Append warnings as caution sentences

    Args:
        r: DecisionRationale with year, bracket, conversion, withdrawal, warnings

    Returns:
        Plain-English narrative string.  The base narrative is 2–4 sentences;
        additional caution sentences are appended for each warning.
    """

    rmd = "rmd" in r.withdrawal.order_used
    # Branch 1: Conversion year
    if r.conversion is not None:
        narrative = _render_conversion_narrative(r)
    # Branch 2: an RMD that leaves no room in its bracket. Only the recorded
    # sizing establishes that; an RMD year with room left is not explained by it.
    elif rmd and _rmd_fills_bracket(r) and zero_reason in (None, RULE_FOUND_NO_ROOM):
        narrative = _render_rmd_narrative(r)
    # Branch 3: the reason the caller knows from the strategy itself (it
    # converts nothing, has stopped, has not started, or its rule sized $0)
    elif zero_reason is not None:
        narrative = f"No Roth conversion this year: {zero_reason}." + _rmd_fact(r)
    elif rmd:
        narrative = "No Roth conversion this year." + _rmd_fact(r)
    # Branch 4: Zero-conversion outside window
    else:
        narrative = _render_window_closed_narrative(r)

    # Append warnings
    for warning in r.warnings:
        narrative += _render_warning_narrative(warning)

    return narrative


def _render_conversion_narrative(r: DecisionRationale) -> str:
    """Render narrative for a conversion year.

    Template:
    "Converted ${amount:,.0f} to Roth, filling the {rate:.0%} bracket to ${top:,.0f}
    (${remaining:,.0f} of headroom left). Each converted dollar cost {marginal:.1%} in
    tax now. Break-even future tax rate: {betr:.1%} — the no-conversion path projects a
    {projected:.0%} marginal rate once RMDs begin, so this conversion is {verdict}
    (Vanguard BETR framework, 2025)."
    """
    conv = r.conversion
    bracket = r.bracket

    action_id = conv.action_id
    amount = float(conv.amount)
    rate = bracket.bracket_rate        # marginal ordinary rate the year lands in
    rate_str = f"{rate:.0%}"
    marginal = conv.marginal_cost_rate  # actual incremental cost of conversion
    betr = conv.betr
    projected = conv.projected_future_marginal_rate
    verdict = conv.betr_verdict

    remaining = float(bracket.headroom_remaining)

    # Handle bracket_top being None (top bracket)
    if bracket.bracket_top is not None:
        top = float(bracket.bracket_top)
        top_phrase = f"${top:,.0f}"
        room_clause = f", with ${remaining:,.0f} of room left in the {rate_str} bracket"
    else:
        top_phrase = "the top bracket"
        room_clause = ""

    # The opening clause must describe the policy that was actually applied, not
    # infer intent from the bracket the year happens to land in. "fill_irmaa_tier"
    # sizes the conversion to the next IRMAA MAGI threshold and can stop well
    # short of filling the ordinary bracket; proportional policies (level_*,
    # max_pre_rmd) target a share of the IRA. Only the true bracket-fill actions
    # are described as "filling the X% bracket".
    if action_id == "fill_irmaa_tier":
        opening = (
            f"Converted ${amount:,.0f} to Roth, sized to stop just under the next "
            f"IRMAA tier. This lands your ordinary income at a {rate_str} marginal "
            f"rate{room_clause}."
        )
    elif action_id.startswith("fill_"):
        opening = (
            f"Converted ${amount:,.0f} to Roth, filling the {rate_str} bracket to "
            f"{top_phrase} (${remaining:,.0f} of headroom left)."
        )
    else:
        opening = (
            f"Converted ${amount:,.0f} to Roth. This lands your ordinary income at a "
            f"{rate_str} marginal rate{room_clause}."
        )

    # BETR is reported as a neutral single-year break-even figure, not a
    # favorable/unfavorable verdict: the per-year break-even routinely
    # disagrees with the winning strategy (which is chosen on lifetime totals),
    # so a judgment word here reads like a contradiction. `verdict` is left in
    # the data model for callers that still want it.
    _ = verdict
    narrative = (
        f"{opening} Each converted dollar cost {marginal:.1%} in tax now. "
        f"Single-year break-even rate: {betr:.1%} vs. a projected {projected:.0%} "
        f"future marginal rate once RMDs begin (Vanguard BETR framework, 2025). "
        f"This break-even prices one year in isolation; the winning strategy is "
        "chosen on lifetime totals — see Close alternatives for how this one "
        "stacks up."
    )

    return narrative


def _render_rmd_narrative(r: DecisionRationale) -> str:
    """Render narrative for zero-conversion with RMD in withdrawal order.

    Template:
    "No conversion this year: RMD of ${rmd:,.0f} plus other income already fills
    the {rate:.0%} bracket."
    """
    bracket = r.bracket
    rate = bracket.bracket_rate
    rmd = float(r.withdrawal.rmd_amount)

    narrative = (
        f"No conversion this year: RMD of ${rmd:,.0f} plus other income already fills the "
        f"{rate:.0%} bracket."
    )

    return narrative


def _rmd_fills_bracket(r: DecisionRationale) -> bool:
    """True when the year's income, RMD included, reaches its bracket's top."""
    return r.bracket.bracket_top is not None and r.bracket.headroom_remaining <= Decimal("1")


def _rmd_fact(r: DecisionRationale) -> str:
    """The year's RMD as a plain fact, with no claim that it caused anything."""
    if "rmd" not in r.withdrawal.order_used or r.withdrawal.rmd_amount <= 0:
        return ""
    return f" This year's required minimum distribution is ${float(r.withdrawal.rmd_amount):,.0f}."


def _render_window_closed_narrative(_r: DecisionRationale) -> str:
    """Render narrative for a zero-conversion year (no RMD involved).

    The generator cannot distinguish "conversion window closed" from "the
    optimizer evaluated conversions and $0 was the best choice" — both land
    here.  The text must only claim what is actually known.
    """
    return (
        "No Roth conversion this year: either the conversion window is closed, "
        "or converting offered no lifetime after-tax benefit (conversion "
        "strategies are always evaluated — see Alternative Policies)."
    )


def _render_warning_narrative(warning) -> str:
    """Render a single warning as a caution sentence.

    Template:
    " Caution: {consequence} — MAGI is ${distance:,.0f} below the {kind_label} threshold."
    (or "crossed the ... threshold" when distance < 0)
    """
    kind = warning.kind
    kind_label = _WARNING_KIND_DISPLAY.get(kind, kind)
    consequence = warning.consequence
    distance_decimal = warning.distance
    distance = abs(float(distance_decimal))

    # Determine "below" or "crossed" phrasing
    if distance_decimal > 0:
        narrative = (
            f" Caution: {consequence} — MAGI is ${distance:,.0f} below the "
            f"{kind_label} threshold."
        )
    else:
        narrative = (
            f" Caution: {consequence} — MAGI crossed the "
            f"{kind_label} threshold by ${distance:,.0f}."
        )

    return narrative


# A gap inside a rule strategy's schedule: the rule sized this year at $0.
# When the year's RMD left no bracket room, the RMD template names that cause.
RULE_FOUND_NO_ROOM = "the recommended strategy's rule found no room to convert this year"


def zero_conversion_reason(
    policy_id: str,
    year: int,
    first_conversion_year: int | None,
    last_conversion_year: int | None,
    traditional_before: Decimal,
) -> str:
    """Why the recommended strategy converts nothing in *year*.

    Only reasons that are known are stated: the strategy converts nothing,
    has not started, has stopped by design, or has nothing left to convert.
    """
    from src.optimization.search import thru_year_of

    if policy_id == "none":
        return "the recommended strategy makes no Roth conversions"
    if traditional_before <= Decimal("1"):
        return "nothing is left in traditional accounts to convert"
    if first_conversion_year is not None and year < first_conversion_year:
        return f"the recommended strategy starts converting in {first_conversion_year}"
    thru = thru_year_of(policy_id)
    if thru is not None and year > thru:
        return f"the recommended strategy converts only through {thru}"
    if last_conversion_year is not None and year > last_conversion_year:
        return f"the recommended strategy's last conversion is in {last_conversion_year}"
    return RULE_FOUND_NO_ROOM
