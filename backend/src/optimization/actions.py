"""Candidate Roth-conversion action generation at economic boundaries.

`generate_conversions` produces a deduplicated list of (action_id, amount)
tuples representing Roth conversion amounts worth evaluating for a given
simulation state.  The first element is always ("none", Decimal("0")).

Candidates (§NEW_SPEC §3.3):
  fill_10/12/22/24/32  — conversion that lands taxable ORDINARY income on
                         bracket.upper (root-found when ordinary income feeds
                         back on itself; see _bracket_fill_amount)
  fill_irmaa_tier      — room from baseline_magi to next IRMAA tier threshold
  level_25/50/100      — fraction × balance_traditional / _LEVEL_DRAW_YEARS
  max_pre_rmd          — balance_traditional / years until the RMD applicable
                         age (73 or 75 by birth cohort; below it only)

Filters (applied in order, drop unless noted as clamp):
  * amount ≤ 0 or < min_conversion                → drop
  * > balance_traditional or > max_conversion_per_year  → clamp, then re-check min
  * conversion_window blocks                      → drop all non-none
  * irmaa_policy "avoid"/"strict" + simulated MAGI
    crossing the next tier                        → drop
  * marginal_rate_limit exceeded                  → drop
  * duplicate amounts                              → keep first (by action_id order)
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from src.data.tax_rules.rmd import RMD_START_AGE, applicable_rmd_age
from src.engines.tax.capital_gains import net_capital_gains
from src.engines.tax.federal import FederalIncome
from src.optimization.state import Constraints, Engines, Settings, State
from src.optimization.transition import (
    _rmd_birth_year,
    household_rmds,
    simulate_year,
    taxable_social_security,
)

if TYPE_CHECKING:
    pass

_ZERO = Decimal("0")
_ONE = Decimal("1")

# Bracket-fill bisection, used only when the closed-form room overshoots the
# simulated year. It halves until the bracket is narrower than a dollar — below
# that the answer rounds away — with a cap so a pathological case cannot spin.
# Years where the closed form lands within the bracket pay one simulation.
_FILL_SOLVE_TOLERANCE = Decimal("1")
# level_25/50/100 take 25/50/100% of the IRA spread over this many years
# (5% / 10% / 20%). It was Settings.lookahead_years, the greedy window, until
# the greedy rollouts were removed; the level-dollar rules in search.py use the
# same shares.
_LEVEL_DRAW_YEARS = 5
_FILL_SOLVE_MAX_STEPS = 24

# Bracket rates we generate fill candidates for (skip 35 and 37).
_FILL_RATES: dict[Decimal, str] = {
    Decimal("0.10"): "fill_10",
    Decimal("0.12"): "fill_12",
    Decimal("0.22"): "fill_22",
    Decimal("0.24"): "fill_24",
    Decimal("0.32"): "fill_32",
}


def _irmaa_tiers_for_this_years_magi(state: State, engines: Engines, settings: Settings):
    """IRMAA tiers that this year's MAGI will be judged against: premium year
    ``state.year + 2``, projected at the plan's inflation once past the last
    published year. After a death the survivor files single and is judged on
    single thresholds; that filing status is the one this year's return uses."""
    year = engines.rules.irmaa(state.year + 2, settings.inflation)
    return year.tiers[state.filing_status]


