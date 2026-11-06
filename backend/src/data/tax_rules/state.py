"""State income tax brackets and related data for TY2025.

Data source: state_brackets_2025.csv (Tax Foundation / state DOR pages, 2025 edition).

CSV format: two-row header; one row per bracket (lower-bound convention);
  state name appears only on the first row of each state block; no-tax states
  marked "none"; deductions in the last two columns.

Parsing decisions:
  - Lower-bound rows (">  $X at R%") are converted to upper-bound Bracket(upper, rate).
  - States whose first bracket starts above $0 (ND, OH, MS) get a synthetic
    Bracket(first_lower, Decimal("0")) prepended.
  - Washington's "7.0% on capital gains income only" is not a general income tax;
    WA is treated as no-income-tax and returns [].
  - Utah's deduction column contains "$900 credit" / "$1,800 credit" — credits
    are not standard deductions; state_standard_deduction("UT", …) returns 0.
  - "Lousiana" typo in CSV is mapped to LA.
  - District of Columbia is mapped to "DC".
  - NJ has asymmetric bracket counts (7 single / 8 joint) due to an extra
    joint-only row in the CSV; the parser handles this naturally.
  - California rows hold ONLY the ordinary schedule (FTB 2025 Schedules X and
    Y, verified 2026-10-16 against ftb.ca.gov/forms/2025/2025-540-tax-rate-
    schedules.pdf; standard deduction $5,706 / $11,412 from the FTB deduction
    page). The 1% Mental Health Services Tax is NOT in the ladder: it is a
    separate surcharge with its own fixed threshold (STATE_SURCHARGES), so the
    ordinary brackets can be indexed without moving it. The previous rows
    were the 2024 schedule with the surcharge merged into the ladder.

STATES_TAXING_SS: verified 2026-07-02 via:
  - https://money.com/social-security-state-taxes-2026/
  - https://bogartwealth.com/social-security-taxes-by-state/
  WV: fully exempt from 2026 (completed 3-year phase-out that began in 2024).
  MO, NE, KS: exempt since tax year 2024.
  Remaining states that tax SS as of 2026: CO, CT, MN, MT, NM, RI, UT, VT.
"""
import csv
import pathlib
from decimal import Decimal

from .types import Bracket

_DATA_DIR = pathlib.Path(__file__).parent

# Full state name (as it appears in the CSV, stripped) → 2-letter USPS code.
# "Lousiana" (CSV typo) is included alongside the correct spelling.
_NAME_TO_CODE: dict[str, str] = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Lousiana": "LA",  # CSV typo
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "District of Columbia": "DC",
}

# States with no general state income tax.
# Washington has a 7% capital-gains tax but no general income tax; treated as no-tax here.
# Every code the tax tables cover: the 50 states and DC. Anything else would
# silently get no state tax, so the API rejects it.
SUPPORTED_STATES: frozenset[str] = frozenset(_NAME_TO_CODE.values())

NO_TAX_STATES: frozenset[str] = frozenset({
    "AK", "FL", "NH", "NV", "SD", "TN", "TX", "WA", "WY",
})

# States that tax Social Security benefits as of tax year 2026.
# Verified 2026-07-02:
#   https://money.com/social-security-state-taxes-2026/
#   https://bogartwealth.com/social-security-taxes-by-state/
# WV fully exempt from 2026 (3-year phase-out complete).
# MO, NE, KS exempt since 2024.
STATES_TAXING_SS: dict[str, str] = {
    "CO": "under 65 only",
    "CT": "income-limited",
    "MN": "income-limited",
    "MT": "taxed",
    "NM": "high income only",
    "RI": "income-limited",
    "UT": "credit offset",
    "VT": "income-limited",
}


# Flat surcharges on state taxable income above a FIXED threshold, applied on
# top of the ordinary schedule. Kept out of the bracket ladder because the
# threshold is not inflation-indexed while the ordinary brackets are.
#   CA: Mental Health Services Tax, R&TC §17043 — 1% of taxable income over
#   $1,000,000, the same threshold for every filing status.
STATE_SURCHARGES: dict[str, tuple[Decimal, Decimal]] = {
    "CA": (Decimal("1000000"), Decimal("0.01")),
}


