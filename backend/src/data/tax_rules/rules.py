"""TaxRules facade — single entry point for all tax-rule data.

Every projection engine in Plan 03 depends only on this class; the underlying
data modules (federal, irmaa, rmd, state) are implementation details.

Years beyond the latest published data:
  * with an ``inflation`` rate (what the simulator always passes) the table is
    PROJECTED from the latest published one — see ``indexing`` for the rule
    each provision follows. Projections are cached per (year, rate) on this
    instance and never mutate the published tables.
  * with ``inflation=None`` the latest published table is returned unchanged
    (the legacy clamp) and a WARNING is logged once per unknown year.
Published years are always returned as published.
"""
from __future__ import annotations

import logging
import threading
from decimal import Decimal

from . import indexing
from .federal import FEDERAL
from .irmaa import IRMAA
from .rmd import RMD_START_AGE, UNIFORM_LIFETIME, applicable_rmd_age
from .state import known_state_years as _known_state_years
from .state import latest_state_year as _latest_state_year
from .state import state_brackets as _state_brackets
from .state import state_standard_deduction as _state_standard_deduction
from .types import Bracket, FederalTaxYear, IrmaaYear

logger = logging.getLogger(__name__)


class TaxRules:
    """Facade providing validated access to all tax-rule data tables.

    Instantiate once and inject everywhere — the object is stateless except
    for its "warned years" deduplication sets.
    """

    def __init__(
        self,
        federal: dict[int, FederalTaxYear] | None = None,
        irmaa: dict[int, IrmaaYear] | None = None,
    ) -> None:
        # Allow injection for testing; fall back to shipped data.
        self._federal_data: dict[int, FederalTaxYear] = federal if federal is not None else FEDERAL
        self._irmaa_data: dict[int, IrmaaYear] = irmaa if irmaa is not None else IRMAA

        # Track which future years have already received a warning so that
        # multi-year simulation loops don't flood the log.
        self._warned_federal: set[int] = set()
        self._warned_irmaa: set[int] = set()
        self._warned_state: set[int] = set()
        # Projected tables, keyed (kind, year, rate[, state, status]). One
        # instance is shared by every request and the worker thread, so writes
        # go through a lock; reads of an existing entry are lock-free.
        self._projected: dict[tuple, object] = {}
        self._lock = threading.Lock()

    def _cached(self, key: tuple, build):
        hit = self._projected.get(key)
        if hit is None:
            with self._lock:
                hit = self._projected.get(key)
                if hit is None:
                    hit = build()
                    self._projected[key] = hit
        return hit

    def published_through(self) -> dict[str, int]:
        """Latest published year per table — what a result's provenance cites."""
        return {
            "federal": self.latest_federal_year(),
            "irmaa": max(self._irmaa_data),
            "state": _latest_state_year(),
        }

    # ------------------------------------------------------------------
    # Federal
    # ------------------------------------------------------------------

    def federal(self, year: int, inflation: Decimal | None = None) -> FederalTaxYear:
        """Return the FederalTaxYear for *year*.

        A published year is returned as published. A later year is projected at
        *inflation* from the latest published year; with ``inflation=None`` the
        latest year is returned unchanged with a one-time WARNING.
        """
        if year in self._federal_data:
            return self._federal_data[year]

        latest = self.latest_federal_year()
        if inflation is not None and year > latest:
            return self._cached(
                ("federal", year, inflation),
                lambda: indexing.project_federal_year(
                    self._federal_data[latest], year, inflation
                ),
            )
        if year not in self._warned_federal:
            logger.warning(
                "Federal tax data for year %d is not available; "
                "clamping to latest known year %d.",
                year,
                latest,
            )
            self._warned_federal.add(year)
        return self._federal_data[latest]

    def latest_federal_year(self) -> int:
        """Return the most recent year for which federal tax data is available."""
        return max(self._federal_data)

    # ------------------------------------------------------------------
    # IRMAA
    # ------------------------------------------------------------------

    def irmaa(self, premium_year: int, inflation: Decimal | None = None) -> IrmaaYear:
        """Return the IrmaaYear for *premium_year* (the year premiums are paid;
        its thresholds apply to MAGI from premium_year − 2).

        A published year is returned as published; a later one is projected at
        *inflation* (thresholds only), or clamped with a one-time WARNING when
        ``inflation`` is None.
        """
        if premium_year in self._irmaa_data:
            return self._irmaa_data[premium_year]

        latest = max(self._irmaa_data)
        if inflation is not None and premium_year > latest:
            return self._cached(
                ("irmaa", premium_year, inflation),
                lambda: indexing.project_irmaa_year(
                    self._irmaa_data[latest], premium_year, inflation
                ),
            )
        if premium_year not in self._warned_irmaa:
            logger.warning(
                "IRMAA data for year %d is not available; "
                "clamping to latest known year %d.",
                premium_year,
                latest,
            )
            self._warned_irmaa.add(premium_year)
        return self._irmaa_data[latest]

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _warn_state_year(self, year: int | None) -> None:
        if (
            year is not None
            and year not in _known_state_years()
            and year not in self._warned_state
        ):
            self._warned_state.add(year)
            logger.warning(
                "State tax data for year %d is not available; "
                "clamping to latest known year %d.",
                year,
                _latest_state_year(),
            )

    def _state_projects(self, state: str, year: int | None, inflation) -> bool:
        return (
            inflation is not None
            and year is not None
            and year > _latest_state_year()
            and state.upper() in indexing.INDEXED_STATES
        )

    def state_brackets(
        self, state: str, filing_status: str, year: int | None = None,
        inflation: Decimal | None = None,
    ) -> list[Bracket]:
        """Return state income-tax brackets for *state* (2-letter USPS code)
        and *filing_status* ('single' or 'joint') for *year* (None = latest).

        Beyond the latest CSV: a modelled state (``indexing.INDEXED_STATES``)
        is projected at *inflation*; any other state, or a call without
        *inflation*, keeps the latest CSV (with a once-per-year warning when
        no rate was given).

        Returns [] for no-income-tax states and unknown state codes.
        """
        if self._state_projects(state, year, inflation):
            base_year = _latest_state_year()
            return self._cached(
                ("state_brackets", year, inflation, state.upper(), filing_status),
                lambda: indexing.project_state_brackets(
                    state, _state_brackets(state, filing_status, base_year),
                    base_year, year, inflation,
                ),
            )
        if inflation is None:
            self._warn_state_year(year)
        return _state_brackets(state, filing_status, year)

    def state_standard_deduction(
        self, state: str, filing_status: str, year: int | None = None,
        inflation: Decimal | None = None,
    ) -> Decimal:
        """Return the state standard deduction (Decimal) for *state* and
        *filing_status* for *year* (projection and clamping as in
        :meth:`state_brackets`). Returns Decimal('0') when not applicable.
        """
        if self._state_projects(state, year, inflation):
            base_year = _latest_state_year()
            return self._cached(
                ("state_deduction", year, inflation, state.upper(), filing_status),
                lambda: indexing.project_state_deduction(
                    state, _state_standard_deduction(state, filing_status, base_year),
                    base_year, year, inflation,
                ),
            )
        if inflation is None:
            self._warn_state_year(year)
        return _state_standard_deduction(state, filing_status, year)

    # ------------------------------------------------------------------
    # RMD
    # ------------------------------------------------------------------

    def rmd_factor(self, age: int, birth_year: int | None = None) -> Decimal:
        """Return the IRS Uniform Lifetime Table distribution period for *age*.

        Returns Decimal('0') below the RMD start age. When *birth_year* is
        given the SECURE 2.0 §107 applicable age applies (73 for the 1951-1959
        cohort, 75 for 1960 and later); without it the legacy flat 73 is used.
        Ages above 120 (the table's highest entry) are clamped to 120.
        """
        start_age = RMD_START_AGE if birth_year is None else applicable_rmd_age(birth_year)
        if age < start_age:
            return Decimal("0")
        # Clamp to table maximum
        clamped_age = min(age, max(UNIFORM_LIFETIME))
        return UNIFORM_LIFETIME[clamped_age]
