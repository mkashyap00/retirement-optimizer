#!/usr/bin/env python3
"""Purge all rows from the database while preserving the schema.

Usage:
    python scripts/db_purge.py [DB_PATH]

DB_PATH defaults to data/retire.db (relative to the project root).

WARNING: This is destructive.  All rows are permanently deleted.  The script
asks for confirmation before proceeding unless --yes is passed.

All tables are cleared in dependency order (child rows before parent rows)
so that FK-style relationships are respected even though DuckDB does not
enforce FK constraints at runtime.

The schema and table definitions are left intact — the database is ready
for new data immediately after this script completes.
"""

import sys
from pathlib import Path

# Allow running from the project root without installing the package
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import duckdb


def purge(db_path: str, *, confirm: bool = True) -> None:
    if confirm:
        answer = input(
            f"This will DELETE ALL ROWS in {db_path!r} (schema preserved).\n"
            "Type YES to continue: "
        ).strip()
        if answer != "YES":
            print("Aborted.")
            sys.exit(0)

    print(f"Connecting to {db_path!r} ...")
    conn = duckdb.connect(db_path)

    # Deletion order: children before parents
    tables = [
        "runs",
        "settings",
        "income_sources",
        "accounts",
        "portfolios",
        "profile_portfolios",
        "households",
        "profiles",
    ]

    for table in tables:
        try:
            result = conn.execute(f"DELETE FROM {table}").fetchone()
            # DuckDB DELETE returns the number of deleted rows when fetchone() is called
            count = result[0] if result else 0
            print(f"  Deleted {count:>6} rows from {table}")
        except Exception as exc:
            print(f"  WARNING: could not clear {table}: {exc}")

    conn.close()
    print("Done. All rows purged; schema intact.")
    print(
        "Note: the app re-seeds the single default profile on the next backend "
        "start, so restart your stack before using the API."
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    yes_flag = "--yes" in args
    path_args = [a for a in args if not a.startswith("--")]
    db_path = path_args[0] if path_args else str(PROJECT_ROOT / "data" / "retire.db")
    purge(db_path, confirm=not yes_flag)
