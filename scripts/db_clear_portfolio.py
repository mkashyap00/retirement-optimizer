#!/usr/bin/env python3
"""Clear uploaded portfolio data without touching plans or households.

Usage:
    python scripts/db_clear_portfolio.py [DB_PATH]

DB_PATH defaults to data/retire.db (relative to the project root).
Requires the backend to be stopped (DuckDB exclusive file lock).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import duckdb


def clear_portfolio(db_path: str, *, confirm: bool = True) -> None:
    if confirm:
        answer = input(
            f"This will DELETE all portfolio data in {db_path!r}.\n"
            "Plans and households are kept. Type YES to continue: "
        ).strip()
        if answer != "YES":
            print("Aborted.")
            sys.exit(0)

    print(f"Connecting to {db_path!r} ...")
    conn = duckdb.connect(db_path)

    for table in ["profile_portfolios", "portfolios"]:
        try:
            result = conn.execute(f"DELETE FROM {table}").fetchone()
            count = result[0] if result else 0
            print(f"  Deleted {count:>4} rows from {table}")
        except Exception as exc:
            print(f"  WARNING: could not clear {table}: {exc}")

    conn.close()
    print("Done. Portfolio cleared; plans and households intact.")


if __name__ == "__main__":
    args = sys.argv[1:]
    yes_flag = "--yes" in args
    path_args = [a for a in args if not a.startswith("--")]
    db_path = path_args[0] if path_args else str(PROJECT_ROOT / "data" / "retire.db")
    clear_portfolio(db_path, confirm=not yes_flag)
