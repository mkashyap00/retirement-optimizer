#!/usr/bin/env python3
"""Reset the database entirely — drop all tables and re-apply the schema.

Usage:
    python scripts/db_reset.py [DB_PATH]

DB_PATH defaults to data/retire.db (relative to the project root).

WARNING: This is destructive.  All data is permanently lost.  The script
asks for confirmation before proceeding unless --yes is passed.

After the reset the database is in a clean state, identical to a
freshly-created database, and is immediately ready for new data.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import duckdb

SCHEMA_PATH = PROJECT_ROOT / "backend" / "schema.sql"


def reset(db_path: str, *, confirm: bool = True) -> None:
    if confirm:
        answer = input(
            f"This will DELETE ALL DATA in {db_path!r} and recreate the schema.\n"
            "Type YES to continue: "
        ).strip()
        if answer != "YES":
            print("Aborted.")
            sys.exit(0)

    print(f"Connecting to {db_path!r} ...")
    conn = duckdb.connect(db_path)

    # Drop tables in dependency order (children first)
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
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"  Dropped {table}")
        except Exception as exc:
            print(f"  WARNING: could not drop {table}: {exc}")

    # Re-apply schema (creates households, accounts, ..., portfolios, and the
    # profile store — see schema.sql).
    sql = SCHEMA_PATH.read_text()
    conn.execute(sql)
    print(f"  Schema applied from {SCHEMA_PATH}")

    conn.close()
    print("Done. Database reset to empty schema.")
    print(
        "Note: the app seeds the single default profile on the next backend "
        "start, so restart your stack before using the API."
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    yes_flag = "--yes" in args
    path_args = [a for a in args if not a.startswith("--")]
    db_path = path_args[0] if path_args else str(PROJECT_ROOT / "data" / "retire.db")
    reset(db_path, confirm=not yes_flag)