def generate_conversions(
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    dedupe: bool = True,
    requested: dict[str, Decimal] | None = None,
    only: str | None = None,
) -> list[tuple[str, Decimal]]:
    """Return candidate (action_id, conversion_amount) pairs for one simulation year.

    The list always starts with ("none", Decimal("0")).  All other entries are
    Roth conversion amounts that sit at economically meaningful boundaries,
    filtered and clamped according to *constraints*.

    With *dedupe* (the default) each amount appears once, under the first id
    that produced it -- right for choosing among amounts. A caller sizing one
    NAMED rule passes ``dedupe=False``: when a cap makes two rules coincide,
    the later rule's own entry must still be there to find.

    *requested* adds caller-sized amounts (``{action_id: amount}``, e.g. a
    level-dollar rule's fixed amount). They pass through the same clamps,
    affordability cut and IRMAA / marginal-rate filters as every candidate, so
    the amount is a requested maximum, not a promise.

    *only* sizes just that action id (plus ``none``). Undeduplicated, each
    candidate is sized, clamped and filtered on its own, so its amount is the
    same as in the full list; a rule walk that reads one id skips sizing the
    others, which was most of the search's time (each bracket fill can take
    a bisection of simulated years).
    """
    # ── Step 1: baseline federal result (zero conversion) ────────────────────
    baseline_ordinary, baseline_income = _baseline_income(state, engines, settings)

    baseline_result = engines.federal.calculate(
        baseline_income,
        state.filing_status,
        state.year,
        state.age_self,
        state.age_spouse,
        inflation=settings.inflation,
    )
    baseline_magi: Decimal = baseline_result.agi

    # ── Step 2: build raw candidate list ─────────────────────────────────────
    candidates: list[tuple[str, Decimal]] = []

    # 2a. Bracket fill candidates
    #
    # A conversion is ordinary income, so bracket room has to be measured in
    # ORDINARY-income space: the conversion that lands taxable ordinary income
    # (ordinary − deduction) exactly on the bracket's upper edge.
    #
    # Not `bracket.upper − baseline_result.taxable_income`, for these reasons
    # (docs/OPTIMIZER_INTERNALS.md, "Bracket sizing"):
    #   * taxable_income includes qualified dividends and LTCG. Those stack
    #     ABOVE ordinary income and are taxed on the capital-gains schedule —
    #     they cannot occupy an ordinary bracket, so they must not consume it.
    #   * taxable_income floors at zero, silently discarding whatever deduction
    #     the baseline income did not use. A conversion can absorb that unused
    #     deduction before a cent of it is taxed, so the room starts at the
    #     deduction, not at zero.
    #   * the baseline leaves out the gains from the year's own sales (see
    #     _baseline_income), so in a year whose spending is funded by selling
    #     taxable assets it
    #     understates taxable Social Security — and the conversion then raises
    #     provisional income further, making still more of it taxable.
    #
    #   * the baseline knows nothing of the year's SPENDING withdrawals. Once the
    #     taxable account is empty, spending -- grossed up for its own tax and
    #     the conversion's -- comes out of the traditional IRA, and that is
    #     ordinary income in the same bracket ladder. Sized without it, "fill
    #     the 12% bracket every year" landed in the 24% bracket on the standard
    #     household from 2030.
    #
    # The first two are closed-form. The rest only show up once the year is
    # solved, so the closed-form room is treated as an upper bound and checked
    # against the simulated year; see _bracket_fill_amount.
    # The SAME projected table _compute_taxes will tax this year with.
    fy = engines.rules.federal(state.year, settings.inflation)
    baseline_deduction: Decimal = baseline_result.deduction_used
    for bracket in fy.brackets[state.filing_status]:
        label = _FILL_RATES.get(bracket.rate)
        if label is None or (only is not None and label != only):
            continue
        if bracket.upper is None:
            continue  # top bracket — no upper bound
        room = bracket.upper + baseline_deduction - baseline_ordinary
        if room <= _ZERO:
            continue
        room = _bracket_fill_amount(
            state, bracket.upper, room, engines, settings, constraints
        )
        if room > _ZERO:
            candidates.append((label, room))

    # IRMAA sizing must use MAGI *including* the capital gains realized to fund
    # spending — the gain-free baseline above understates MAGI whenever spending
    # is met by selling taxable assets, which made fill_irmaa_tier / Avoid
    # overshoot the tier. A zero-conversion simulate_year gives the true baseline
    # MAGI (gains, RMD, SS activation all included). Computed once, reused below.
    irmaa_active = _irmaa_in_view(state) or constraints.irmaa_policy in _TIER_POLICIES
    irmaa_baseline_magi = baseline_magi
    if irmaa_active:
        _, zero_ledger = simulate_year(state, _ZERO, engines, settings, constraints)
        irmaa_baseline_magi = zero_ledger.magi

    # 2b. IRMAA tier fill (activate when on Medicare or within 2-yr lookback window)
    #
    # This year's conversion raises THIS year's MAGI, which sets the premium
    # two years from now — so it is sized against that premium year's
    # thresholds. (This year's premium was already fixed by MAGI two years ago.)
    if _irmaa_in_view(state) and only in (None, "fill_irmaa_tier"):
        irmaa_tiers = _irmaa_tiers_for_this_years_magi(state, engines, settings)
        next_tier_upper = _next_irmaa_threshold(irmaa_baseline_magi, irmaa_tiers)
        if next_tier_upper is not None:
            # Root-find the conversion whose *simulated* MAGI lands just below the
            # tier: MAGI keeps rising past the conversion's face value because the
            # extra tax pulls more taxable sales (more realized gains), so a naive
            # (tier − baseline) sizing still crosses.
            irmaa_amount = _irmaa_fill_amount(
                state,
                next_tier_upper,
                irmaa_baseline_magi,
                engines,
                settings,
                constraints,
            )
            if irmaa_amount > _ZERO:
                candidates.append(("fill_irmaa_tier", irmaa_amount))

    # 2c. Level fractions of annual traditional draw
    annual_draw = state.balance_traditional / _LEVEL_DRAW_YEARS
    for label, frac in (
        ("level_25", Decimal("0.25")),
        ("level_50", Decimal("0.50")),
        ("level_100", _ONE),
    ):
        candidates.append((label, annual_draw * frac))

    # 2d. Max pre-RMD
    rmd_age = _rmd_start_age(state, settings)
    if state.age_self < rmd_age:
        years_until_rmd = max(1, rmd_age - state.age_self)
        candidates.append(("max_pre_rmd", state.balance_traditional / years_until_rmd))

    candidates.extend((requested or {}).items())

    # ── Step 3: window gate (blocks ALL non-none candidates) ─────────────────
    window_blocked = _window_blocks(state, settings, constraints.conversion_window)

    # ── Step 4: pre-compute IRMAA-avoid threshold ────────────────────────────
    irmaa_ceiling: Decimal | None = None
    if constraints.irmaa_policy in _TIER_POLICIES:
        irmaa_tiers = _irmaa_tiers_for_this_years_magi(state, engines, settings)
        irmaa_ceiling = _next_irmaa_threshold(irmaa_baseline_magi, irmaa_tiers)

    # ── Step 5: filter + clamp + deduplicate ─────────────────────────────────
    result: list[tuple[str, Decimal]] = [("none", _ZERO)]
    seen_amounts: set[Decimal] = set()
    baseline_shortfall: Decimal | None = None  # simulated once, on first need

    for action_id, raw_amount in candidates:
        if window_blocked:
            break  # all non-none candidates are skipped
        if only is not None and action_id != only:
            continue

        # Clamp to available balance and optional per-year cap
        amount = min(raw_amount, state.balance_traditional)
        if constraints.max_conversion_per_year is not None:
            amount = min(amount, constraints.max_conversion_per_year)

        # Drop if ≤ 0 or below minimum
        if amount <= _ZERO or amount < constraints.min_conversion:
            continue

        # Never convert money the year needs for spending. Spending is funded
        # from the Roth balance as it stood at the start of the year, so
        # converting IRA dollars that spending (or the conversion's own tax)
        # needs leaves the year short while the converted money sits in the
        # Roth -- a plan nobody would follow. Cut the conversion back to the
        # most the year can spare; drop it if that falls below the minimum.
        if baseline_shortfall is None:
            _, zero_year = simulate_year(state, _ZERO, engines, settings, constraints)
            baseline_shortfall = zero_year.shortfall
        amount = _affordable_conversion(
            state, amount, baseline_shortfall, engines, settings, constraints
        )
        if amount < constraints.min_conversion:
            continue

        # Avoid / Strict: drop a conversion whose year, as simulated, crosses
        # the next IRMAA tier. Baseline + conversion was not enough: the
        # conversion's tax is paid by selling more taxable stock, which
        # realizes more gains, so MAGI rises by more than the conversion. A
        # tier the baseline is already in cannot be avoided by not converting;
        # the guard is against the NEXT one.
        if irmaa_ceiling is not None:
            _, sim_ledger = simulate_year(state, amount, engines, settings, constraints)
            if sim_ledger.magi > irmaa_ceiling:
                continue

        # Marginal-rate limit, judged on the year as simulated -- spending
        # withdrawals, taxable Social Security and the senior deduction
        # included -- since the closed-form baseline misses all three and let
        # conversions through a 12% cap in years that landed in 24%. The rate
        # that matters is the one on the LAST dollar of ordinary income, not
        # the next dollar after it: those differ exactly when a conversion
        # fills a bracket to its edge, which is what fill_NN exists to do.
        if constraints.marginal_rate_limit is not None:
            _, sim_ledger = simulate_year(state, amount, engines, settings, constraints)
            last_rate = _last_dollar_rate(
                fy.brackets[state.filing_status], _taxable_ordinary(sim_ledger)
            )
            if last_rate > constraints.marginal_rate_limit:
                continue

        # Deduplicate by amount (keep first action_id)
        if dedupe and amount in seen_amounts:
            continue
        seen_amounts.add(amount)
        result.append((action_id, amount))

    return result