# How a state treats a net capital loss. Unlisted states start from federal
# adjusted gross income and keep the federal result: the federal $3,000
# deduction and the federal carryover (e.g. New York, whose IT-201 lines 1-19
# are the federal return's amounts).
#   "separate": the state nets the same gains with a $3,000 limit and figures
#       its own carryover on state income.
#     CA: Schedule D (540) and its Capital Loss Carryover Worksheet, on Form
#         540 lines 17-18.
#     WI: Schedule WD; the limit rose from $500 to $3,000 from tax year 2023,
#         and the Wisconsin carryover can differ from the federal one
#         (Publication 103, sections 2.B and 3.B).
#   "none": losses offset gains of the same year only; no deduction against
#       other income and no carryover.
#     PA: PA Personal Income Tax Guide, "Net Gains or Income from the Sale,
#         Exchange or Disposition of Property".
#     NJ: NJ-1040 instructions, net gains or income from disposition of
#         property: a net loss is entered as zero and does not carry over.
# Not modelled: other states with their own capital-gain rules (e.g.
# Massachusetts, Arkansas) are treated as federal.
STATE_CAPITAL_LOSS_RULES: dict[str, str] = {
    "CA": "separate",
    "WI": "separate",
    "PA": "none",
    "NJ": "none",
}


def _parse_rate(s: str) -> Decimal | None:
    """Parse '2.00%' → Decimal('0.02').  Returns None for empty / 'none' / unrecognised."""
    s = s.strip()
    if not s or s.lower() == "none":
        return None
    pct_idx = s.find("%")
    if pct_idx < 0:
        return None
    try:
        return Decimal(s[:pct_idx].strip()) / Decimal("100")
    except Exception:
        return None


def _parse_money(s: str) -> Decimal | None:
    """Parse '$3,000 ' → Decimal('3000').  Returns None for n.a./none/credit entries."""
    s = s.strip()
    if not s or s.lower() in ("n.a.", "n/a", "none", "n.a"):
        return None
    if "credit" in s.lower():
        # Utah uses "$900 credit" — a credit, not a deduction; treat as None.
        return None
    s = s.replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def _lower_to_upper(raw: list[tuple[Decimal, Decimal]]) -> list[Bracket]:
    """Convert (lower_bound, rate) pairs to Bracket(upper, rate) list.

    If the lowest lower_bound is > 0, a synthetic 0% bracket is prepended so
    that the brackets cover the full income range from $0.
    """
    if not raw:
        return []
    raw_sorted = sorted(raw, key=lambda x: x[0])
    result: list[Bracket] = []
    # Prepend implicit 0% bracket when the first bracket starts above $0
    if raw_sorted[0][0] > Decimal("0"):
        result.append(Bracket(upper=raw_sorted[0][0], rate=Decimal("0")))
    for i, (_lower, rate) in enumerate(raw_sorted):
        if i + 1 < len(raw_sorted):
            result.append(Bracket(upper=raw_sorted[i + 1][0], rate=rate))
        else:
            result.append(Bracket(upper=None, rate=rate))
    return result


