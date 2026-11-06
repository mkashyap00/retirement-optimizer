"""Social Security benefits calculator engine.

Implements SSA early-claiming reduction and delayed-retirement credit formulas.
No external data dependency — SSA benefit adjustments are structural (statutory).

Ported from backend/reference/engines/social_security.py (v2 quarantine).
Dropped: survivor benefits, optimize_claiming_strategy, NPV helpers, db_connection.
Fixed: early-claiming reduction now uses exact Decimal fractions (5/900, 5/1200)
       instead of v2's approximate constants (0.00556, 0.00417), which produced
       a 0.168% rounding error at claim_age=62.
"""

from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")

# Early claiming: 5/9 of 1% per month for first 36 months before FRA
_EARLY_RATE_36 = Decimal("5") / Decimal("900")
# Early claiming: 5/12 of 1% per month for months beyond 36
_EARLY_RATE_REST = Decimal("5") / Decimal("1200")

# Delayed credits: 8% per year = 2/3 of 1% per month
_DELAYED_RATE_PER_YEAR = Decimal("8") / Decimal("100")


class SocialSecurityCalculator:
    """Calculate Social Security monthly benefits.

    Methods
    -------
    monthly_benefit(pia, claim_age, fra) -> Decimal
        Own benefit adjusted for early/delayed claiming.
    spousal_benefit(own_pia, primary_pia, claim_age, fra, spousal_start_age) -> Decimal
        Own adjusted benefit plus the excess of 50 % of the primary's PIA over
        the own PIA, that excess reduced for months before FRA at spousal
        entitlement (SSA dual entitlement).
    survivor_benefit(own_benefit, deceased_benefit, survivor_age, fra) -> Decimal
        Higher of own benefit or the deceased's — never the sum.
    """

    def survivor_basis_claim_age(
        self,
        deceased_claim_age: int,
        age_at_death: int | None,
        fra: Decimal | int = 67,
    ) -> Decimal | int:
        """Claim age whose benefit the survivor benefit is computed FROM.

        Not the same as the deceased's planned claim age. SSA bases a survivor
        benefit on what the worker was *actually* receiving, or would have been:

          * Worker had already claimed  -> the amount they were drawing.
          * Died before claiming, before FRA -> their PIA, i.e. the FRA amount.
            Planning to claim at 70 earns nothing if you die at 62.
          * Died before claiming, after FRA -> PIA plus the delayed credits
            earned up to death.

        Getting this wrong runs GENEROUS — crediting a delayed claim that never
        happened would overstate survivor income and understate the widow's
        penalty, which is the exact bias this whole feature exists to remove.

        ``age_at_death=None`` means we cannot tell (no birth year for the
        deceased), and the planned claim age is used unchanged.
        """
        if age_at_death is None or deceased_claim_age <= age_at_death:
            return deceased_claim_age  # had claimed; drawing that amount
        return min(max(age_at_death, fra), 70)

    def survivor_benefit(
        self,
        own_benefit: Decimal,
        deceased_benefit: Decimal,
        survivor_age: int,
        fra: Decimal | int = 67,
    ) -> Decimal:
        """Return the survivor's monthly benefit: the LARGER of the two, not the sum.

        This is the whole point of the widow's penalty — household income falls
        by the smaller benefit while the survivor moves to single brackets.

        Survivor benefits start at **60** (earlier only for disability, not
        modelled). Claimed before FRA they are reduced on their own schedule:
        **71.5%** of the deceased's benefit at 60, rising linearly to 100% at
        FRA. That is a different curve from both the own-benefit and the
        spousal reduction, so it gets its own arithmetic here.

        Parameters
        ----------
        own_benefit:      The survivor's own monthly benefit, already adjusted.
        deceased_benefit: The deceased's monthly benefit — see
                          ``survivor_basis_claim_age`` for which one that is.
        survivor_age:     The survivor's age this year.
        fra:              The survivor's Full Retirement Age for survivor
                          benefits (its own SSA table; see
                          data/tax_rules/social_security.py).
        """
        if survivor_age < 60:
            survivor_portion = Decimal("0")
        elif survivor_age >= fra:
            survivor_portion = deceased_benefit
        else:
            # 71.5% at 60 -> 100% at FRA, linear in the months between.
            span = Decimal(fra - 60)
            progressed = Decimal(survivor_age - 60) / span
            factor = Decimal("0.715") + Decimal("0.285") * progressed
            survivor_portion = deceased_benefit * factor

        return max(own_benefit, survivor_portion).quantize(
            _CENTS, rounding=ROUND_HALF_UP
        )

    def monthly_benefit(
        self,
        pia: Decimal,
        claim_age: int,
        fra: Decimal = Decimal("67"),
    ) -> Decimal:
        """Return monthly benefit at *claim_age*, quantized to cents.

        Parameters
        ----------
        pia:        Primary Insurance Amount (monthly benefit at FRA).
        claim_age:  Integer age when claiming (62–70; capped at 70).
        fra:        Full Retirement Age as Decimal (default 67; 66 and 2-10
                    months for those born 1955-1959 -- see
                    data/tax_rules/social_security.py).
        """
        claim_age = min(claim_age, 70)

        if claim_age < fra:
            # Early claiming reduction
            months_early = (fra - claim_age) * 12
            if months_early <= 36:
                reduction = months_early * _EARLY_RATE_36
            else:
                reduction = (36 * _EARLY_RATE_36) + (
                    (months_early - 36) * _EARLY_RATE_REST
                )
            factor = Decimal("1") - reduction

        elif claim_age > fra:
            # Delayed retirement credits: 8 %/year, capped at age 70
            years_delayed = min(Decimal(claim_age) - fra, Decimal("70") - fra)
            factor = Decimal("1") + (years_delayed * _DELAYED_RATE_PER_YEAR)

        else:
            factor = Decimal("1")

        return (pia * factor).quantize(_CENTS, rounding=ROUND_HALF_UP)

    def spousal_benefit(
        self,
        own_pia: Decimal,
        primary_pia: Decimal,
        claim_age: int,
        fra: Decimal = Decimal("67"),
        spousal_start_age: int | None = None,
    ) -> Decimal:
        """Return the monthly benefit of someone also entitled as a spouse.

        SSA dual entitlement (POMS RS 00615.020, Method C): the own retirement
        benefit, reduced or credited for ``claim_age`` as usual, PLUS the
        spousal EXCESS — half the primary's PIA minus the recipient's
        *unreduced* own PIA — reduced separately for the months before FRA at
        which spousal entitlement begins. Taking the larger of the two whole
        benefits instead understates an early claim (it reduces the full half
        rather than the excess) and drops the own benefit's delayed credits.

        Spousal months early use SSA's spousal rate: 25/36 of 1% for the first
        36, 5/12 of 1% beyond. Spousal benefits earn no delayed credits.

        Parameters
        ----------
        own_pia:     Recipient's own Primary Insurance Amount.
        primary_pia: Primary worker's PIA.
        claim_age:   Integer age when the recipient claims their own benefit.
        fra:         Recipient's Full Retirement Age (default 67).
        spousal_start_age: Recipient's age when spousal entitlement begins —
                     later than ``claim_age`` when the primary files later.
                     Defaults to ``claim_age`` (deemed filing: born after
                     1/1/1954, filing for one benefit files for both).
        """
        own_benefit = self.monthly_benefit(own_pia, claim_age, fra)

        excess = max(Decimal("0"), primary_pia * Decimal("0.5") - own_pia)
        start = max(claim_age, spousal_start_age if spousal_start_age is not None else claim_age)
        if start < fra:
            months_early = (fra - start) * 12
            spousal_early_rate_36 = Decimal("25") / Decimal("3600")
            if months_early <= 36:
                reduction = months_early * spousal_early_rate_36
            else:
                reduction = (36 * spousal_early_rate_36) + (
                    (months_early - 36) * _EARLY_RATE_REST
                )
            excess = excess * (Decimal("1") - reduction)

        return (own_benefit + excess).quantize(_CENTS, rounding=ROUND_HALF_UP)
