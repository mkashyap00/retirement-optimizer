"""Pure single-year transition function for the retirement optimizer.

`simulate_year` advances the simulation by exactly one year using ONLY the real
tax/benefit engines (federal, state, IRMAA, RMD). It is deterministic: no DB, no
`datetime.now()`, no random. Given a `State`, a Roth-conversion amount, the
engine bundle, `Settings` and `Constraints`, it SOLVES the year's discretionary
withdrawals internally (via a tax<->withdrawal fixed point) and returns the next
`State` plus a fully-populated `YearLedger`.

A year that cannot fund required spending is NOT a failure to report upward: it
spends every dollar it can reach and records what is left unmet in
`ledger.shortfall`. Callers detect underfunding with `ledger.shortfall > 0`
rather than a `None` return. Charging a partly-funded year in full was worth
$160k-265k of objective in testing.

Critical semantics (the v2 regression list this rebuild exists to prevent):
  * Roth withdrawals are NEVER taxable income (but ARE spendable cash).
  * Taxable-account sales realize gains only on the gain fraction.
  * Pro-rata rule (Form 8606) for traditional distributions when basis > 0.
  * Federal taxable Social Security via the provisional-income two-tier formula.
  * The STATE engine receives GROSS Social Security (it exempts SS internally).
"""
from __future__ import annotations

import dataclasses
from decimal import ROUND_HALF_UP, Decimal

from src.data.tax_rules.social_security import (
    full_retirement_age,
    survivor_full_retirement_age,
)
from src.engines.social_security import SocialSecurityCalculator
from src.engines.tax.capital_gains import (
    LOSS_DEDUCTION_LIMIT,
    NetGains,
    loss_carryover,
    net_capital_gains,
    state_loss_rule,
)
from src.engines.tax.federal import FederalIncome
from src.engines.tax.state import StateIncome
from src.optimization.state import (
    Constraints,
    Engines,
    Settings,
    State,
    YearLedger,
    resolve_income,
)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")

# Below this, an apparent funding gap is the fixed point's own convergence
# residue rather than a real shortfall. See the shortfall block in simulate_year.
_FUNDING_TOLERANCE = Decimal("1")

# Iteration cap for the tax<->withdrawal fixed point in simulate_year.
#
# Picard iteration, converging because the map is a contraction whose factor IS
# the effective marginal rate r on the funding dollar: a withdrawal raised by D
# raises tax by r*D, so the error after each pass is r times the error before.
# It starts from a zero tax estimate, so the opening error e0 is the WHOLE tax
# bill:
#
#     e_n = r^n * e0      =>      n >= log(eps / e0) / log(r)
#
# A $500k conversion funded partly from a traditional IRA in a high-tax state
# contracts at r ~ 0.443 against e0 ~ 226k, which the formula puts at ~21
# passes to reach the $0.01 the loop exits on. MEASURED: 26 — the estimate runs
# low because r is not constant over the first few passes (~0.49 before it
# settles). 60 leaves ~2.3x headroom over that.
#
# A cap that stops short leaves a residual that lands in `net_spendable` and is
# reported as an unfunded year: it flips `feasible` for the whole path and stops
# _build_rule_schedule early. This is not a tolerance widened to hide a gap;
# _FUNDING_TOLERANCE stays at $1, and the early exit means a year that converges
# in two passes still takes two. Why the old cap of 12 failed:
# docs/OPTIMIZER_HISTORY.md, "The funding-solver iteration cap".
_FUNDING_SOLVE_MAX_ITERATIONS = 60

# Provisional-income thresholds for taxability of Social Security benefits.
# (base threshold, additional threshold)
_SS_THRESHOLDS = {
    "single": (Decimal("25000"), Decimal("34000")),
    "joint": (Decimal("32000"), Decimal("44000")),
}


def taxable_social_security(
    ss: Decimal, other_ordinary: Decimal, filing_status: str
) -> Decimal:
    """Federally taxable portion of Social Security via provisional-income rules.

    provisional = other_income + tax_exempt_interest(0 here) + 0.5 * ss
      * below the first threshold t1        -> 0 taxable
      * between t1 and t2                    -> min(0.5*(prov - t1), 0.5*ss)
      * above the second threshold t2        -> min(0.85*(prov - t2)
                                                    + min(0.5*(t2 - t1), 0.5*ss),
                                                    0.85*ss)
    Result never exceeds 85% of benefits.
    """
    if ss <= 0:
        return _ZERO
    t1, t2 = _SS_THRESHOLDS[filing_status]
    provisional = other_ordinary + Decimal("0.5") * ss
    if provisional <= t1:
        return _ZERO
    if provisional <= t2:
        return min(Decimal("0.5") * (provisional - t1), Decimal("0.5") * ss)
    tier1 = min(Decimal("0.5") * (t2 - t1), Decimal("0.5") * ss)
    return min(Decimal("0.85") * (provisional - t2) + tier1, Decimal("0.85") * ss)


