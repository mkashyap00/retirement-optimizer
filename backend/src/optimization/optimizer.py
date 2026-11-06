"""End-to-end optimizer orchestrator.

`run_optimization` is the single entry-point for the retirement optimizer pipeline:
  1. Rule search (``search``) → candidate policies sorted by path_value.
  2. Monte Carlo scoring (``score_policies_adaptive``) → staged ranking.
  3. Output assembly → dict with a stable, documented shape.

This module is the ONLY Decimal→float boundary in the backend.  All values in
the returned dict are Python native types (float, int, str, list, dict).

Performance
-----------
``FederalTaxEngine.calculate`` is the hot path.  A per-call memo dict
(keyed on income + filing parameters) is injected via a thin wrapper so that
repeated identical tax computations during the search and Monte Carlo phases
return cached results without modifying any engine.
"""
from __future__ import annotations

import dataclasses
import time
from decimal import Decimal

from src.data.tax_rules.indexing import INDEXED_STATES
from src.engines.tax.federal import FederalIncome, FederalResult, FederalTaxEngine
from src.optimization.claiming import (
    assumed_filing_people,
    legacy_inference_people,
    require_claim_ages,
)
from src.optimization.evaluate import PathResult, objective_value
from src.optimization.montecarlo import (
    PairedComparison,
    ScoredPolicy,
    compare_paired,
    market_model,
    score_policies_adaptive,
)
from src.optimization.search import Policy, rule_of, search
from src.optimization.state import (
    Constraints,
    Engines,
    Settings,
    State,
    YearLedger,
)
from src.rationale.generator import build_rationale
from src.rationale.narrative import render_narrative, zero_conversion_reason
from src.reports.policy_labels import policy_label

_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Audit finalization — winner rows only (the raw dict is captured for every
# simulated year, but quantising in simulate_year would sit in the hot path)
# ---------------------------------------------------------------------------

_CENT = Decimal("0.01")

_AUDIT_ORDINARY_COMPONENTS = (
    "salary",
    "pension",
    "rental",
    "interest",
    "ordinary_dividends",
    "traditional_taxable_portion",
    "short_term_gain",
    "capital_loss_deduction",  # stored negative
    "taxable_social_security",
)


def _finalize_audit(ledger) -> dict | None:
    """Quantise the raw audit lines and build the sum lines FROM the
    quantised components, so the exported sheet's identities hold exactly
    (a CPA ticking lines must never hit a rounding mismatch)."""
    raw = ledger.audit
    if raw is None:
        return None

    quantised = {
        k: (v.quantize(_CENT) if isinstance(v, Decimal) else v)
        for k, v in raw.items()
    }
    quantised["ordinary_income"] = sum(
        quantised[k] for k in _AUDIT_ORDINARY_COMPONENTS
    )
    # Ledger fields are already cent-quantised; summing them keeps the line
    # identical to the Yearly Plan sheet's rmd/conversion/withdrawal columns.
    quantised["traditional_distributions"] = (
        ledger.rmd + ledger.conversion + ledger.withdrawal_traditional
    )
    quantised["total_tax"] = ledger.total_tax
    quantised["federal_tax"] = ledger.federal_tax
    quantised["state_tax"] = ledger.state_tax
    quantised["irmaa"] = ledger.irmaa
    quantised["agi"] = ledger.agi

    return {
        k: (float(v) if isinstance(v, Decimal) else v)
        for k, v in quantised.items()
    }


# ---------------------------------------------------------------------------
# Rationale serialization helper
# ---------------------------------------------------------------------------


def _rationale_to_dict(r) -> dict:
    """Convert a DecisionRationale dataclass to a plain JSON-safe dict.

    Uses ``dataclasses.asdict`` for recursive dataclass→dict expansion, then
    walks the resulting structure to convert every ``Decimal`` to ``float``.
    ``None`` values pass through unchanged.  ``list`` and nested ``dict``
    entries are handled recursively so that ``warnings`` (a list of
    ``ThresholdWarning`` dicts) and all nested sub-dataclasses (BracketFacts,
    ConversionRationale, WithdrawalRationale) convert cleanly.
    """

    def _convert(obj):
        if obj is None:
            return None
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(v) for v in obj]
        return obj

    return _convert(dataclasses.asdict(r))


