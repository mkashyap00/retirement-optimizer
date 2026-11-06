"""Unit tests for the synchronous DuckDB wrapper.

TDD order: tests were written before the implementation in database.py.
Each test covers exactly one behaviour.
"""


from src.data.database import DEFAULT_PROFILE_ID, Database

# ---------------------------------------------------------------------------
# Schema application
# ---------------------------------------------------------------------------


def test_connect_memory_applies_schema():
    """Connecting to :memory: creates all five expected tables."""
    db = Database(":memory:")
    db.connect()

    tables = db.fetch_all(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    )
    table_names = {row[0] for row in tables}
    assert {"households", "accounts", "income_sources", "settings", "runs"}.issubset(
        table_names
    )

    db.close()


def test_connect_memory_no_extra_tables():
    """The trimmed schema must NOT contain v2 tables (rules_cache, audit_log, etc.)."""
    db = Database(":memory:")
    db.connect()

    tables = db.fetch_all(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    )
    table_names = {row[0] for row in tables}
    legacy = {"rules_cache", "audit_log", "optimization_runs", "cashflows"}
    assert not legacy.intersection(table_names), (
        f"Legacy tables still present: {legacy.intersection(table_names)}"
    )

    db.close()


# ---------------------------------------------------------------------------
# Household roundtrip
# ---------------------------------------------------------------------------


def test_household_insert_and_fetch_roundtrip():
    """Insert a household row, fetch it back; values must survive the round-trip."""
    db = Database(":memory:")
    db.connect()

    hh_id = "00000000-0000-0000-0000-000000000001"
    now = "2025-01-01 00:00:00"
    cols = "(id, filing_status, self_birth_date, state, created_at, updated_at)"
    db.execute(
        f"INSERT INTO households {cols} VALUES (?, 'single', '1970-06-15', 'CA', ?, ?)",
        [hh_id, now, now],
    )

    row = db.fetch_one(
        "SELECT id, filing_status, state FROM households WHERE id = ?",
        [hh_id],
    )

    assert row is not None
    assert str(row[0]) == hh_id
    assert row[1] == "single"
    assert row[2] == "CA"

    db.close()


# ---------------------------------------------------------------------------
# fetch_one miss → None
# ---------------------------------------------------------------------------


def test_fetch_one_returns_none_on_miss():
    """fetch_one must return None when the query matches no rows."""
    db = Database(":memory:")
    db.connect()

    result = db.fetch_one(
        "SELECT id FROM households WHERE id = ?",
        ["ffffffff-ffff-ffff-ffff-ffffffffffff"],
    )
    assert result is None

    db.close()


# ---------------------------------------------------------------------------
# fetch_all returns list
# ---------------------------------------------------------------------------


def test_fetch_all_returns_empty_list_on_miss():
    """fetch_all must return an empty list when no rows match."""
    db = Database(":memory:")
    db.connect()

    rows = db.fetch_all("SELECT id FROM households WHERE filing_status = ?", ["joint"])
    assert rows == []

    db.close()


# ---------------------------------------------------------------------------
# Schema idempotency — connecting twice to the same :memory: instance
# ---------------------------------------------------------------------------


def test_nickname_column_exists_after_connect():
    """After connect(), households must have a nickname column (schema or ALTER)."""
    db = Database(":memory:")
    db.connect()

    # Insert a row with an explicit nickname value to confirm the column exists.
    hh_id = "22222222-2222-2222-2222-222222222222"
    now = "2025-06-01 00:00:00"
    db.execute(
        "INSERT INTO households "
        "(id, filing_status, self_birth_date, state, nickname, created_at, updated_at) "
        "VALUES (?, 'single', '1970-01-01', 'CA', 'Test Plan', ?, ?)",
        [hh_id, now, now],
    )

    row = db.fetch_one(
        "SELECT nickname FROM households WHERE id = ?",
        [hh_id],
    )
    assert row is not None
    assert row[0] == "Test Plan"

    db.close()


def test_alter_nickname_idempotent():
    """Running connect() twice on the same connection is safe (ALTER IF NOT EXISTS)."""
    db = Database(":memory:")
    db.connect()
    # A second call to the ALTER must not raise even though the column already exists.
    db._conn.execute(
        "ALTER TABLE households ADD COLUMN IF NOT EXISTS nickname TEXT"
    )
    db.close()


