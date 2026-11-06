"""IRMAA (Income-Related Monthly Adjustment Amount) data for premium years 2025-2026.

IRMAA applies to Medicare Part B and Part D premiums.
The premium year's IRMAA is based on MAGI from two years prior (lookback year).

Sources:
  2025: CMS-8083-N, Federal Register Vol. 89, Nov 2024
  2026: CMS-8089-N, Federal Register, 90 FR 2025-20251, Nov 19 2025
"""

from decimal import Decimal

from src.data.tax_rules.types import IrmaaTier, IrmaaYear


def _T(magi_upper: str | None, part_b: str, part_d: str) -> IrmaaTier:
    """Convenience constructor for IrmaaTier."""
    return IrmaaTier(
        magi_upper=Decimal(magi_upper) if magi_upper is not None else None,
        part_b_monthly=Decimal(part_b),
        part_d_monthly=Decimal(part_d),
    )


IRMAA: dict[int, IrmaaYear] = {
    # ------------------------------------------------------------------ 2025
    # Source: CMS-8083-N (Nov 2024)
    # Standard Part B premium: $185.00
    # MAGI lookback: 2023 tax year
    # Joint thresholds = 2× single, EXCEPT top explicit tier is 750,000 (not 1,000,000)
    2025: IrmaaYear(
        year=2025,
        source="CMS-8083-N (Nov 2024)",
        part_b_standard=Decimal("185.00"),
        tiers={
            "single": [
                _T("106000", "185.00",  "0"),
                _T("133000", "259.00",  "13.70"),
                _T("167000", "370.00",  "35.30"),
                _T("200000", "480.90",  "57.00"),
                _T("500000", "591.90",  "78.60"),
                _T(None,     "628.90",  "85.80"),
            ],
            "joint": [
                _T("212000", "185.00",  "0"),
                _T("266000", "259.00",  "13.70"),
                _T("334000", "370.00",  "35.30"),
                _T("400000", "480.90",  "57.00"),
                _T("750000", "591.90",  "78.60"),
                _T(None,     "628.90",  "85.80"),
            ],
        },
    ),

    # ------------------------------------------------------------------ 2026
    # Source: CMS-8089-N, FR Doc. 2025-20251, Federal Register Nov 19 2025
    # Standard Part B premium: $202.90
    # MAGI lookback: 2024 tax year
    # Verified against:
    #   - medicareresources.org (Dec 2025)
    #   - quantcalc.app/irmaa-brackets-2026/
    #   - currentfederaltaxdevelopments.com (Nov 17 2025)
    #   - federalpensionadvisors.com
    2026: IrmaaYear(
        year=2026,
        source="CMS-8089-N, FR Doc. 2025-20251 (Nov 2025)",
        part_b_standard=Decimal("202.90"),
        tiers={
            "single": [
                _T("109000", "202.90",  "0"),
                _T("137000", "284.10",  "14.50"),
                _T("171000", "405.80",  "37.50"),
                _T("205000", "527.50",  "60.40"),
                _T("500000", "649.20",  "83.30"),
                _T(None,     "689.90",  "91.00"),
            ],
            "joint": [
                _T("218000", "202.90",  "0"),
                _T("274000", "284.10",  "14.50"),
                _T("342000", "405.80",  "37.50"),
                _T("410000", "527.50",  "60.40"),
                _T("750000", "649.20",  "83.30"),
                _T(None,     "689.90",  "91.00"),
            ],
        },
    ),
}
