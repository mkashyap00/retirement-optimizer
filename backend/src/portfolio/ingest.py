"""CSV ingest for tax-lot data.

The documented v1 layout is the aggregate-position **template** (see the
User Guide)::

    symbol,shares,price,cost_basis,account_type[,long_term]

``cost_basis`` is the **total** (aggregate) dollars paid for the position —
the same figure the Accounts wizard collects — and the per-share basis is
derived internally as ``cost_basis / shares``. Positions carry no dates;
``long_term`` (yes/no, blank = yes) flags the holding period explicitly.
Basis is required for taxable rows only.

Three legacy lot-level layouts remain supported (auto-detected by header):

Mode A — per-share basis::

    ticker,lot_date,shares,cost_basis_per_share,current_price,account_type

Mode B — total basis + market value::

    ticker,lot_date,shares,cost_basis_total,market_value,account_type

Mode C — no lot dates, average cost only::

    ticker,shares,avg_cost_basis,market_value,account_type

Input may be comma- or **tab**-separated (a range pasted straight out of
Excel/Google Sheets is tab-separated), may have a UTF-8 BOM, blank lines,
or dollar signs / commas in numbers (e.g. ``$1,234.56``). Header names are
matched case-insensitively with internal spaces treated as underscores, so
``Cost Basis`` == ``cost_basis``. All numeric values are parsed as
:class:`~decimal.Decimal`.  Unknown column sets raise :class:`ValueError`
naming the expected sets.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from src.portfolio.models import TaxLot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Expected header sets (frozensets for order-insensitive matching)
# ---------------------------------------------------------------------------

_HEADERS_A = frozenset(
    {"ticker", "lot_date", "shares", "cost_basis_per_share", "current_price", "account_type"}
)
_HEADERS_B = frozenset(
    {"ticker", "lot_date", "shares", "cost_basis_total", "market_value", "account_type"}
)
_HEADERS_C = frozenset(
    {"ticker", "shares", "avg_cost_basis", "market_value", "account_type"}
)
# The documented v1 template: aggregate positions with total cost basis.
# ``long_term`` is an optional extra column (yes/no, blank = yes).
_HEADERS_TEMPLATE = frozenset(
    {"symbol", "shares", "price", "cost_basis", "account_type"}
)

_MODE_C_WARNING = (
    "Lot-level detail unavailable. Using average cost basis — "
    "specific identification not possible."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clean_number(raw: str) -> str:
    """Strip leading ``$``, commas, and surrounding whitespace."""
    return raw.strip().lstrip("$").replace(",", "")


def _norm_key(name: str) -> str:
    """Normalise a header name: lowercase, strip, collapse whitespace to ``_``.

    So ``"Cost Basis"`` and ``" cost   basis "`` both become ``cost_basis``.
    """
    return "_".join(name.strip().lower().split())


def _detect_delimiter(text: str) -> str:
    """Return the delimiter of the first non-empty line.

    Copying a range out of Excel/Google Sheets yields **tab**-separated
    values; downloaded or hand-typed files are comma-separated. We sniff the
    header line so a pasted spreadsheet range just works.
    """
    for line in text.splitlines():
        if line.strip():
            return "\t" if "\t" in line else ","
    return ","


def _parse_decimal(raw: str, field_name: str) -> Decimal:
    cleaned = _clean_number(raw)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse {field_name!r} value {raw!r} as a number") from exc


def _parse_date_optional(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Cannot parse date {raw!r} (expected YYYY-MM-DD)") from exc


def _template_row_to_lot(row: dict[str, str]) -> TaxLot:
    """Build a TaxLot from one row of the documented aggregate template.

    ``cost_basis`` is the total dollars paid for the position; the per-share
    basis stored on the lot is ``cost_basis / shares``. Basis is required for
    taxable rows (it drives gain estimates) and ignored elsewhere. A blank
    ``long_term`` means yes — retirees selling long-accumulated positions are
    long-term almost always; flag the exceptions with ``no``.
    """
    ticker = row["symbol"].upper()
    account_type = row["account_type"].lower()
    shares = _parse_decimal(row["shares"], "shares")
    if shares <= 0:
        raise ValueError(f"Row with symbol {ticker}: shares must be positive, got {shares}")
    price = _parse_decimal(row["price"], "price")

    raw_basis = row.get("cost_basis", "")
    if account_type == "taxable":
        if not raw_basis:
            raise ValueError(
                f"Row with symbol {ticker}: cost_basis is required "
                "for taxable positions"
            )
        basis = _parse_decimal(raw_basis, "cost_basis") / shares
    else:
        basis = _parse_decimal(raw_basis, "cost_basis") / shares if raw_basis else Decimal("0")

    raw_lt = row.get("long_term", "").lower()
    if raw_lt in ("", "yes", "y", "true", "1"):
        long_term = True
    elif raw_lt in ("no", "n", "false", "0"):
        long_term = False
    else:
        raise ValueError(
            f"Row with symbol {ticker}: long_term must be yes/no, got {raw_lt!r}"
        )

    return TaxLot(
        ticker=ticker,
        lot_date=None,
        shares=shares,
        cost_basis_per_share=basis,
        current_price=price,
        account_type=account_type,
        long_term=long_term,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_csv(text: str) -> tuple[list[TaxLot], list[str]]:
    """Parse a CSV string into a list of :class:`~models.TaxLot` objects.

    Args:
        text: Raw CSV text (may include BOM).

    Returns:
        A 2-tuple ``(lots, warnings)`` where *lots* is the parsed list and
        *warnings* is a list of advisory strings (may be empty).

    Raises:
        ValueError: If the header row does not match any known layout.
    """
    # Strip BOM if present
    text = text.lstrip("﻿")

    reader = csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text))

    # Normalise header names (lowercase, strip, spaces → underscores)
    raw_fieldnames = reader.fieldnames or []
    norm_fields = frozenset(_norm_key(f) for f in raw_fieldnames)

    # --- Detect mode -------------------------------------------------------
    if _HEADERS_TEMPLATE <= norm_fields:
        mode = "template"
    elif _HEADERS_A <= norm_fields:
        mode = "A"
    elif _HEADERS_B <= norm_fields:
        mode = "B"
    elif _HEADERS_C <= norm_fields:
        mode = "C"
    else:
        raise ValueError(
            f"Unrecognised CSV columns {sorted(norm_fields)!r}. "
            f"Expected one of:\n"
            f"  Template: {sorted(_HEADERS_TEMPLATE)} (+ optional long_term)\n"
            f"  Mode A: {sorted(_HEADERS_A)}\n"
            f"  Mode B: {sorted(_HEADERS_B)}\n"
            f"  Mode C: {sorted(_HEADERS_C)}"
        )

    warnings: list[str] = []
    if mode == "C":
        warnings.append(_MODE_C_WARNING)

    lots: list[TaxLot] = []
    for row in reader:
        # Normalise keys
        row = {
            _norm_key(k): (v or "").strip()
            for k, v in row.items()
            if k is not None
        }

        # Skip blank rows (all values empty)
        if not any(row.values()):
            continue

        if mode == "template":
            lots.append(_template_row_to_lot(row))
            continue

        ticker = row["ticker"].upper()
        account_type = row["account_type"].lower()
        shares = _parse_decimal(row["shares"], "shares")

        if mode == "A":
            lot_date = _parse_date_optional(row["lot_date"])
            cost_basis_per_share = _parse_decimal(
                row["cost_basis_per_share"], "cost_basis_per_share"
            )
            current_price = _parse_decimal(row["current_price"], "current_price")

        elif mode == "B":
            lot_date = _parse_date_optional(row["lot_date"])
            cost_basis_total = _parse_decimal(row["cost_basis_total"], "cost_basis_total")
            market_value = _parse_decimal(row["market_value"], "market_value")
            # Validate shares before division
            if shares <= 0:
                raise ValueError(f"Row with ticker {ticker}: shares must be positive, got {shares}")
            # Derive per-share values
            cost_basis_per_share = cost_basis_total / shares
            current_price = market_value / shares

        else:  # mode C
            lot_date = None
            avg_cost_basis = _parse_decimal(row["avg_cost_basis"], "avg_cost_basis")
            market_value = _parse_decimal(row["market_value"], "market_value")
            # Validate shares before division
            if shares <= 0:
                raise ValueError(f"Row with ticker {ticker}: shares must be positive, got {shares}")
            cost_basis_per_share = avg_cost_basis
            current_price = market_value / shares

        lots.append(
            TaxLot(
                ticker=ticker,
                lot_date=lot_date,
                shares=shares,
                cost_basis_per_share=cost_basis_per_share,
                current_price=current_price,
                account_type=account_type,
            )
        )

    return lots, warnings