# ---------------------------------------------------------------------------
# Memoized federal-engine wrapper (optimizer-scoped; does not mutate the engine)
# ---------------------------------------------------------------------------


class _MemoFederalEngine:
    """Drop-in wrapper for FederalTaxEngine that caches calculate() results.

    The cache is per-instance (i.e. per optimizer run).  Only calls without
    ``itemized`` inputs are cached, since itemized deductions are path-specific
    and rare.

    Key: (ordinary, ltcg, qualified_dividends, investment_income,
          filing_status, year, taxpayer_age, spouse_age, inflation)
    """

    def __init__(self, inner: FederalTaxEngine) -> None:
        self._inner = inner
        self._cache: dict[tuple, FederalResult] = {}
        # Expose attributes accessed by actions.py / transition.py
        self.rules = inner.rules

    def calculate(
        self,
        income: FederalIncome,
        filing_status: str,
        year: int,
        taxpayer_age: int,
        spouse_age: int | None = None,
        itemized=None,
        inflation: Decimal | None = None,
    ) -> FederalResult:
        # Only cache the common path (no itemized deductions).
        if itemized is None:
            key = (
                income.ordinary,
                income.ltcg,
                income.qualified_dividends,
                income.investment_income,
                filing_status,
                year,
                taxpayer_age,
                spouse_age,
                inflation,
            )
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            result = self._inner.calculate(
                income, filing_status, year, taxpayer_age, spouse_age, itemized,
                inflation,
            )
            self._cache[key] = result
            return result

        # itemized path: no caching (rare and highly path-specific)
        return self._inner.calculate(
            income, filing_status, year, taxpayer_age, spouse_age, itemized, inflation
        )

    def salt_cap(
        self, magi: Decimal, filing_status: str, year: int,
        inflation: Decimal | None = None,
    ) -> Decimal:
        return self._inner.salt_cap(magi, filing_status, year, inflation)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _paired_dict(c: PairedComparison) -> dict:
    """Serialise a paired comparison for the API.

    ``verdict`` is the field to read first. "unresolved" means the simulation
    cannot tell which policy is better at this budget — it does NOT mean they
    are equivalent, which is a separate verdict that only a declared
    materiality threshold can earn.
    """
    return {
        "verdict": c.verdict,
        "mean_difference": float(c.mean_difference),
        "median_difference": float(c.median_difference),
        "std_error": float(c.std_error),
        "ci_low": float(c.ci_low),
        "ci_high": float(c.ci_high),
        "winner_win_fraction": float(c.winner_win_fraction),
        # Where the difference comes from: a mean can rest on a handful of
        # paths where one plan depletes and the other does not.
        "both_feasible": c.both_feasible,
        "winner_only_feasible": c.winner_only_feasible,
        "alternative_only_feasible": c.alternative_only_feasible,
        "both_infeasible": c.both_infeasible,
        "both_feasible_mean_difference": float(c.both_feasible_mean_difference),
    }


def materiality(state: State) -> Decimal:
    """The gap worth calling a difference: max($5,000, 0.25% of investable
    assets), the benchmark gate's tolerance. Paired comparisons inside it are
    "equivalent" rather than merely "unresolved"."""
    assets = state.balance_taxable + state.balance_traditional + state.balance_roth
    return max(Decimal("5000"), Decimal("0.0025") * assets).quantize(Decimal("0.01"))


def mc_score_components(sp: ScoredPolicy, settings: Settings) -> dict | None:
    """Mean components over the paths *sp* was scored on; they reconstruct
    ``sp.score`` to rounding (each mean is quantised separately). None when
    *sp* carries no component means."""
    m = sp.mean_components
    if m is None:
        return None
    return {
        "basis": "monte_carlo",
        "monte_carlo_paths": len(sp.path_objectives),
        "estate_pv": float(m.estate_pv),
        "shortfall_pv": float(m.shortfall_pv),
        "discretionary_shortfall_pv": float(m.discretionary_shortfall_pv),
        "shortfall_weight": float(settings.shortfall_weight),
        "discretionary_shortfall_weight": float(settings.discretionary_shortfall_weight),
        "score": float(sp.score),
        # Reported, not scored: the estate is already net of every tax paid.
        "lifetime_taxes_pv": float(m.taxes_pv),
    }


