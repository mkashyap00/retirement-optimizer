"""Social Security claim-age scenarios: which ages each person may claim at,
and the inputs each claim pair runs under.

A claim-age scenario changes Settings (the claim ages the simulator activates
benefits at) and ONE field of the starting State: this year's household
benefit, ``State.social_security``. Every year after the first re-derives the
benefit from Settings (transition.py Step 0), but year 0's conversion
candidates, the ``pre_ss`` window and the baseline-income bracket room all
read the State field directly, so a scenario that left it alone would size
year 0 for the stored claim ages.

Historical MAGI (``magi_two_years_ago``, ``magi_last_year``) is NOT
recomputed: a claim made in the future cannot change income already earned.
The proxy those fields hold was built from the stored claim ages, which is
the approximation the result discloses.

Eligibility rules (``claim_age_options``):

- No PIA: no claim-age dimension. Searching such a person is an input error
  ("enter a PIA, 0 if none"); an explicit 0 PIA is a real dimension, because a
  spousal benefit can still depend on when that person files.
- Already receiving: locked to the stored (actual) claim age.
- 70 or older and not receiving: only "file now", credited at 70.
- Otherwise every age from max(62, today's age) to 70, less the ages where
  that person's salary (or a joint salary) is still being paid in a year
  between the claim and full retirement age — the earnings test would
  withhold benefits the model does not track.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import Literal

from src.data.tax_rules.social_security import full_retirement_age
from src.optimization.search import Policy
from src.optimization.state import Engines, Settings, State
from src.optimization.transition import household_social_security

_ZERO = Decimal("0")
MIN_CLAIM_AGE = 62
MAX_CLAIM_AGE = 70

Person = Literal["self", "spouse"]


class ClaimInputError(ValueError):
    """Claim-age inputs that contradict each other or cannot be searched.

    Endpoints report it as HTTP 422 with the message as the detail.
    """


@dataclass(frozen=True)
class AgeControl:
    """How one person's claim age is chosen.

    ``fixed`` uses *age* (or the stored claim age when *age* is None);
    ``search`` tries every eligible age.
    """

    mode: Literal["fixed", "search"] = "fixed"
    age: int | None = None


@dataclass(frozen=True)
class ClaimControls:
    self_age: AgeControl = AgeControl()
    spouse_age: AgeControl = AgeControl()


@dataclass(frozen=True)
class Exclusion:
    person: Person
    age: int
    reason: str


@dataclass(frozen=True)
class ClaimScenario:
    """One claim pair and the inputs it runs under.

    ``eligible=False`` marks the entered-age scenario when one of its ages is
    excluded: it is scored as a labeled diagnostic baseline and never wins.
    """

    claim_age_self: int | None
    claim_age_spouse: int | None
    state: State
    settings: Settings
    key: str
    eligible: bool = True
    # The ages the user entered (or fixed): what "benefit of choosing claim
    # ages" is measured against.
    entered: bool = False


@dataclass(frozen=True)
class Candidate:
    """A conversion policy under one claim scenario."""

    scenario: ClaimScenario
    policy: Policy

    @property
    def key(self) -> str:
        return f"{self.policy.policy_id}@{self.scenario.key}"


def scenario_key(claim_age_self: int | None, claim_age_spouse: int | None) -> str:
    """``"67-65"``; a person with no claim-age dimension shows as ``-``."""
    def fmt(age: int | None) -> str:
        return "-" if age is None else str(age)

    return f"{fmt(claim_age_self)}-{fmt(claim_age_spouse)}"


def _person_fields(settings: Settings, state: State, person: Person):
    """(pia, stored claim age, receiving flag, today's age, birth year)."""
    if person == "self":
        return (settings.ss_pia_self, settings.ss_claim_age_self,
                settings.ss_receiving_self, state.age_self, settings.birth_year_self)
    return (settings.ss_pia_spouse, settings.ss_claim_age_spouse,
            settings.ss_receiving_spouse, state.age_spouse, settings.birth_year_spouse)


def receiving_error(
    person: Person, age: int | None, claim_age: int | None, receiving: bool | None
) -> str | None:
    """Why a stored claim age contradicts the receiving flag, or None.

    Shared by input validation and assembly, and applied to fixed-age runs as
    well as the claim-age search.
    """
    if receiving and claim_age is None:
        return (
            f"{person} is marked as already receiving Social Security; enter the "
            f"age their benefits started"
        )
    if receiving is None or age is None or claim_age is None:
        return None
    if receiving and claim_age > age:
        return (
            f"{person} is marked as already receiving Social Security, but the "
            f"claim age {claim_age} is later than their age today ({age}); "
            f"enter the age they actually claimed"
        )
    if not receiving and claim_age < min(age, MAX_CLAIM_AGE):
        return (
            f"{person} is marked as not yet receiving Social Security, but the "
            f"claim age {claim_age} is earlier than their age today ({age}); "
            f"enter a claim age of {min(age, MAX_CLAIM_AGE)} or later, or mark "
            f"them as receiving"
        )
    return None


def missing_claim_people(state: State, settings: Settings) -> list[Person]:
    """People with a benefit entered but no claim age: a run that holds their
    age fixed has none to use. A claim-age search may leave one out (the age
    is then only searched, with no comparison age); nothing else may."""
    out: list[Person] = []
    for person in ("self", "spouse"):
        pia, claim, _, age, _ = _person_fields(settings, state, person)
        if pia is not None and claim is None and age is not None:
            out.append(person)
    return out


def require_claim_ages(state: State, settings: Settings) -> None:
    """Refuse a fixed-age run with a claim age missing: modelling it would
    silently drop that person's benefit."""
    missing = missing_claim_people(state, settings)
    if missing:
        who = " and ".join("you" if p == "self" else "your spouse" for p in missing)
        raise ClaimInputError(
            f"choose a Social Security claim age for {who}, or let the optimizer "
            f"find the best one"
        )


def legacy_inference_people(state: State, settings: Settings) -> list[Person]:
    """People whose receiving flag is unknown and whose age has reached the
    stored claim age: their benefit is inferred as already being paid."""
    out: list[Person] = []
    for person in ("self", "spouse"):
        pia, claim, receiving, age, _ = _person_fields(settings, state, person)
        if pia is not None and claim is not None and age is not None:
            if receiving is None and age >= claim:
                out.append(person)
    return out


def assumed_filing_people(state: State, settings: Settings) -> list[Person]:
    """People over 70 who have not filed: modelled as filing this year, at
    the age-70 benefit. An assumption, not a historical claim."""
    out: list[Person] = []
    for person in ("self", "spouse"):
        pia, claim, receiving, age, _ = _person_fields(settings, state, person)
        if pia is not None and receiving is False and age is not None and age > MAX_CLAIM_AGE:
            out.append(person)
    return out


def _salary_overlap(
    settings: Settings, person: Person, birth_year: int, claim_age: int
) -> tuple[int, int] | None:
    """First and last year a salary (the person's or joint) is paid between
    the claim year and the FRA year, or None."""
    claim_year = birth_year + claim_age
    fra_year = birth_year + math.ceil(full_retirement_age(birth_year))
    years: list[int] = []
    for entry in settings.income_schedule:
        if entry.category != "salary" or entry.owner not in (person, "joint"):
            continue
        if entry.amount <= _ZERO:
            continue
        lo = claim_year if entry.start_year is None else max(claim_year, entry.start_year)
        hi = fra_year - 1 if entry.end_year is None else min(fra_year - 1, entry.end_year)
        if lo <= hi:
            years.extend((lo, hi))
    return (min(years), max(years)) if years else None


def claim_age_options(
    person: Person, state: State, settings: Settings, mode: str = "search"
) -> tuple[list[int], list[Exclusion]]:
    """The ages *person* may claim at, and the ages excluded with a reason.

    An empty list means the person has no claim-age dimension (no PIA, or no
    spouse). See the module docstring for the rules.
    """
    pia, claim, receiving, age, birth_year = _person_fields(settings, state, person)
    if age is None:
        return [], []
    if pia is None:
        if mode == "search":
            raise ClaimInputError(
                f"enter a Social Security PIA for {person} (0 if none) to search "
                f"their claim age"
            )
        return [], []
    if receiving is True:
        return [claim], []
    if age >= MAX_CLAIM_AGE:
        return [MAX_CLAIM_AGE], []

    ages: list[int] = []
    exclusions: list[Exclusion] = []
    for a in range(max(MIN_CLAIM_AGE, age), MAX_CLAIM_AGE + 1):
        overlap = _salary_overlap(settings, person, birth_year, a) if birth_year else None
        if overlap is None:
            ages.append(a)
        else:
            lo, hi = overlap
            span = str(lo) if lo == hi else f"{lo}–{hi}"
            exclusions.append(
                # Left out of the SEARCH, not prohibited: the model does not
                # apply the earnings test, so a claim it would reduce is skipped.
                Exclusion(person, a, f"salary paid {span}, before full retirement age")
            )
    return ages, exclusions


def with_claim_ages(
    state: State,
    settings: Settings,
    engines: Engines,
    claim_age_self: int | None,
    claim_age_spouse: int | None,
) -> tuple[State, Settings]:
    """The inputs under these claim ages (None keeps the stored age).

    Only the claim ages on Settings and year-0 ``State.social_security``
    change; balances, income and the MAGI look-back are identical in every
    scenario.
    """
    changes: dict = {}
    if claim_age_self is not None:
        changes["ss_claim_age_self"] = claim_age_self
    if claim_age_spouse is not None:
        changes["ss_claim_age_spouse"] = claim_age_spouse
    if not changes:
        return state, settings
    new_settings = dataclasses.replace(settings, **changes)
    ss = household_social_security(
        engines.ss, new_settings, state.age_self, state.age_spouse, state.year
    )
    new_state = state if ss is None else dataclasses.replace(state, social_security=ss)
    return new_state, new_settings


def claim_age_preview(state: State, settings: Settings) -> dict[Person, dict | None]:
    """What a claim-age search would do for each person, before it runs.

    The wizard and the run setup show this, so the interface and the search
    apply one set of rules. ``status``: ``searchable`` (``ages`` are the
    eligible ones, ``exclusions`` the skipped ones), ``receiving`` (the age is
    the one already claimed and stays fixed), ``assumed_70`` (over 70, not
    yet filed: modelled as filing now), ``no_benefit`` (no PIA entered),
    ``needs_answer`` (receiving unknown and the claim age has passed) or
    ``invalid`` (the inputs contradict each other). ``None`` = no spouse.
    """
    out: dict[Person, dict | None] = {}
    for person in ("self", "spouse"):
        pia, claim, receiving, age, _ = _person_fields(settings, state, person)
        if age is None:
            out[person] = None
            continue
        row: dict = {"age": age, "entered_age": claim, "receiving": receiving,
                     "pia": None if pia is None else float(pia),
                     "ages": [], "exclusions": [], "message": None}
        err = receiving_error(person, age, claim, receiving)
        if err:
            row.update(status="invalid", message=err)
        elif pia is None:
            row.update(status="no_benefit",
                       message="No Social Security benefit entered, so there is no age to choose.")
        elif claim is not None and receiving is None and age >= claim:
            row.update(status="needs_answer", message=(
                f"Say whether benefits have started: the planned claim age {claim} "
                f"has been reached."))
        elif receiving:
            row.update(status="receiving", ages=[claim], message=(
                f"Already receiving since {claim}: a claim already made is not searched."))
        elif age >= MAX_CLAIM_AGE:
            row.update(status="assumed_70", ages=[MAX_CLAIM_AGE], message=(
                "Over 70 and not yet receiving: modelled as filing this year at the "
                "age-70 benefit."))
        else:
            ages, excl = claim_age_options(person, state, settings, "search")
            row.update(status="searchable", ages=ages,
                       exclusions=[{"age": e.age, "reason": e.reason} for e in excl])
        out[person] = row
    return out


def _check_searchable(person: Person, state: State, settings: Settings) -> None:
    pia, claim, receiving, age, _ = _person_fields(settings, state, person)
    if pia is None or claim is None or age is None:
        return
    if receiving is None and age >= claim:
        raise ClaimInputError(
            f"confirm whether {person} is already receiving Social Security: "
            f"they are {age} and the stored claim age is {claim}"
        )


def enumerate_scenarios(
    state: State,
    settings: Settings,
    engines: Engines,
    controls: ClaimControls,
) -> tuple[list[ClaimScenario], list[Exclusion]]:
    """Every claim pair to run, and the ages excluded from the search.

    The cartesian product of each person's eligible ages (a fixed person
    contributes one age). The entered-age scenario is included whenever every
    person with a claim-age dimension has an entered age; when it uses an
    excluded age it is ``eligible=False``. A searched person may have no
    entered age: then there is no entered-age scenario, and no comparison with
    "your ages" -- none is invented.
    """
    for person in ("self", "spouse"):
        _check_searchable(person, state, settings)

    dims: dict[Person, list[int | None]] = {}
    entered: dict[Person, int | None] = {}
    exclusions: list[Exclusion] = []
    for person, control in (("self", controls.self_age), ("spouse", controls.spouse_age)):
        pia, claim, _, _, _ = _person_fields(settings, state, person)
        ages, excl = claim_age_options(person, state, settings, control.mode)
        if not ages:
            dims[person], entered[person] = [None], None
            continue
        if control.mode == "search":
            dims[person] = list(ages)
            exclusions.extend(excl)
            entered[person] = claim
        else:
            fixed = control.age if control.age is not None else claim
            if fixed is None:
                raise ClaimInputError(
                    f"choose a Social Security claim age for {person}, or search it"
                )
            dims[person], entered[person] = [fixed], fixed
            if fixed not in ages:
                exclusions.extend(e for e in excl if e.age == fixed)

    excluded = {(e.person, e.age) for e in exclusions}
    pairs = list(product(dims["self"], dims["spouse"]))
    entered_pair = (entered["self"], entered["spouse"])
    has_entered = all(entered[p] is not None or dims[p] == [None] for p in dims)
    if has_entered and entered_pair not in pairs:
        pairs.append(entered_pair)

    scenarios: list[ClaimScenario] = []
    for a_self, a_spouse in pairs:
        eligible = (
            ("self", a_self) not in excluded and ("spouse", a_spouse) not in excluded
            and (a_self in dims["self"]) and (a_spouse in dims["spouse"])
        )
        s_state, s_settings = with_claim_ages(state, settings, engines, a_self, a_spouse)
        scenarios.append(ClaimScenario(
            claim_age_self=a_self, claim_age_spouse=a_spouse,
            state=s_state, settings=s_settings,
            key=scenario_key(a_self, a_spouse), eligible=eligible,
            entered=has_entered and (a_self, a_spouse) == entered_pair,
        ))
    return scenarios, exclusions


def check_pinned_ages(
    state: State, settings: Settings, claim_age_self: int | None, claim_age_spouse: int | None
) -> None:
    """A run pinned to explicit claim ages must use eligible ones."""
    for person, age in (("self", claim_age_self), ("spouse", claim_age_spouse)):
        if age is None:
            continue
        ages, excl = claim_age_options(person, state, settings, "search")
        if age in ages:
            continue
        reason = next((e.reason for e in excl if e.age == age), None)
        raise ClaimInputError(
            f"claim age {age} is not available for {person}"
            + (f": {reason}" if reason else f" (options: {ages})")
        )