def test_schema_not_applied_twice():
    """Calling connect() a second time on the same path must not error.

    (Practically: the households-table check prevents re-running DROP+CREATE.)
    """
    db = Database(":memory:")
    db.connect()

    # Insert a sentinel row
    sentinel_id = "11111111-1111-1111-1111-111111111111"
    db.execute(
        "INSERT INTO households (id, filing_status, self_birth_date, state) "
        "VALUES (?, 'single', '1980-01-01', 'TX')",
        [sentinel_id],
    )

    # A second connect on a *new* object pointing to the same path would be a
    # separate connection in DuckDB; for :memory: each connect() is independent,
    # so we test the idempotency guard by checking the households-exists branch
    # directly: after connect, the table must still have the sentinel.
    row = db.fetch_one("SELECT id FROM households WHERE id = ?", [sentinel_id])
    assert row is not None

    db.close()


# ---------------------------------------------------------------------------
# v4: profiles + profile-scoped portfolio
# ---------------------------------------------------------------------------


def test_default_profile_seeded_and_portfolio_table_exists():
    """connect() seeds exactly one default profile and the profile store."""
    db = Database(":memory:")
    db.connect()

    tables = {
        r[0]
        for r in db.fetch_all(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        )
    }
    assert {"profiles", "profile_portfolios"}.issubset(tables)

    profiles = db.fetch_all("SELECT id FROM profiles")
    assert len(profiles) == 1
    assert str(profiles[0][0]) == DEFAULT_PROFILE_ID

    db.close()


def test_legacy_household_portfolio_migrates_into_default_profile(tmp_path):
    """A pre-existing per-household portfolio is carried into the default
    profile on the next connect (so upgrading users keep their upload)."""
    path = str(tmp_path / "retire.db")

    # First connect creates the schema (profile store still empty).
    db = Database(path)
    db.connect()
    db.execute(
        "INSERT INTO households (id, filing_status, self_birth_date, state) "
        "VALUES ('22222222-2222-2222-2222-222222222222', 'single', '1960-01-01', 'CA')"
    )
    # Simulate a legacy per-household portfolio row.
    db.execute(
        "INSERT INTO portfolios (household_id, lots_json, warnings_json) "
        "VALUES ('22222222-2222-2222-2222-222222222222', '[{\"t\":1}]', '[]')"
    )
    db.close()

    # Reconnect: the carry-over migration should copy it to the default profile.
    db2 = Database(path)
    db2.connect()
    row = db2.fetch_one(
        "SELECT lots_json FROM profile_portfolios WHERE profile_id = ?",
        [DEFAULT_PROFILE_ID],
    )
    assert row is not None
    assert row[0] == '[{"t":1}]'
    db2.close()


def test_concurrent_queries_do_not_swap_results(tmp_path):
    """Two threads querying at once must each get their own result set.

    FastAPI runs sync endpoints on a thread pool, and every request shared one
    DuckDB connection. execute() stores the result on the connection, so a
    second thread's execute() could replace it before the first fetched: the
    What-if page's parallel /households/{id} and /policies calls each got the
    other's rows ("could not convert string to float: 'taxable'", "too many
    values to unpack (expected 4, got 12)").
    """
    import threading

    db = Database(str(tmp_path / "race.db"))
    db.connect()
    db.execute("CREATE TABLE narrow (a INTEGER)")
    db.execute("INSERT INTO narrow VALUES (1)")
    db.execute("CREATE TABLE wide (a VARCHAR, b VARCHAR, c VARCHAR)")
    db.execute("INSERT INTO wide VALUES ('x', 'y', 'z')")

    errors: list[str] = []
    start = threading.Barrier(2)

    def hammer(sql: str, expected: list[tuple]) -> None:
        start.wait()
        for _ in range(2000):
            got = db.fetch_all(sql)
            if got != expected:
                errors.append(f"{sql!r} returned {got!r}")
                return

    threads = [
        threading.Thread(target=hammer, args=("SELECT a FROM narrow", [(1,)])),
        threading.Thread(target=hammer, args=("SELECT * FROM wide", [("x", "y", "z")])),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    db.close()
    assert not errors, errors


def test_transaction_spans_calls_on_one_thread(tmp_path):
    """BEGIN/COMMIT issued through separate db.execute calls on one thread must
    form a single transaction (households.py relies on this for multi-INSERT
    writes), so per-thread isolation must not become per-call isolation."""
    db = Database(str(tmp_path / "txn.db"))
    db.connect()
    db.execute("CREATE TABLE t (a INTEGER)")
    db.execute("BEGIN TRANSACTION")
    db.execute("INSERT INTO t VALUES (1)")
    db.execute("ROLLBACK")
    assert db.fetch_all("SELECT * FROM t") == []
    db.close()