def _baseline_dict(winner: ScoredPolicy, base: ScoredPolicy, mat: Decimal,
                   settings: Settings) -> dict:
    """``none`` at the same ages against the reported plan: what converting
    adds, on the full sample and the same paths."""
    same = base.policy.policy_id == winner.policy.policy_id
    return {
        "policy_id": base.policy.policy_id,
        "score": float(base.score),
        "success_probability": float(base.success_probability),
        "monte_carlo_paths": len(base.path_objectives),
        # winner − baseline; 0 and no verdict when the plan IS the baseline.
        "score_difference": float(winner.score - base.score),
        "is_recommendation": same,
        "paired": None if same else _paired_dict(compare_paired(winner, base, mat)),
        # Both sides' estate and unfunded spending on the same paths, so the
        # page can say what the score difference is made of.
        "score_components": mc_score_components(base, settings),
        "recommendation_score_components": mc_score_components(winner, settings),
    }


def _first_conversion_year(policy: Policy) -> int | None:
    """Calendar year of the policy's first non-zero conversion, or None."""
    return next(
        (lg.year for lg in policy.result.ledgers if lg.conversion > _ZERO), None
    )


def _year0_conversion(policy: Policy) -> float:
    """The policy's first-year conversion; 0 for an all-zero schedule."""
    return float(policy.conversions[0]) if policy.conversions else 0.0


# Identifies the objective a run was scored with; see evaluate.objective_value.
OBJECTIVE_ID = "pv_estate_minus_weighted_shortfall"


def _tax_tables(engines: Engines, settings: Settings) -> dict:
    """Provenance of the tax tables a run used."""
    published = engines.rules.published_through()
    return {
        "federal_published_through": published["federal"],
        "irmaa_published_through": published["irmaa"],
        "state_published_through": published["state"],
        # States whose later years are projected; every other state keeps its
        # latest published schedule.
        "state_indexed": sorted(INDEXED_STATES),
        "indexation_rate": float(max(_ZERO, settings.inflation)),
        "irmaa_premiums_projected": False,
    }


def _score_components(result: PathResult, settings: Settings) -> dict:
    """What the score is made of, on the policy's DETERMINISTIC (expected-return)
    path. These reconcile with ``deterministic_value``, not with the Monte
    Carlo ``score``, which averages the same objective over many paths."""
    return {
        "basis": "deterministic",
        "terminal_estate_pv": float(result.terminal_estate_pv),
        "shortfall_pv": float(result.shortfall_pv),
        "discretionary_shortfall_pv": float(result.discretionary_shortfall_pv),
        "shortfall_weight": float(settings.shortfall_weight),
        "discretionary_shortfall_weight": float(settings.discretionary_shortfall_weight),
        "deterministic_value": float(objective_value(result, settings)),
        # Reported, not scored: the estate is already net of every tax paid.
        "lifetime_taxes_pv": float(result.lifetime_taxes_pv),
    }


