"""Tax data validator — structural integrity checks for all tax-rule data.

``validate_all()`` returns an empty list when all shipped data is healthy.
Each helper (``validate_federal_year``, ``validate_irmaa_year``,
``validate_rmd_table``) can be called independently to diagnose a specific
injected object, which makes unit-testing corruption detection straightforward.
"""
from __future__ import annotations

from decimal import Decimal

from .federal import FEDERAL
from .irmaa import IRMAA
from .rmd import UNIFORM_LIFETIME
from .types import FederalTaxYear, IrmaaYear

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_all(
    *,
    federal: dict[int, FederalTaxYear] | None = None,
    irmaa: dict[int, IrmaaYear] | None = None,
    rmd: dict[int, Decimal] | None = None,
) -> list[str]:
    """Run all structural checks on the tax-rule data.

    Parameters allow injecting alternative data for testing; when omitted the
    shipped module-level constants are used.

    Returns a list of issue strings.  An empty list means all checks passed.
    """
    federal_data = federal if federal is not None else FEDERAL
    irmaa_data = irmaa if irmaa is not None else IRMAA
    rmd_data = rmd if rmd is not None else UNIFORM_LIFETIME

    issues: list[str] = []

    # Federal
    for year, fy in federal_data.items():
        for issue in validate_federal_year(fy):
            issues.append(f"federal[{year}]: {issue}")

    # IRMAA
    for year, iy in irmaa_data.items():
        for issue in validate_irmaa_year(iy):
            issues.append(f"irmaa[{year}]: {issue}")

    # RMD
    for issue in validate_rmd_table(rmd_data):
        issues.append(f"rmd: {issue}")

    return issues


# ---------------------------------------------------------------------------
# Per-object validators
# ---------------------------------------------------------------------------


def validate_federal_year(fy: FederalTaxYear) -> list[str]:
    """Return a list of structural issues found in a single FederalTaxYear."""
    issues: list[str] = []

    # Source must be non-empty and must not contain placeholder flags.
    if not fy.source or not fy.source.strip():
        issues.append("source is empty")
    elif "PENDING" in fy.source.upper():
        issues.append(f"source contains 'PENDING': {fy.source!r}")
    elif "VERIFY" in fy.source.upper():
        issues.append(f"source contains 'VERIFY': {fy.source!r}")

    # Ordinary income brackets
    for status, brackets in fy.brackets.items():
        issues.extend(_check_ordinary_brackets(brackets, label=f"brackets[{status!r}]"))

    # LTCG brackets
    for status, brackets in fy.ltcg_brackets.items():
        issues.extend(_check_ltcg_brackets(brackets, label=f"ltcg_brackets[{status!r}]"))

    # Standard deductions
    for status, amount in fy.standard_deduction.items():
        if amount <= Decimal("0"):
            issues.append(
                f"standard_deduction[{status!r}] must be > 0, got {amount}"
            )
    for status, amount in fy.aged_addition.items():
        if amount <= Decimal("0"):
            issues.append(f"aged_addition[{status!r}] must be > 0, got {amount}")

    return issues


def validate_irmaa_year(iy: IrmaaYear) -> list[str]:
    """Return a list of structural issues found in a single IrmaaYear."""
    issues: list[str] = []

    # Source checks
    if not iy.source or not iy.source.strip():
        issues.append("source is empty")
    elif "PENDING" in iy.source.upper():
        issues.append(f"source contains 'PENDING': {iy.source!r}")
    elif "VERIFY" in iy.source.upper():
        issues.append(f"source contains 'VERIFY': {iy.source!r}")

    for status, tiers in iy.tiers.items():
        label = f"tiers[{status!r}]"

        if not tiers:
            issues.append(f"{label}: empty tier list")
            continue

        # Tier 0 (lowest MAGI bracket) must have part_b == part_b_standard
        if tiers[0].part_b_monthly != iy.part_b_standard:
            issues.append(
                f"{label}[0].part_b_monthly {tiers[0].part_b_monthly} "
                f"!= part_b_standard {iy.part_b_standard}"
            )

        # MAGI upper bounds must strictly ascend (last tier upper is None)
        for i in range(len(tiers) - 1):
            curr_upper = tiers[i].magi_upper
            next_upper = tiers[i + 1].magi_upper

            if curr_upper is None:
                issues.append(
                    f"{label}[{i}].magi_upper is None but is not the last tier"
                )
                continue

            # All non-final tiers must have a numeric upper; final tier must be None
            if next_upper is not None and curr_upper >= next_upper:
                issues.append(
                    f"{label}: magi_upper does not strictly ascend at index {i} "
                    f"({curr_upper} >= {next_upper})"
                )

        # Last tier must have magi_upper = None
        if tiers[-1].magi_upper is not None:
            issues.append(f"{label}: last tier magi_upper must be None (top tier)")

    return issues


def validate_rmd_table(table: dict[int, Decimal]) -> list[str]:
    """Return a list of structural issues in an RMD Uniform Lifetime table.

    Factors must strictly decrease as age increases.
    """
    issues: list[str] = []
    if not table:
        issues.append("rmd table is empty")
        return issues

    sorted_ages = sorted(table)
    for i in range(len(sorted_ages) - 1):
        age_a = sorted_ages[i]
        age_b = sorted_ages[i + 1]
        if table[age_a] <= table[age_b]:
            issues.append(
                f"rmd factor must strictly decrease: "
                f"factor[{age_a}]={table[age_a]} <= factor[{age_b}]={table[age_b]}"
            )

    return issues


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_ordinary_brackets(brackets: list, label: str) -> list[str]:
    """Validate a list of ordinary-income Bracket objects."""
    issues: list[str] = []

    if not brackets:
        issues.append(f"{label}: empty bracket list")
        return issues

    # Last bracket must have upper=None
    if brackets[-1].upper is not None:
        issues.append(f"{label}: last bracket upper must be None (top bracket), "
                      f"got {brackets[-1].upper}")

    # Uppers of non-final brackets must strictly ascend
    non_final = [b for b in brackets if b.upper is not None]
    for i in range(len(non_final) - 1):
        a = non_final[i].upper
        b = non_final[i + 1].upper
        if a is not None and b is not None and a >= b:
            issues.append(
                f"{label}: bracket uppers do not strictly ascend at index {i} "
                f"({a} >= {b})"
            )

    # Rates must strictly ascend across all brackets
    for i in range(len(brackets) - 1):
        r_a = brackets[i].rate
        r_b = brackets[i + 1].rate
        if r_a >= r_b:
            issues.append(
                f"{label}: bracket rates do not strictly ascend at index {i} "
                f"({r_a} >= {r_b})"
            )

    return issues


def _check_ltcg_brackets(brackets: list, label: str) -> list[str]:
    """Validate LTCG bracket list: exactly 3 brackets, first rate == 0."""
    issues: list[str] = []

    if len(brackets) != 3:
        issues.append(f"{label}: expected exactly 3 LTCG brackets, got {len(brackets)}")

    if brackets and brackets[0].rate != Decimal("0"):
        issues.append(
            f"{label}: first LTCG bracket rate must be 0, got {brackets[0].rate}"
        )

    # Also run standard ascending checks
    issues.extend(_check_ordinary_brackets(brackets, label=label))

    return issues