# ── Private helpers ───────────────────────────────────────────────────────────


def _baseline_income(
    state: State, engines: Engines, settings: Settings
) -> tuple[Decimal, FederalIncome]:
    """Compute (baseline_ordinary, FederalIncome) for a zero-conversion baseline.

    RMD is included, and so are gains already realized this year and losses
    carried in, netted as the year will net them. The gains from the year's
    own sales are not (they depend on the withdrawals the year solves for).
    Adding long-term gain never lowers the ordinary part of a netted result,
    so leaving them out keeps the room computed from this baseline an upper
    bound. Returns (baseline_ordinary, income) so callers can reuse ordinary
    for the marginal-rate check without recomputing it.
    """
    rmd = sum(household_rmds(state, settings, engines), _ZERO)

    # Pro-rata taxable fraction (Form 8606)
    if state.basis_traditional > _ZERO and state.balance_traditional > _ZERO:
        trad_taxable_frac = _ONE - state.basis_traditional / state.balance_traditional
    else:
        trad_taxable_frac = _ONE

    rmd_taxable = rmd * trad_taxable_frac

    non_ss_ordinary = (
        state.salary
        + state.pension
        + state.rental
        + state.interest
        + state.dividends_ordinary
        + rmd_taxable
    )
    gains = net_capital_gains(
        state.realized_st_gain - state.loss_carryover_st,
        state.realized_lt_gain - state.loss_carryover_lt,
    )
    non_ss_ordinary += gains.short_term - gains.loss_deduction
    # Provisional income: qualified dividends and long-term gains count too.
    other_for_ss = non_ss_ordinary + state.dividends_qualified + gains.long_term
    taxable_ss = taxable_social_security(state.social_security, other_for_ss, state.filing_status)

    baseline_ordinary = non_ss_ordinary + taxable_ss

    income = FederalIncome(
        ordinary=baseline_ordinary,
        ltcg=gains.long_term,
        qualified_dividends=state.dividends_qualified,
        investment_income=_ZERO,  # not needed for bracket/MAGI boundaries
    )
    return baseline_ordinary, income