def build_report(
    winner: ScoredPolicy,
    runners_up: list[ScoredPolicy],
    none_policy: Policy | None,
    state: State,
    engines: Engines,
    settings: Settings,
    materiality: Decimal = _ZERO,
) -> tuple[list[dict], dict, list[dict], list[str]]:
    """The yearly plan, winner card, alternatives and warnings for an already
    scored winner -- no search, no simulation beyond what *winner* carries.

    Every Monte Carlo figure (score, success_probability, paths, paired
    comparisons) comes from the ScoredPolicy objects passed in, so a caller
    that scored them itself (the joint claim-age search) reports its own
    statistics rather than a re-run's. *none_policy* is the no-conversion
    policy on the winner's inputs: the rationale's counterfactual.
    """
    # ── Baseline ("none") policy projected future marginal rate ──────────────
    if none_policy is not None:
        _projected_future_marginal_rate: float = float(
            max(lg.marginal_rate for lg in none_policy.result.ledgers)
        )
    else:
        _projected_future_marginal_rate = 0.0

    # ── 3. Yearly plan from the winning policy's deterministic PathResult ────
    ledgers: tuple[YearLedger, ...] = winner.policy.result.ledgers

    # Baseline ("none") ledgers for counterfactual rationale.
    # Each year in the winner's plan is paired with the corresponding baseline
    # ledger (same year index) so build_rationale can compute marginal_cost_rate
    # and BETR.  When the winner IS the "none" policy, or when the baseline has
    # fewer feasible years, None is passed instead (build_rationale returns
    # conversion=None in those cases anyway since ledger.conversion == 0).
    _baseline_ledgers: tuple[YearLedger, ...] = (
        none_policy.result.ledgers if none_policy is not None else ()
    )
    _winner_is_none: bool = winner.policy.policy_id == "none"
    _pfmr_decimal: Decimal = Decimal(str(_projected_future_marginal_rate))

    _conv_years = [lg.year for lg in ledgers if lg.conversion > _ZERO]
    _first_conv = _conv_years[0] if _conv_years else None
    _last_conv = _conv_years[-1] if _conv_years else None

    yearly_plan: list[dict] = []
    for year_idx, ledger in enumerate(ledgers):
        agi_f = float(ledger.agi)
        total_tax_f = float(ledger.total_tax)
        effective_rate = (total_tax_f / agi_f) if agi_f != 0.0 else 0.0

        # ── Rationale ───────────────────────────────────────────────────────
        # action_id per year (tags the rationale; narrative wording itself comes
        # from the actual bracket the conversion landed in, not this string):
        #   rule winner ("<rule>_annual" / "<rule>_thru_<YYYY>") → the base
        #     rule every conversion year, since it is what sized that year.
        #   "none" never converts.
        _base_rule = rule_of(winner.policy.policy_id)
        if _base_rule is not None and ledger.conversion > _ZERO:
            _action_id = _base_rule
        else:
            _action_id = "none"

        # Counterfactual: baseline "none" ledger for the same year index.
        # Omit when the winner is "none" (winner == baseline, no meaningful
        # counterfactual) or when the baseline path ended before this year.
        if _winner_is_none or year_idx >= len(_baseline_ledgers):
            _zero_ledger: YearLedger | None = None
        else:
            _zero_ledger = _baseline_ledgers[year_idx]

        _r = build_rationale(
            ledger=ledger,
            zero_ledger=_zero_ledger,
            action_id=_action_id,
            rules=engines.rules,
            settings=settings,
            filing_status=state.filing_status,
            projected_future_marginal_rate=_pfmr_decimal,
        )
        _zero_reason = None
        if ledger.conversion <= _ZERO:
            _trad_before = (ledgers[year_idx - 1].end_traditional if year_idx > 0
                            else state.balance_traditional)
            _zero_reason = zero_conversion_reason(
                winner.policy.policy_id, ledger.year, _first_conv, _last_conv, _trad_before,
            )
        _rationale = dataclasses.replace(_r, narrative=render_narrative(_r, _zero_reason))

        yearly_plan.append(
            {
                "year": ledger.year,           # int — no conversion needed
                "age_self": ledger.age_self,   # int
                "age_spouse": ledger.age_spouse,  # int | None
                "conversion": float(ledger.conversion),
                "withdrawal_taxable": float(ledger.withdrawal_taxable),
                "withdrawal_traditional": float(ledger.withdrawal_traditional),
                "withdrawal_roth": float(ledger.withdrawal_roth),
                "rmd": float(ledger.rmd),
                "agi": agi_f,
                "magi": float(ledger.magi),
                "federal_tax": float(ledger.federal_tax),
                "state_tax": float(ledger.state_tax),
                "irmaa": float(ledger.irmaa),
                "total_tax": total_tax_f,
                "effective_rate": effective_rate,
                "marginal_rate": float(ledger.marginal_rate),
                "net_spendable": float(ledger.net_spendable),
                # What the plan TRIED to fund — the target, or the reduced
                # amount the spending rule allowed.
                "required_spending": float(ledger.required_spending),
                # The un-cut goal, so the UI can show both when they differ.
                "target_spending": float(ledger.target_spending),
                # Spending the guardrails chose to give up this year (0 under
                # the default fixed rule).
                "discretionary_cut": float(ledger.discretionary_cut),
                # > 0 only when the year could not fund even the planned
                # spending after draining every account.
                "shortfall": float(ledger.shortfall),
                "balance_taxable": float(ledger.end_taxable),
                "balance_traditional": float(ledger.end_traditional),
                "balance_roth": float(ledger.end_roth),
                "rationale": _rationale_to_dict(_rationale),
                # Worksheet-line derivation for the Tax Audit sheet
                "audit": _finalize_audit(ledger),
            }
        )

    # ── 4. Winning-policy summary ────────────────────────────────────────────
    total_conversions = float(sum(winner.policy.conversions, _ZERO))
    winning_policy: dict = {
        "policy_id": winner.policy.policy_id,
        "lifetime_taxes_nominal": float(winner.policy.result.lifetime_taxes_nominal),
        "lifetime_taxes_pv": float(winner.policy.result.lifetime_taxes_pv),
        # The rate lifetime_taxes_pv is discounted at, so the UI can state the
        # basis instead of hardcoding it.
        "discount_rate": float(settings.discount_rate),
        "terminal_estate": float(winner.policy.result.terminal_estate),
        "success_probability": float(winner.success_probability),
        # Scenarios this policy was actually scored on -- what the success
        # interval must be computed from. monte_carlo_runs is the REQUEST.
        "monte_carlo_paths": len(winner.path_objectives),
        "score": float(winner.score),
        "total_conversions": total_conversions,
        # This year's conversion: the one decision the user acts on before
        # re-running next year. Reported beside each alternative's so the
        # spread between close strategies is visible, not just their totals.
        "year0_conversion": _year0_conversion(winner.policy),
        "projected_future_marginal_rate": _projected_future_marginal_rate,
        # Average years spending landed below target across the Monte Carlo
        # scenarios. Belongs next to success_probability: once spending can
        # flex, "the plan never failed" and "the plan delivered what you asked
        # for" are different claims, and only this one answers the second.
        "mean_years_reduced": float(winner.mean_years_reduced),
        "score_components": _score_components(winner.policy.result, settings),
    }

    # ── 5. Alternative policies (sign: alternative − winner) ─────────────────
    # lifetime_taxes_delta > 0 means alternative costs more in taxes than winner.
    # terminal_estate_delta > 0 means alternative leaves a larger estate.
    # success_probability_delta > 0 means alternative has higher success rate.
    # Taxes are compared on PRESENT VALUE — the same figure the winner card
    # shows and the basis the optimizer actually ranks on — so a runner-up with
    # a lower *nominal* bill can't appear to "beat" the winner it lost to.
    winner_taxes = float(winner.policy.result.lifetime_taxes_pv)
    winner_estate = float(winner.policy.result.terminal_estate)
    winner_success = float(winner.success_probability)

    alternative_policies: list[dict] = []
    for sp in runners_up:
        alternative_policies.append(
            {
                "policy_id": sp.policy.policy_id,
                # positive = alternative costs MORE in PV taxes (worse than winner)
                "lifetime_taxes_delta": (
                    float(sp.policy.result.lifetime_taxes_pv) - winner_taxes
                ),
                # positive = alternative leaves MORE estate (better than winner)
                "terminal_estate_delta": float(sp.policy.result.terminal_estate) - winner_estate,
                # positive = alternative has HIGHER success probability (better than winner)
                "success_probability_delta": float(sp.success_probability) - winner_success,
                # A policy eliminated at stage 1 rests on a third of the
                # scenarios; its figures are noisier than the winner's.
                "monte_carlo_paths": len(sp.path_objectives),
                # Its own Monte Carlo score, the figure the ranking compares.
                "score": float(sp.score),
                # Absolute, not deltas: close strategies agree on roughly how
                # much to convert overall and can disagree by hundreds of
                # thousands on how much to convert NOW. That is the number a
                # user acts on, so it is reported as-is.
                "year0_conversion": _year0_conversion(sp.policy),
                "total_conversions": float(sum(sp.policy.conversions, _ZERO)),
                # When close strategies all convert $0 this year, what still
                # separates them is the year each starts. None = never converts.
                "first_conversion_year": _first_conversion_year(sp.policy),
                # Paired comparison on identical return sequences. The deltas
                # above come from ONE expected-return path; this is the whole
                # distribution, and it is what says whether the winner's lead
                # is real or inside the simulation's own noise.
                "paired": _paired_dict(compare_paired(winner, sp, materiality)),
                "score_components": _score_components(sp.policy.result, settings),
            }
        )

    # ── 6. Warnings ──────────────────────────────────────────────────────────
    warnings: list[str] = []

    # Dynamic spending changes what "success" claims. With guardrails on, a
    # plan can reach 100% by cutting its way there — never failing to fund what
    # it decided to spend, while spending less than the household asked for.
    # Saying so is not optional: it is the difference between "your plan works"
    # and "your plan works if you accept these cuts".
    if settings.spending_rule == "guardrails":
        _cut_years = [lg for lg in ledgers if lg.discretionary_cut > _ZERO]
        _floor_txt = (
            f" Spending never drops below your ${settings.spending_floor:,.0f} "
            "floor."
            if settings.spending_floor is not None
            else ""
        )
        if _cut_years:
            _deepest = max(
                lg.discretionary_cut / lg.target_spending for lg in _cut_years
            )
            warnings.append(
                f"Spending guardrails are ON: this plan reduces spending below "
                f"your target in {len(_cut_years)} of {settings.simulation_years} "
                f"years, by up to {_deepest:.0%}. Success probability therefore "
                f"means 'never failed to fund the REDUCED spending', not 'always "
                f"funded your full target'.{_floor_txt}"
            )
        else:
            warnings.append(
                "Spending guardrails are ON but were never triggered in the "
                "projected case — spending stays at your target throughout. "
                "They may still trigger in the weaker Monte Carlo scenarios; "
                "see the years-reduced figure beside success probability."
            )

    # Underfunded plan: the winner's rollout cannot cover required spending in
    # every year.  The table now runs the full horizon with the short years
    # shown as they are, so the warning names where the gap starts and how big
    # it is rather than explaining a table that stops early.
    winner_result = winner.policy.result
    if not winner_result.feasible:
        short_ledgers = [lg for lg in ledgers if lg.shortfall > _ZERO]
        if short_ledgers:
            first_short = short_ledgers[0]
            worst = max(lg.shortfall for lg in short_ledgers)
            warnings.append(
                f"Projected funds fall short of required spending starting in "
                f"{first_short.year} (age {first_short.age_self}): "
                f"${first_short.shortfall:,.0f} unfunded that year, "
                f"{len(short_ledgers)} short years in total, worst "
                f"${worst:,.0f}. The table still runs the full "
                f"{settings.simulation_years}-year horizon — the short years "
                "show what income alone would cover. Consider lower spending, "
                "later spending needs, or different claiming ages."
            )

    # Roth 5-year rule caveat (v1 deliberate simplification).
    # Warn if any ledger shows withdrawal_roth > 0 within 5 years of a conversion.
    conversion_years = frozenset(
        ledger.year for ledger in ledgers if ledger.conversion > _ZERO
    )
    if conversion_years:
        for ledger in ledgers:
            if ledger.withdrawal_roth > _ZERO:
                if any(0 <= ledger.year - cy < 5 for cy in conversion_years):
                    warnings.append(
                        "Roth 5-year rule: a Roth withdrawal occurs within 5 years of a "
                        "conversion; earnings on that conversion amount may be subject to "
                        "tax and penalty (v1 simplification — individual conversion layers "
                        "are not tracked)."
                    )
                    break  # one warning is sufficient

    # Account-based Roth 5-year rule caveat (uses the earliest Roth open year,
    # when provided). Warn — do not block — if a Roth withdrawal happens while
    # the account is under 5 years old and the owner is under 59.5 (approximated
    # as age < 60 at year resolution), since earnings may then be non-qualified.
    opened_year = state.roth_earliest_opened_year
    if opened_year is not None:
        for ledger in ledgers:
            if (
                ledger.withdrawal_roth > _ZERO
                and ledger.age_self < 60
                and (ledger.year - opened_year) < 5
            ):
                warnings.append(
                    "Roth 5-year rule: a Roth withdrawal occurs before the account has "
                    "been open 5 years and before age 59½; earnings withdrawn may be "
                    "subject to income tax and a 10% penalty. Contributions and converted "
                    "principal are generally still tax- and penalty-free."
                )
                break  # one warning is sufficient

    # Social Security readings the inputs did not state outright.
    for person in legacy_inference_people(state, settings):
        warnings.append(
            f"Social Security ({person}): treated as already being received because "
            "their age has reached the stored claim age (legacy inference — whether "
            "they are receiving was not stated). Confirm it in the plan's settings."
        )
    for person in assumed_filing_people(state, settings):
        warnings.append(
            f"Social Security ({person}): over 70 and not yet receiving, so modelled as "
            "filing this year at the age-70 benefit — an assumed filing, not a "
            "historical claim."
        )

    if settings.stale_capital_gains_year is not None:
        warnings.append(
            f"Capital gains entered for {settings.stale_capital_gains_year} were not "
            f"applied: this plan starts in {state.year}. Update the gains already "
            f"realized in {state.year}, and any loss carried into it, in the plan's "
            "Income & Social Security step."
        )

    # Success-probability caveat.
    if float(winner.success_probability) < 0.8:
        warnings.append(
            "Warning: the recommended strategy funds spending in fewer than 80% of the "
            "simulated market paths. Consider reducing spending, increasing savings, or "
            "adjusting asset allocation."
        )


    return yearly_plan, winning_policy, alternative_policies, warnings