def _parse_csv(csv_path: pathlib.Path) -> tuple[
    dict[tuple[str, str], list[Bracket]],
    dict[tuple[str, str], Decimal],
]:
    """Parse one year's CSV; return (bracket_data, deduction_data).

    Keys are (state_code, filing_status) where filing_status is 'single' or 'joint'.
    """
    with open(csv_path, encoding="utf-8-sig") as f:
        all_rows: list[list[str]] = list(csv.reader(f))

    # Group rows by state.  The CSV has two header rows; skip them.
    # Each state block starts with a non-empty cell in column 0.
    state_blocks: list[tuple[str, list[list[str]]]] = []
    current_name: str | None = None
    current_rows: list[list[str]] = []

    for row in all_rows[2:]:
        # Pad to at least 9 columns
        row = list(row) + [""] * max(0, 9 - len(row))
        state_cell = row[0].strip()
        if state_cell:
            if current_name is not None:
                state_blocks.append((current_name, current_rows))
            current_name = state_cell
            current_rows = [row]
        elif current_name is not None:
            current_rows.append(row)

    if current_name is not None:
        state_blocks.append((current_name, current_rows))

    brackets_data: dict[tuple[str, str], list[Bracket]] = {}
    deduction_data: dict[tuple[str, str], Decimal] = {}

    for state_name, rows in state_blocks:
        code = _NAME_TO_CODE.get(state_name)
        if code is None:
            continue  # unrecognised state name — skip

        first_row = rows[0]
        single_rate_str = first_row[1].strip()

        # No-income-tax state (marker "none" or in the explicit set)
        if single_rate_str.lower() == "none" or code in NO_TAX_STATES:
            brackets_data[(code, "single")] = []
            brackets_data[(code, "joint")] = []
            deduction_data[(code, "single")] = Decimal("0")
            deduction_data[(code, "joint")] = Decimal("0")
            continue

        # Standard deductions (first row only; "n.a." or "credit" → 0)
        single_ded = _parse_money(first_row[7])
        joint_ded = _parse_money(first_row[8])
        deduction_data[(code, "single")] = single_ded if single_ded is not None else Decimal("0")
        deduction_data[(code, "joint")] = joint_ded if joint_ded is not None else Decimal("0")

        # Collect lower-bound bracket rows
        raw_single: list[tuple[Decimal, Decimal]] = []
        raw_joint: list[tuple[Decimal, Decimal]] = []

        for row in rows:
            s_rate = _parse_rate(row[1])
            s_lb = _parse_money(row[3])
            j_rate = _parse_rate(row[4])
            j_lb = _parse_money(row[6])

            if s_rate is not None and s_lb is not None:
                raw_single.append((s_lb, s_rate))
            if j_rate is not None and j_lb is not None:
                raw_joint.append((j_lb, j_rate))

        brackets_data[(code, "single")] = _lower_to_upper(raw_single)
        brackets_data[(code, "joint")] = _lower_to_upper(raw_joint)

    return brackets_data, deduction_data


# ---------------------------------------------------------------------------
# Year-keyed module cache — one entry per state_brackets_YYYY.csv, parsed
# once at import time. Update path: drop a new year's CSV (Tax Foundation
# publishes the 50-state table annually) next to this file; nothing else
# changes. Years beyond the latest CSV clamp to the latest (the TaxRules
# facade emits the once-per-year warning, mirroring the federal policy).
# ---------------------------------------------------------------------------


def _discover_years() -> dict[int, pathlib.Path]:
    out: dict[int, pathlib.Path] = {}
    for path in _DATA_DIR.glob("state_brackets_*.csv"):
        try:
            out[int(path.stem.rsplit("_", 1)[1])] = path
        except ValueError:
            continue
    return out


_BY_YEAR: dict[
    int,
    tuple[dict[tuple[str, str], list[Bracket]], dict[tuple[str, str], Decimal]],
] = {year: _parse_csv(path) for year, path in _discover_years().items()}
_LATEST_YEAR = max(_BY_YEAR)


def known_state_years() -> set[int]:
    """Return the tax years for which a state CSV exists."""
    return set(_BY_YEAR)


def latest_state_year() -> int:
    """Return the most recent tax year with state data."""
    return _LATEST_YEAR


def _data_for(year: int | None) -> tuple[
    dict[tuple[str, str], list[Bracket]], dict[tuple[str, str], Decimal]
]:
    if year is not None and year in _BY_YEAR:
        return _BY_YEAR[year]
    return _BY_YEAR[_LATEST_YEAR]


def state_brackets(
    state: str, filing_status: str, year: int | None = None
) -> list[Bracket]:
    """Return income-tax brackets for *state* (2-letter code) and *filing_status*.

    *filing_status* is "single" or "joint". *year* selects that year's CSV
    when present, else clamps to the latest known year (None = latest).
    Returns [] for no-income-tax states and for unknown state codes.
    """
    brackets, _ = _data_for(year)
    return brackets.get((state.upper(), filing_status.lower()), [])


def state_standard_deduction(
    state: str, filing_status: str, year: int | None = None
) -> Decimal:
    """Return state standard deduction for *state* and *filing_status*.

    *year* behaves as in :func:`state_brackets`. Returns Decimal("0") when
    the state has no standard deduction, no income tax, or the state code
    is unknown.
    """
    _, deductions = _data_for(year)
    return deductions.get((state.upper(), filing_status.lower()), Decimal("0"))