def _last_dollar_rate(brackets, taxable_ordinary: Decimal) -> Decimal:
    """Statutory rate on the last dollar of *taxable_ordinary*.

    A bracket's upper edge belongs to that bracket: income landing exactly on
    the 12% top was taxed at 12% throughout. (The ledger's ``marginal_rate`` is
    the rate on the NEXT dollar, which there is already 22%.) Zero taxable
    income -- everything inside the deduction -- reads as the lowest rate.
    """
    last = taxable_ordinary - _ONE
    for bracket in brackets:
        if bracket.upper is None or last < bracket.upper:
            return bracket.rate
    return brackets[-1].rate


def _taxable_ordinary(ledger) -> Decimal:
    """Taxable ordinary income actually realized by a simulated year."""
    return ledger.audit["taxable_ordinary_income"]


def _bracket_fill_amount(
    state: State,
    bracket_upper: Decimal,
    closed_form_room: Decimal,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
) -> Decimal:
    """Largest conversion whose *simulated* taxable ordinary income stays at or
    below ``bracket_upper``.

    Taxable ordinary income rises at least dollar-for-dollar with the
    conversion -- faster once it pulls more Social Security into tax, phases
    out the senior deduction, or (with the taxable account empty) grosses up
    an IRA withdrawal to pay its own tax -- and the baseline behind
    ``closed_form_room`` misses the year's spending withdrawals entirely. So
    the closed form is an upper bound: simulate it once, keep it when it lands
    within the bracket (the common case, one simulation), and bisect over
    [0, room] only when it overshoots. Returns 0 when even a zero conversion is
    already over the edge, which correctly drops the candidate.
    """
    _, at_room = simulate_year(state, closed_form_room, engines, settings, constraints)
    if _taxable_ordinary(at_room) <= bracket_upper:
        return closed_form_room

    lo = _ZERO
    hi = closed_form_room
    best = _ZERO
    for _ in range(_FILL_SOLVE_MAX_STEPS):
        if hi - lo <= _FILL_SOLVE_TOLERANCE:
            break
        mid = (lo + hi) / 2
        _, sim_ledger = simulate_year(state, mid, engines, settings, constraints)
        if _taxable_ordinary(sim_ledger) <= bracket_upper:
            best = mid
            lo = mid
        else:
            hi = mid
    return best