def run_optimization(
    state: State,
    engines: Engines,
    settings: Settings,
    constraints: Constraints,
    monte_carlo_runs: int = 300,
    seed: int = 42,
    forced_policy: str | None = None,
) -> dict:
    """Run the full optimization pipeline and return the result as a plain dict.

    This is the single Decimal→float conversion boundary.  Every numeric value
    in the returned dict is a Python float (or int for year/age fields).

    Parameters
    ----------
    state:
        Starting simulation state (not mutated).
    engines:
        Bundle of tax/benefit engines.  A memoized federal-engine wrapper is
        injected for the duration of this call.
    settings:
        Simulation configuration (simulation_years, nominal_return, etc.).
    constraints:
        Action constraints (conversion window, IRMAA policy, etc.).
    monte_carlo_runs:
        Number of stochastic return scenarios.  0 → deterministic passthrough.
    seed:
        Base random seed passed to ``score_policies_adaptive``.

    Returns
    -------
    dict with keys:
        status, computation_time_seconds, paths_evaluated, monte_carlo_runs,
        winning_policy, yearly_plan, alternative_policies, warnings.
    """
    # Every age is held fixed here: one left blank would drop that benefit.
    require_claim_ages(state, settings)
    t0 = time.monotonic()

    # Inject per-run memo cache for the federal engine.
    memo_federal = _MemoFederalEngine(engines.federal)
    engines_memo = dataclasses.replace(engines, federal=memo_federal)  # type: ignore[arg-type]

    # ── 1. Rule search ───────────────────────────────────────────────────────
    policies: list[Policy] = search(state, engines_memo, settings, constraints)

    # ── 2. Monte Carlo scores every policy ───────────────────────────────────
    # No cut by path_value: one expected-return path misranks in a predictable
    # direction (long schedules look better than on average). The staged budget
    # in score_policies_adaptive bounds the cost instead. History:
    # docs/OPTIMIZER_HISTORY.md, "The Monte Carlo cut and why it was removed".
    mc_candidates = list(policies)

    # Forced-policy run: the requested policy must be scored (so the user can
    # inspect its full plan) alongside the search's own favorites for context.
    if forced_policy is not None:
        forced_matches = [p for p in policies if p.policy_id == forced_policy]
        if not forced_matches:
            available = sorted({p.policy_id for p in policies})
            return {
                "status": "error",
                "computation_time_seconds": time.monotonic() - t0,
                "paths_evaluated": len(policies),
                "monte_carlo_runs": monte_carlo_runs,
                "winning_policy": {},
                "yearly_plan": [],
                "alternative_policies": [],
                "warnings": [
                    f"Requested policy {forced_policy!r} is not available for "
                    f"these inputs (window/IRMAA filters may exclude it). "
                    f"Available: {', '.join(available)}."
                ],
            }
        mc_candidates = forced_matches + [
            p for p in mc_candidates if p.policy_id != forced_policy
        ]

    # Adaptive budget: score every candidate on a cheap slice, then carry only
    # the contenders to the full count by APPENDING to the same common paths,
    # so every finalist is measured on the same scenarios.
    scored: list[ScoredPolicy] = score_policies_adaptive(
        mc_candidates,
        state,
        engines_memo,
        settings,
        constraints,
        runs=monte_carlo_runs,
        seed=seed,
        # A forced policy is reported whatever its rank, so it is measured on
        # the full budget even when stage 1 would have eliminated it -- but
        # ranked where stage 1 put it, so `optimizer_pick` is unchanged.
        pinned=forced_policy,
        # `none`, the no-conversion baseline the result is compared against,
        # is always measured on the full budget and ranked with the
        # finalists: fully sampled, it can be the recommendation.
        contenders="none",
    )

    if not scored:
        # Degenerate edge case — no feasible policy found.
        return {
            "status": "error",
            "computation_time_seconds": time.monotonic() - t0,
            "paths_evaluated": 0,
            "monte_carlo_runs": monte_carlo_runs,
            "winning_policy": {},
            "yearly_plan": [],
            "alternative_policies": [],
            "warnings": ["No feasible policy found for the given inputs."],
        }

    winner: ScoredPolicy = scored[0]
    optimizer_pick_id: str = winner.policy.policy_id
    if forced_policy is not None:
        # The forced policy becomes the "winner" whose full plan is reported;
        # the search's own pick is kept for the caveat warning below.
        winner = next(
            sp for sp in scored if sp.policy.policy_id == forced_policy
        )

    # Exclude the reported winner by id (it is scored[0] in normal runs, but
    # can sit anywhere in the list when a policy was forced).
    runners_up = [
        sp for sp in scored if sp.policy.policy_id != winner.policy.policy_id
    ][:3]
    none_policy = next((p for p in policies if p.policy_id == "none"), None)
    mat = materiality(state)
    yearly_plan, winning_policy, alternative_policies, warnings = build_report(
        winner, runners_up, none_policy, state, engines, settings, mat,
    )
    none_scored = next((sp for sp in scored if sp.policy.policy_id == "none"), None)
    # Forced-policy caveat: this plan was requested, not recommended.
    if forced_policy is not None and forced_policy != optimizer_pick_id:
        start = float(state.balance_traditional)
        warnings.insert(0,
            f"Forced-policy run: this plan shows {policy_label(forced_policy, start)} as "
            f"requested. The optimizer's own pick for these inputs was "
            f"{policy_label(optimizer_pick_id, start)} (see Close alternatives for the comparison)."
        )

    t1 = time.monotonic()

    return {
        "status": "success",
        # Which objective produced "score". Runs saved before October 2026
        # have no such key: they scored -PV(taxes) + estate_weight·PV(estate)
        # less the shortfalls, and their stored priority label still applies.
        "objective": OBJECTIVE_ID,
        # Which tax tables are published and which were projected, and at what
        # rate. Absent on runs saved before projection existed (those froze
        # every table at its last published year).
        "tax_tables": _tax_tables(engines, settings),
        "computation_time_seconds": t1 - t0,
        "paths_evaluated": len(policies),
        "monte_carlo_runs": monte_carlo_runs,
        # How the market scenarios were drawn; absent on runs saved before
        # October 2026, which used the same model.
        "market_model": market_model(settings, monte_carlo_runs),
        # Level-dollar rules convert a share of this, so labels can name the amount.
        "starting_traditional_balance": float(state.balance_traditional),
        "winning_policy": winning_policy,
        "yearly_plan": yearly_plan,
        "alternative_policies": alternative_policies,
        # What converting adds at these claim ages: `none` against the plan on
        # the same paths. None when `none` was filtered out of the search.
        "baseline_no_conversion": (
            None if none_scored is None
            else _baseline_dict(winner, none_scored, mat, settings)
        ),
        # The gap treated as immaterial ("equivalent") in paired comparisons.
        "materiality": float(mat),
        "warnings": warnings,
        # The claim ages this run used (stored, or pinned by the request).
        "claim_ages": {
            "self": settings.ss_claim_age_self,
            "spouse": settings.ss_claim_age_spouse,
        },
        # None for normal runs; the requested policy id for forced runs.
        "forced_policy": forced_policy,
        # What the optimizer itself would choose on these inputs -- the
        # winner on a normal run, and on a forced run the pick the pinned
        # plan is being shown instead of. Structured rather than left to the
        # forced-run warning, which is absent when the two coincide.
        "optimizer_pick": optimizer_pick_id,
    }