def _q(value: Decimal) -> Decimal:
    """Quantize to cents, ROUND_HALF_UP."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def ss_cola_factor(settings: Settings, year: int | None) -> Decimal:
    """Cumulative Social Security COLA from ``settings.start_year`` to *year*.

    PIAs are start-year dollars. Anchored to ``start_year`` — never to the
    year a schedule or a remaining-horizon evaluation happens to begin — so
    every call for the same calendar year sees the same factor. The rate is
    ``settings.ss_cola`` when set, otherwise ``settings.inflation`` floored at
    zero. ``year=None`` means start-year dollars (factor 1).
    """
    if year is None:
        return _ONE
    n = year - settings.start_year
    if n <= 0:
        return _ONE
    rate = settings.ss_cola if settings.ss_cola is not None else max(_ZERO, settings.inflation)
    if rate == _ZERO:
        return _ONE
    return (_ONE + rate) ** n


def _annual_survivor_social_security(
    ss: SocialSecurityCalculator, settings: Settings, survivor_age: int, factor: Decimal
) -> Decimal:
    """Household SS after the first death: ONE benefit, the larger of the two.

    This is the arithmetic heart of the widow's penalty. Household income drops
    by the smaller benefit while the survivor moves to single brackets and a
    single standard deduction, usually while the RMDs carry on undiminished.

    Any spousal top-up from `_annual_social_security` ends here — it is
    *replaced* by the survivor benefit, never stacked on top of it.

    *factor* is this year's cumulative COLA (``ss_cola_factor``); both PIAs are
    indexed by it before the calculator's own rounding.
    """
    if settings.first_death_is_spouse:
        own_pia, own_claim = settings.ss_pia_self, settings.ss_claim_age_self
        dec_pia, dec_claim = settings.ss_pia_spouse, settings.ss_claim_age_spouse
        own_birth_year, dec_birth_year = settings.birth_year_self, settings.birth_year_spouse
    else:
        own_pia, own_claim = settings.ss_pia_spouse, settings.ss_claim_age_spouse
        dec_pia, dec_claim = settings.ss_pia_self, settings.ss_claim_age_self
        own_birth_year, dec_birth_year = settings.birth_year_spouse, settings.birth_year_self

    own_monthly = _ZERO
    if own_pia is not None and own_claim is not None and survivor_age >= own_claim:
        own_monthly = ss.monthly_benefit(
            own_pia * factor, own_claim, full_retirement_age(own_birth_year)
        )

    if dec_pia is None or dec_claim is None:
        return own_monthly * 12

    # Which of the deceased's benefits the survivor inherits — see
    # SocialSecurityCalculator.survivor_basis_claim_age. A worker who planned to
    # claim at 70 but died at 62 earns no delayed credits, and crediting them
    # would understate exactly the penalty this feature exists to expose.
    age_at_death = (
        settings.first_death_year - dec_birth_year
        if dec_birth_year is not None and settings.first_death_year is not None
        else None
    )
    dec_fra = full_retirement_age(dec_birth_year)
    basis_age = ss.survivor_basis_claim_age(dec_claim, age_at_death, dec_fra)
    dec_monthly = ss.monthly_benefit(dec_pia * factor, basis_age, dec_fra)

    return ss.survivor_benefit(
        own_monthly, dec_monthly, survivor_age, survivor_full_retirement_age(own_birth_year)
    ) * 12


def _rmd_birth_year(state: State, settings: Settings) -> int | None:
    """Birth year driving this year's SECURE 2.0 RMD applicable age.

    Normally the account owner's. But once SELF has died and the spouse
    survives, the rolled-over IRA is the SURVIVOR's, so their cohort decides
    when distributions start. The applicable age turns on the 1959/1960
    boundary (73 vs 75) — reading the wrong person's birth year there is worth
    two full years of forced distributions, and every tax figure that follows.
    """
    if (
        settings.first_death_year is not None
        and not settings.first_death_is_spouse
        and state.year > settings.first_death_year
        and settings.birth_year_spouse is not None
    ):
        return settings.birth_year_spouse
    return settings.birth_year_self


def household_rmds(
    state: State, settings: Settings, engines: Engines
) -> tuple[Decimal, Decimal]:
    """This year's RMDs as (self's IRA, spouse's IRA).

    Each owner's balance over the factor for that owner's age, from that
    owner's SECURE 2.0 applicable age. One factor on the household total, at
    self's age, overstated the RMD when the spouse is younger and missed it
    entirely when the spouse is older.
    """
    spouse_bal = state.balance_traditional_spouse if state.age_spouse is not None else _ZERO
    rmd_self = engines.rmd.calculate(
        state.balance_traditional - spouse_bal, state.age_self,
        _rmd_birth_year(state, settings),
    )
    rmd_spouse = (
        engines.rmd.calculate(spouse_bal, state.age_spouse, settings.birth_year_spouse)
        if spouse_bal > _ZERO
        else _ZERO
    )
    return rmd_self, rmd_spouse


def _annual_social_security(
    engines: Engines,
    settings: Settings,
    age_self: int,
    age_spouse: int | None,
    widowed: bool = False,
    *,
    year: int | None = None,
) -> Decimal | None:
    """Household SS benefit for a year at the given ages (engine wrapper)."""
    return household_social_security(
        engines.ss, settings, age_self, age_spouse, year, widowed=widowed
    )


def household_social_security(
    ss: SocialSecurityCalculator,
    settings: Settings,
    age_self: int,
    age_spouse: int | None,
    year: int | None,
    *,
    widowed: bool = False,
) -> Decimal | None:
    """Household SS benefit for calendar *year* at the given ages, from Settings.

    Benefits activate the year a person reaches their claim age. Every PIA is
    multiplied by ``ss_cola_factor(settings, year)`` before the calculator
    applies its reductions, credits and cent rounding, so early, delayed,
    spousal and survivor amounts all carry the same COLA exactly once.
    Returns None when Settings carries no claiming config at all; callers then
    fall back to the legacy behavior of carrying ``State.social_security``
    forward unchanged. Pure: shared by the simulator and input assembly.

    **Spousal benefit.** The lower-PIA spouse receives their own adjusted
    benefit PLUS the spousal excess — half the primary's PIA over their own
    unreduced PIA — reduced for the months before FRA at which spousal
    entitlement began (see ``spousal_benefit``). Computing each person's
    benefit in isolation lost the excess entirely. Two SSA rules the wiring has
    to respect:

      * The top-up cannot begin until the **primary has filed**. "File and
        suspend" was eliminated by the Bipartisan Budget Act of 2015, so a
        spouse cannot draw on a record the worker has not claimed. A couple
        where the lower earner claims at 62 and the higher earner waits until
        70 therefore gets own-benefit-only for those eight years.
      * The spousal half is 50% of the primary's **PIA**, never of their
        delayed-credit-boosted benefit — delaying past FRA raises your own
        cheque, not your spouse's. ``spousal_benefit`` already has this right.

    Spousal entitlement begins at the later of the recipient's own claim and
    the primary's filing (deemed filing ties the two together for anyone born
    after 1/1/1954), so a spouse topped up years after claiming early has the
    excess reduced only for the months still short of FRA at that point.
    """
    if settings.ss_pia_self is None and settings.ss_pia_spouse is None:
        return None

    factor = ss_cola_factor(settings, year)
    if widowed:
        return _annual_survivor_social_security(ss, settings, age_self, factor)

    # (label, pia, claim_age, age this year, FRA) for each person configured.
    # FRA comes from the person's birth year: 67 only for 1960 and later.
    people: list[tuple[str, Decimal, int, int, Decimal]] = []
    if settings.ss_pia_self is not None and settings.ss_claim_age_self is not None:
        people.append(
            ("self", settings.ss_pia_self * factor, settings.ss_claim_age_self, age_self,
             full_retirement_age(settings.birth_year_self))
        )
    if (
        settings.ss_pia_spouse is not None
        and settings.ss_claim_age_spouse is not None
        and age_spouse is not None
    ):
        people.append(
            ("spouse", settings.ss_pia_spouse * factor, settings.ss_claim_age_spouse, age_spouse,
             full_retirement_age(settings.birth_year_spouse))
        )
    if not people:
        return _ZERO

    # The primary is the higher PIA; the other is the one eligible for a top-up.
    # On a tie the top-up is worthless anyway (half your own PIA never beats
    # your own benefit), so which one wins the max() does not matter.
    primary_label, primary_pia, primary_claim_age, primary_age, _ = max(
        people, key=lambda p: p[1]
    )
    primary_has_filed = primary_age >= primary_claim_age
    # Years since the primary filed; the recipient was that much younger then.
    years_since_primary_filed = primary_age - primary_claim_age

    total = _ZERO
    for label, pia, claim_age, age_now, fra in people:
        if age_now < claim_age:
            continue  # has not claimed yet
        if label != primary_label and primary_has_filed:
            monthly = ss.spousal_benefit(
                pia, primary_pia, claim_age, fra,
                spousal_start_age=age_now - years_since_primary_filed,
            )
        else:
            monthly = ss.monthly_benefit(pia, claim_age, fra)
        total += monthly * 12
    return total


def simulate_year(
    state: State,
    conversion: Decimal,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
) -> tuple[State, YearLedger]:
    """Advance one simulation year; return (next_state, ledger).

    Always succeeds. When withdrawals cannot cover required spending plus the
    taxes triggered by the requested conversion, the year drains what it can
    and reports the unmet amount as ``ledger.shortfall`` (0 on a funded year).
    """
    conversion = max(_ZERO, conversion)

    # --- Step 0: Social Security for THIS year's ages -------------------------
    # With claiming config in Settings, benefits switch on the year each
    # person reaches their claim age.  (Without config, the pre-set
    # State.social_security is used as-is — legacy behavior.)
    # After the first death this must be the SURVIVOR benefit: recomputing as
    # if both were alive discarded what the death transition carried in, and
    # paid the survivor off whichever record sat in the `self` slot.
    widowed_now = (
        settings.first_death_year is not None and state.year > settings.first_death_year
    )
    ss_now = _annual_social_security(
        engines, settings, state.age_self, state.age_spouse, widowed=widowed_now,
        year=state.year,
    )
    if ss_now is not None and ss_now != state.social_security:
        state = dataclasses.replace(state, social_security=ss_now)

    # --- Step 1: mandatory RMD from the traditional account ------------------
    rmd_self, rmd_spouse = household_rmds(state, settings, engines)
    rmd = rmd_self + rmd_spouse

    # A conversion can only draw what remains after the mandatory RMD, so an
    # oversized request converts what is actually there. Clamping rather than
    # failing matters under Monte Carlo: a schedule sized on the deterministic
    # balance can outrun a path where markets fell, and refusing the year would
    # score a market drop as a plan failure.
    conversion = min(conversion, max(_ZERO, state.balance_traditional - rmd))

    # --- Fixed once for the year --------------------------------------------
    # Pro-rata (Form 8606) taxable fraction of every traditional distribution.
    if state.basis_traditional > 0 and state.balance_traditional > 0:
        trad_taxable_frac = _ONE_MINUS(state.basis_traditional, state.balance_traditional)
    else:
        trad_taxable_frac = Decimal("1")

    # Gain fraction realized on a taxable-account sale, and the share of each
    # dollar sold that is basis. An account at a loss (basis above value) has
    # a basis share above 1. Its sales would realize a loss, but the plan's own
    # sales are floored at zero gain: an aggregate basis cannot say which lots
    # a sale draws on, and a zero floor keeps the closed-form bracket room in
    # actions.py an upper bound. Losses the household ENTERED (already
    # realized, or carried over) are netted in full; see capital_gains.py.
    if state.balance_taxable > 0:
        basis_share = state.basis_taxable / state.balance_taxable
        gain_fraction = max(_ZERO, _ONE - basis_share)
    else:
        basis_share = _ONE
        gain_fraction = _ZERO

    # Cash income that is spendable BEFORE any discretionary withdrawal.
    # (All of SS is cash; only a portion is taxable.)
    fixed_cash = (
        state.salary
        + state.pension
        + state.rental
        + state.social_security
        + state.interest
        + state.dividends_qualified
        + state.dividends_ordinary
    )

    # Inflated spending for this year: the target the user asked for, and what
    # the spending rule actually allows the plan to attempt. Identical under
    # the default "fixed" rule.
    years_elapsed = state.year - settings.start_year
    inflator = (Decimal("1") + settings.inflation) ** years_elapsed
    target_spending = settings.required_spending * inflator
    required_spending, next_spending_base, initial_rate = _apply_spending_rule(
        state, settings, fixed_cash, inflator, target_spending
    )
    # (The cut itself is derived at ledger time from the quantised pair, so the
    # table's `target - required == cut` holds to the cent.)

    # Discretionary capacity of each source.
    avail_taxable = state.balance_taxable
    avail_traditional = state.balance_traditional - rmd - conversion  # >= 0 (checked)

    # Roth 5-year rule is NOT modelled as a hard withdrawal block: Roth
    # contributions and converted principal remain accessible, and blocking
    # the whole balance would manufacture artificial shortfalls. The 5-year
    # situation is surfaced to the user as a warning in run_optimization
    # (see optimizer.py) using roth_earliest_opened_year instead.
    avail_roth = state.balance_roth

    # Withdrawal fill order: taxable -> traditional -> roth,
    # swapping the first two when preserving the taxable account is requested.
    if constraints.preserve_taxable:
        order = ("traditional", "taxable", "roth")
    else:
        order = ("taxable", "traditional", "roth")
    caps = {"taxable": avail_taxable, "traditional": avail_traditional, "roth": avail_roth}

    def _solve(need: Decimal) -> dict:
        """Fill `need` dollars of cash from the ordered sources."""
        remaining = max(_ZERO, need)
        w = {"taxable": _ZERO, "traditional": _ZERO, "roth": _ZERO}
        for src in order:
            take = min(remaining, caps[src])
            if take < 0:
                take = _ZERO
            w[src] = take
            remaining -= take
        w["unfunded"] = remaining
        return w

    # --- Step 2 & 3: tax<->withdrawal fixed point ----------------------------
    # The brief specifies a 3-iteration fixed point. Because the residual after
    # a fixed iteration count can exceed $1 in high-tax years (each iteration
    # only shrinks the gap by the effective marginal rate), we iterate to tax
    # convergence so the funding invariant net_spendable >= required-1 always
    # holds. Passes vary far more than "a handful": measured medians run from 2
    # (no conversions) to 14 (a greedy policy late in the horizon), with 26 the
    # worst seen. See _FUNDING_SOLVE_MAX_ITERATIONS for why the cap is 60.
    # Gains already realized this year and losses carried in are fixed; the
    # plan's own sales add long-term gain on top, so the year is netted again
    # on every pass.
    # The state keeps the federal result, or nets the same gains again: with
    # its own carryover, or with no loss allowed against other income.
    entered_st = state.realized_st_gain - state.loss_carryover_st
    entered_lt = state.realized_lt_gain - state.loss_carryover_lt
    state_rule = state_loss_rule(state.state_code)
    state_limit = LOSS_DEDUCTION_LIMIT if state_rule == "separate" else _ZERO
    state_entered_st, state_entered_lt = state.realized_st_gain, state.realized_lt_gain
    if state_rule == "separate":
        state_entered_st -= state.state_loss_carryover_st
        state_entered_lt -= state.state_loss_carryover_lt
    tax_estimate = _ZERO
    result: dict = {}
    for _ in range(_FUNDING_SOLVE_MAX_ITERATIONS):
        need = required_spending - (fixed_cash + rmd) + tax_estimate
        w = _solve(need)
        realized_gains = w["taxable"] * gain_fraction
        gains = net_capital_gains(entered_st, entered_lt + realized_gains)
        state_gains = gains if state_rule == "federal" else net_capital_gains(
            state_entered_st, state_entered_lt + realized_gains, state_limit)

        (federal_res, state_tax, irmaa, taxable_ss, trad_taxable_ordinary,
         state_income) = _compute_taxes(
            state, engines, constraints, rmd, conversion, w, gains, state_gains,
            trad_taxable_frac, settings.inflation,
        )
        new_tax = federal_res.total_tax + state_tax + irmaa
        result = {
            "w": w,
            "realized_gains": realized_gains,
            "gains": gains,
            "state_gains": state_gains,
            "state_income": state_income,
            "federal": federal_res,
            "state_tax": state_tax,
            "irmaa": irmaa,
            "total_tax": new_tax,
            "taxable_ss": taxable_ss,
            "trad_taxable_ordinary": trad_taxable_ordinary,
        }
        if abs(new_tax - tax_estimate) < _CENTS:
            tax_estimate = new_tax
            break
        tax_estimate = new_tax

    w = result["w"]
    total_tax = result["total_tax"]
    federal_res = result["federal"]
    realized_gains = result["realized_gains"]
    gains = result["gains"]
    carry_st, carry_lt = loss_carryover(gains, federal_res.agi, federal_res.deduction_used)
    state_gains = result["state_gains"]
    if state_rule == "federal":
        state_carry_st, state_carry_lt = carry_st, carry_lt
    elif state_rule == "separate":
        state_carry_st, state_carry_lt = loss_carryover(
            state_gains,
            engines.state.gross_income(result["state_income"], state.state_code),
            engines.state.rules.state_standard_deduction(
                state.state_code, state.filing_status, state.year, settings.inflation),
        )
    else:
        state_carry_st = state_carry_lt = _ZERO

    withdrawals_total = w["taxable"] + w["traditional"] + w["roth"]
    net_spendable = fixed_cash + rmd + withdrawals_total - total_tax

    # --- Step 5: shortfall ---------------------------------------------------
    # What the household could not fund this year, after spending every dollar
    # it can reach. When the caps bind, `_solve` has drained all three accounts,
    # so net_spendable == required_spending - w["unfunded"] and this gap IS the
    # unfunded amount; when they do not bind, the gap is zero by construction.
    #
    # The $1 floor is the fixed point's own tolerance, not a fudge: the
    # tax<->withdrawal loop converges to within cents, so a sub-dollar gap is
    # arithmetic residue. Reporting it as shortfall would mark every funded year
    # underfunded.
    #
    # net_spendable can go NEGATIVE when the tax on a large conversion exceeds
    # every liquid dollar. The liability is real and the shortfall grows by it —
    # we do not silently forgive the unpayable part of a tax bill.
    gap = required_spending - net_spendable
    shortfall = gap if gap > _FUNDING_TOLERANCE else _ZERO

    # The mirror case: cash income (salary, an RMD larger than the spending)
    # that the year neither spends nor pays in tax. It is saved to the taxable
    # account, at full basis — it is cash, so a later sale realizes no gain on
    # it. Leaving it out lost every working year's surplus and made converting
    # look free in such years: the conversion tax came out of money that was
    # about to vanish anyway. Same $1 residue floor as the shortfall above.
    surplus = -gap if -gap > _FUNDING_TOLERANCE else _ZERO

    # --- Step 6: balance updates, then growth --------------------------------
    trad_distributions = rmd + conversion + w["traditional"]

    end_traditional_pre = state.balance_traditional - trad_distributions
    # The spouse's IRA pays its own RMD, then its pro-rata share of everything
    # else drawn from traditional (conversion and withdrawal).
    spouse_pre = (
        state.balance_traditional_spouse if state.age_spouse is not None else _ZERO
    ) - rmd_spouse
    after_rmd = state.balance_traditional - rmd
    if spouse_pre > _ZERO and after_rmd > _ZERO:
        spouse_pre -= (conversion + w["traditional"]) * spouse_pre / after_rmd
    end_roth_pre = state.balance_roth + conversion - w["roth"]
    end_taxable_pre = state.balance_taxable - w["taxable"] + surplus

    # Basis updates. Traditional basis falls by the NON-taxable portion of every
    # distribution; taxable basis falls by the basis portion of the sale and
    # rises by the saved surplus.
    trad_basis_consumed = trad_distributions * (Decimal("1") - trad_taxable_frac)
    new_basis_traditional = max(_ZERO, state.basis_traditional - trad_basis_consumed)
    taxable_basis_consumed = w["taxable"] * basis_share
    new_basis_taxable = max(_ZERO, state.basis_taxable - taxable_basis_consumed) + surplus

    # Growth: taxable return carries a dividend tax drag; trad/roth grow at the
    # full nominal return.
    taxable_growth = (Decimal("1") + settings.nominal_return) - settings.dividend_yield * Decimal(
        "0.15"
    )
    nominal_growth = Decimal("1") + settings.nominal_return

    end_taxable = _q(end_taxable_pre * taxable_growth)
    end_traditional = _q(end_traditional_pre * nominal_growth)
    end_roth = _q(end_roth_pre * nominal_growth)
    end_traditional_spouse = min(end_traditional, _q(max(_ZERO, spouse_pre) * nominal_growth))

    magi = federal_res.agi

    # --- Step 7: advance year/ages, medicare flags, MAGI history -------------
    next_age_self = state.age_self + 1
    next_age_spouse = state.age_spouse + 1 if state.age_spouse is not None else None
    next_year = state.year + 1

    # --- Death transition ----------------------------------------------------
    # A death during year Y still files JOINTLY for Y (IRS treatment of the year
    # of death) and single from Y+1 — which is exactly what testing `next_year`
    # gives us, for free. Idempotent by construction: it is a comparison on the
    # year being built, not a flag being flipped.
    #
    # Hot path: `simulate_year` runs ~100k times per optimization, so the common
    # case (no death configured) is one `is None` check and nothing else.
    widowed = (
        settings.first_death_year is not None
        and next_year > settings.first_death_year
    )
    if widowed:
        # The SURVIVOR always occupies the `self` slot afterwards, whichever
        # person actually died. Assuming self outlives spouse would silently
        # carry the wrong age, the wrong Medicare status, and the wrong RMD
        # birth cohort for the rest of the plan.
        if settings.first_death_is_spouse:
            surv_age, surv_medicare = next_age_self, state.medicare_self
        else:
            surv_age = next_age_spouse if next_age_spouse is not None else next_age_self
            surv_medicare = state.medicare_spouse
        next_age_self = surv_age
        next_age_spouse = None
        next_filing = "single"
        next_medicare_self = surv_medicare or next_age_self >= 65
        next_medicare_spouse = False
        deceased_owner = "spouse" if settings.first_death_is_spouse else "self"
        end_traditional_spouse = _ZERO
    else:
        next_filing = state.filing_status
        next_medicare_self = state.medicare_self or next_age_self >= 65
        next_medicare_spouse = state.medicare_spouse or (
            next_age_spouse is not None and next_age_spouse >= 65
        )
        deceased_owner = None

    next_inc = resolve_income(settings.income_schedule, next_year, deceased_owner)
    next_state = State(
        year=next_year,
        age_self=next_age_self,
        age_spouse=next_age_spouse,
        balance_taxable=end_taxable,
        balance_traditional=end_traditional,
        balance_roth=end_roth,
        basis_taxable=new_basis_taxable,
        filing_status=next_filing,
        state_code=state.state_code,
        basis_traditional=new_basis_traditional,
        balance_traditional_spouse=end_traditional_spouse,
        salary=next_inc["salary"],
        pension=next_inc["pension"],
        rental=next_inc["rental"],
        # Next year's SS from claiming config (falls back to carry-forward
        # when Settings has no config). Account BALANCES are deliberately
        # untouched by the transition: a surviving spouse rolls the deceased's
        # IRA over and may treat it as their own, so the household total
        # carries forward whole.
        social_security=(
            _annual_social_security(
                engines, settings, next_age_self, next_age_spouse, widowed=widowed,
                year=next_year,
            )
            if (settings.ss_pia_self is not None or settings.ss_pia_spouse is not None)
            else state.social_security
        ),
        interest=next_inc["interest"],
        dividends_qualified=next_inc["dividends_qualified"],
        dividends_ordinary=next_inc["dividends_ordinary"],
        medicare_self=next_medicare_self,
        medicare_spouse=next_medicare_spouse,
        magi_two_years_ago=state.magi_last_year,
        magi_last_year=magi,
        loss_carryover_st=carry_st,
        loss_carryover_lt=carry_lt,
        state_loss_carryover_st=state_carry_st,
        state_loss_carryover_lt=state_carry_lt,
        roth_earliest_opened_year=state.roth_earliest_opened_year,
        # Guardrail cuts persist — carry the (possibly reduced) base and the
        # year-0 anchor forward rather than re-deriving them next year.
        spending_base=next_spending_base,
        initial_withdrawal_rate=initial_rate,
    )

    # Raw worksheet lines for the Tax Audit sheet. Deliberately NO
    # quantisation or sum-building here: simulate_year runs ~100k times per
    # optimization (search + Monte Carlo) but only the winner's ~30 ledgers
    # are exported. run_optimization finalises the audit (quantise, then
    # build sum lines from the quantised components so the sheet's
    # identities hold exactly) for winner rows only.
    audit = {
        "salary": state.salary,
        "pension": state.pension,
        "rental": state.rental,
        "interest": state.interest,
        "ordinary_dividends": state.dividends_ordinary,
        "traditional_taxable_portion": result["trad_taxable_ordinary"],
        "short_term_gain": gains.short_term,
        # Negative: it reduces ordinary income, and the sheet's sum line adds it.
        "capital_loss_deduction": -gains.loss_deduction,
        "gross_social_security": state.social_security,
        "taxable_social_security": result["taxable_ss"],
        "qualified_dividends": state.dividends_qualified,
        # Net long-term gain taxed this year, after netting everything below.
        "realized_ltcg": gains.long_term,
        "st_gain_already_realized": state.realized_st_gain,
        "lt_gain_already_realized": state.realized_lt_gain,
        "lt_gain_from_planned_sales": realized_gains,
        "loss_carryover_in_st": state.loss_carryover_st,
        "loss_carryover_in_lt": state.loss_carryover_lt,
        "loss_carryover_out_st": carry_st,
        "loss_carryover_out_lt": carry_lt,
        "agi": federal_res.agi,
        "deduction_type": federal_res.deduction_type,
        "deduction": federal_res.deduction_used,
        "senior_deduction": federal_res.senior_deduction,
        "taxable_income": federal_res.taxable_income,
        "taxable_ordinary_income": federal_res.taxable_ordinary,
        "ordinary_tax": federal_res.ordinary_tax,
        "ltcg_tax": federal_res.ltcg_tax,
        "niit": federal_res.niit,
        "federal_tax": federal_res.total_tax,
        "state_tax": result["state_tax"],
        "state_capital_loss_deduction": -state_gains.loss_deduction,
        "state_loss_carryover_out": state_carry_st + state_carry_lt,
        "irmaa_magi_lookback": state.magi_two_years_ago,
        "irmaa": result["irmaa"],
        "total_tax": total_tax,
        "surplus_saved": _q(surplus),
    }

    ledger = YearLedger(
        year=state.year,
        age_self=state.age_self,
        age_spouse=state.age_spouse,
        rmd=_q(rmd),
        conversion=_q(conversion),
        withdrawal_taxable=_q(w["taxable"]),
        withdrawal_traditional=_q(w["traditional"]),
        withdrawal_roth=_q(w["roth"]),
        realized_gains=_q(realized_gains),
        agi=_q(federal_res.agi),
        magi=_q(magi),
        federal_tax=_q(federal_res.total_tax),
        state_tax=_q(result["state_tax"]),
        irmaa=_q(result["irmaa"]),
        total_tax=_q(total_tax),
        net_spendable=_q(net_spendable),
        required_spending=_q(required_spending),
        shortfall=_q(shortfall),
        marginal_rate=federal_res.marginal_rate,
        end_taxable=end_taxable,
        end_traditional=end_traditional,
        end_roth=end_roth,
        audit=audit,
        target_spending=_q(target_spending),
        # Derived from the QUANTISED pair, not quantised independently, so
        # `target - required == cut` holds to the cent in the table and the
        # exports. Rounding all three separately left a stray penny.
        discretionary_cut=_q(target_spending) - _q(required_spending),
    )
    return next_state, ledger


def _apply_spending_rule(
    state: State,
    settings: Settings,
    fixed_cash: Decimal,
    inflator: Decimal,
    target_spending: Decimal,
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    """Decide what this year may spend. Returns (spending, next_base, initial_rate).

    Under ``spending_rule="fixed"`` this is the inflated target and nothing
    travels forward. Under ``"guardrails"`` it implements Guyton-Klinger:

      * The **withdrawal rate** is what the PORTFOLIO has to carry, not total
        spending — ``(spending - guaranteed income) / portfolio``. A household
        with a large pension is not overspending at 8% of a small portfolio,
        and rating it that way would cut spending it can plainly afford.
      * Compare that to ``initial_withdrawal_rate``, the rate in year 0, and
        move the spending BASE by ``guardrail_adjustment`` when the current
        rate sits more than ``guardrail_band`` away in either direction.
      * Cuts persist. The base is carried in today's dollars, so a 10% cut
        stays a 10% cut in real terms rather than being inflated away.

    Two deliberate departures from the published rule:

      * **Restoration stops at the target.** Guyton-Klinger's prosperity rule
        keeps raising spending in good markets. The user told us what they need,
        not what they would enjoy, and letting spending exceed the target would
        make the discretionary charge go negative — paying the objective a
        bonus for a bull market it did not earn.
      * **The floor binds after the guardrail.** Spending never drops below
        ``spending_floor``; the rule may find no cut available at all.

    Known characteristic worth stating: guaranteed income is counted GROSS
    here, because the tax on it depends on withdrawals that have not been
    solved yet. That makes the measured rate slightly low and the rule slightly
    permissive — but the SAME approximation sets the year-0 anchor, so the
    comparison the rule actually makes is largely self-cancelling.
    """
    if settings.spending_rule != "guardrails":
        return target_spending, state.spending_base, state.initial_withdrawal_rate

    portfolio = (
        state.balance_taxable + state.balance_traditional + state.balance_roth
    )

    def _rate(spending: Decimal) -> Decimal | None:
        """Share of the portfolio this year's spending has to draw."""
        if portfolio <= _ZERO:
            return None  # nothing left to rate; the shortfall machinery takes over
        return max(_ZERO, spending - fixed_cash) / portfolio

    # Seed the anchor on the first year that sees an unset state. Every policy
    # is simulated from the same starting state, so they all get the same
    # anchor — without that, policies would be measured against different rulers.
    initial_rate = state.initial_withdrawal_rate
    if initial_rate is None:
        initial_rate = _rate(target_spending)

    base = state.spending_base if state.spending_base is not None else settings.required_spending
    current_rate = _rate(base * inflator)

    if initial_rate is not None and current_rate is not None and initial_rate > _ZERO:
        upper = initial_rate * (Decimal("1") + settings.guardrail_band)
        lower = initial_rate * (Decimal("1") - settings.guardrail_band)
        if current_rate > upper:
            base = base * (Decimal("1") - settings.guardrail_adjustment)
        elif current_rate < lower:
            base = base * (Decimal("1") + settings.guardrail_adjustment)

    # Never above the stated target, never below the essential floor.
    base = min(base, settings.required_spending)
    if settings.spending_floor is not None:
        base = max(base, settings.spending_floor)

    return base * inflator, base, initial_rate