def _affordable_conversion(
    state: State,
    amount: Decimal,
    baseline_shortfall: Decimal,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
) -> Decimal:
    """Largest conversion up to *amount* that leaves the year no shorter of
    spending money than converting nothing does.

    The shortfall can only grow with the conversion (it consumes IRA dollars
    and adds tax), so if *amount* is affordable it is returned unchanged --
    the common case, one simulation -- and otherwise a bisection over
    [0, amount] finds the edge to within a dollar.
    """
    limit = baseline_shortfall + _ONE
    _, at_amount = simulate_year(state, amount, engines, settings, constraints)
    if at_amount.shortfall <= limit:
        return amount

    lo = _ZERO
    hi = amount
    for _ in range(_FILL_SOLVE_MAX_STEPS):
        if hi - lo <= _FILL_SOLVE_TOLERANCE:
            break
        mid = (lo + hi) / 2
        _, sim_ledger = simulate_year(state, mid, engines, settings, constraints)
        if sim_ledger.shortfall <= limit:
            lo = mid
        else:
            hi = mid
    return lo


def _irmaa_fill_amount(
    state: State,
    threshold: Decimal,
    zero_magi: Decimal,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
) -> Decimal:
    """Largest conversion whose *simulated* MAGI stays at/below ``threshold``.

    Simulated MAGI rises monotonically with the conversion — the conversion is
    ordinary income, and the extra tax it triggers pulls more taxable sales,
    realizing more capital gains — so a plain ``threshold − baseline`` sizing
    still crosses the tier. Since MAGI(C) ≥ zero_magi + C, the answer is bounded
    above by ``threshold − 1 − zero_magi``; a short binary search over that
    range converges to a few hundred dollars. Returns 0 if a zero conversion is
    already at/above the tier.
    """
    target = threshold - _ONE
    if zero_magi >= target:
        return _ZERO

    lo = _ZERO
    hi = target - zero_magi  # true amount cannot exceed this
    best = _ZERO
    for _ in range(7):
        mid = (lo + hi) / 2
        _, sim_ledger = simulate_year(state, mid, engines, settings, constraints)
        if sim_ledger.magi <= target:
            best = mid
            lo = mid
        else:
            hi = mid
    return best


def _next_irmaa_threshold(
    baseline_magi: Decimal,
    tiers: list,
) -> Decimal | None:
    """Return the magi_upper of the first tier whose magi_upper > baseline_magi.

    Returns None if all tiers have magi_upper=None (top tier) or baseline is
    already in the highest explicit tier.
    """
    for tier in tiers:
        if tier.magi_upper is not None and tier.magi_upper > baseline_magi:
            return tier.magi_upper
    return None


# Policies that keep a conversion below the next IRMAA tier. Strict promised
# "stay below whenever possible"; converting nothing always is possible, so it
# is the same rule as Avoid. Ignore and Soft both count the surcharge as a cost
# and let the objective decide whether crossing is worth it.
_TIER_POLICIES = ("strict", "avoid")


def _irmaa_in_view(state: State) -> bool:
    """Either spouse on Medicare now, or within the two-year MAGI look-back
    of it (63+). Self alone missed an older spouse's surcharge."""
    return (
        state.medicare_self
        or state.medicare_spouse
        or state.age_self >= 63
        or (state.age_spouse is not None and state.age_spouse >= 63)
    )


def _rmd_start_age(state: State, settings: Settings) -> int:
    """The age RMDs begin for this year's account owner.

    The same SECURE 2.0 cohort rule the RMD engine applies (73 for 1951-1959,
    75 for 1960+), read from the same birth year, so "before RMDs" here means
    exactly the years the engine takes none. Without a birth year it falls back
    to the legacy flat 73, as the engine does.
    """
    birth_year = _rmd_birth_year(state, settings)
    return RMD_START_AGE if birth_year is None else applicable_rmd_age(birth_year)


def _window_blocks(state: State, settings: Settings, window: str) -> bool:
    """Return True when the conversion_window constraint blocks all conversions."""
    if window == "pre_medicare" and state.medicare_self:
        return True
    if window == "pre_rmd" and state.age_self >= _rmd_start_age(state, settings):
        return True
    if window == "pre_ss" and state.social_security > _ZERO:
        return True
    return False