def _ONE_MINUS(basis: Decimal, balance: Decimal) -> Decimal:
    """Return 1 - basis/balance (the taxable/gain fraction)."""
    return Decimal("1") - basis / balance


def _compute_taxes(
    state: State,
    engines: Engines,
    constraints: Constraints,
    rmd: Decimal,
    conversion: Decimal,
    w: dict,
    gains: NetGains,
    state_gains: NetGains,
    trad_taxable_frac: Decimal,
    inflation: Decimal,
):
    """Compute (federal_result, state_tax, irmaa, ...) for the current withdrawals.

    *gains* is the federal netting, *state_gains* the state's: the same
    object unless the state nets the gains separately (state_loss_rule).

    *inflation* projects every tax table past its last published year (see
    TaxRules), so years after 2026 are not taxed on frozen 2026 brackets."""
    trad_distributions = rmd + conversion + w["traditional"]
    trad_taxable_ordinary = trad_distributions * trad_taxable_frac

    # Ordinary income before capital results, shared by federal and state.
    base_ordinary = (
        state.salary
        + state.pension
        + state.rental
        + state.interest
        + state.dividends_ordinary
        + trad_taxable_ordinary
    )
    # Ordinary income excluding Social Security (base for SS provisional rules).
    # A net short-term gain is ordinary income; a net capital loss is deducted
    # from it (up to $3,000), which can take it below zero.
    non_ss_ordinary = base_ordinary + gains.short_term - gains.loss_deduction
    # Provisional income also counts preferential income (LTCG + qualified div).
    other_for_ss = non_ss_ordinary + gains.long_term + state.dividends_qualified
    taxable_ss = taxable_social_security(state.social_security, other_for_ss, state.filing_status)

    federal_income = FederalIncome(
        ordinary=non_ss_ordinary + taxable_ss,
        ltcg=gains.long_term,
        qualified_dividends=state.dividends_qualified,
        # Net gains count toward NIIT, and the capital loss deduction may
        # offset other investment income (Treas. Reg. 1.1411-4(d)).
        investment_income=max(
            _ZERO,
            state.interest
            + state.dividends_ordinary
            + state.dividends_qualified
            + gains.short_term
            + gains.long_term
            - gains.loss_deduction,
        ),
    )
    federal_res = engines.federal.calculate(
        federal_income,
        state.filing_status,
        state.year,
        state.age_self,
        state.age_spouse,
        inflation=inflation,
    )

    # State: pass GROSS SS (engine applies its own exemption). Qualified
    # dividends are ordinary at the state level.
    state_income = StateIncome(
        ordinary=base_ordinary + state_gains.short_term - state_gains.loss_deduction
        + state.dividends_qualified,
        capital_gains_long=state_gains.long_term,
        social_security=state.social_security,
    )
    state_tax = engines.state.calculate(
        state_income, state.state_code, state.filing_status, year=state.year,
        inflation=inflation,
    )

    # IRMAA: uses MAGI from two years prior; premium year is the current year.
    # Charged for each person on Medicare, whatever the IRMAA policy: the
    # policy only decides whether conversions may cross a tier, and the
    # premiums are owed either way.
    irmaa = _ZERO
    persons = int(state.medicare_self) + int(state.medicare_spouse)
    if persons:
        irmaa = engines.irmaa.annual_surcharge(
            state.magi_two_years_ago,
            state.filing_status,
            state.year,
            persons,
            inflation=inflation,
        )

    # taxable_ss and trad_taxable_ordinary are returned for the audit
    # worksheet (built once per year in simulate_year, not per iteration —
    # this function runs inside the fixed-point loop, in the hot path).
    return federal_res, state_tax, irmaa, taxable_ss, trad_taxable_ordinary, state_income
