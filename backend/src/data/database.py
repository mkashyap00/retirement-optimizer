"""Synchronous DuckDB wrapper.

Provides a thin, connection-managing facade over duckdb.  All calls are
synchronous — do NOT wrap in ``async def``; DuckDB's Python API is blocking.

Usage::

    db = Database(":memory:")
    db.connect()
    db.execute("INSERT INTO households ...")
    row = db.fetch_one("SELECT ...")
    db.close()
"""

import logging
import threading
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parents[2] / "schema.sql"

# The single, app-level "default" profile. A portfolio is keyed to a profile
# (not a household) so one uploaded snapshot serves every plan and run. Minimal
# build: exactly one profile, seeded at connect; the CFP/multi-client future
# adds more profiles behind this same key.
DEFAULT_PROFILE_ID = "00000000-0000-0000-0000-000000000001"


class Database:
    """Synchronous DuckDB connection wrapper with schema bootstrap."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None
        # One cursor per thread — see _cursor().
        self._local = threading.local()
        self._cursors: list[duckdb.DuckDBPyConnection] = []
        self._cursors_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the database connection and apply the schema if needed.

        For file-backed databases the parent directory is created
        automatically.  Schema is applied only when the ``households``
        table does not yet exist (safe to call on an already-initialised
        database).
        """
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = duckdb.connect(self.db_path)
        logger.info("connected to %s", self.db_path)

        rows = self._conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'households'"
        ).fetchall()

        if not rows:
            sql = _SCHEMA_PATH.read_text()
            self._conn.execute(sql)
            logger.info("schema applied from %s", _SCHEMA_PATH)

        # Always ensure the portfolios table exists so existing databases
        # that predate this table are upgraded without a full schema reset.
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolios (
                household_id    UUID          PRIMARY KEY REFERENCES households(id),
                uploaded_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lots_json       TEXT          NOT NULL,
                warnings_json   TEXT          NOT NULL
            )
            """
        )
        logger.debug("portfolios table ensured")

        # Upgrade existing databases that predate the nickname column.
        # DuckDB supports IF NOT EXISTS on ALTER TABLE ADD COLUMN, so this
        # is safe to run unconditionally on every connect — it is a no-op when
        # the column is already present (fresh schema applied above) and adds
        # the column when connecting to an older file-backed database.
        self._conn.execute(
            "ALTER TABLE households ADD COLUMN IF NOT EXISTS nickname TEXT"
        )
        logger.debug("households.nickname column ensured")

        # v2 migrations: planning horizon and Roth 5-year rule fields
        self._conn.execute(
            "ALTER TABLE households ADD COLUMN IF NOT EXISTS self_death_age INT"
        )
        self._conn.execute(
            "ALTER TABLE households ADD COLUMN IF NOT EXISTS spouse_death_age INT"
        )
        self._conn.execute(
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS roth_opened_year INT"
        )
        # v3 migrations: objective knobs
        self._conn.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS heir_tax_rate DECIMAL(6,4)"
        )
        self._conn.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS estate_weight DECIMAL(6,4)"
        )
        self.execute(
            "ALTER TABLE runs ADD COLUMN IF NOT EXISTS llm_narrative TEXT"
        )
        # v5 migration: dynamic spending. Both nullable — NULL means the fixed
        # rule with no discretionary band, which is exactly how every plan
        # created before this behaved.
        self._conn.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS spending_rule TEXT"
        )
        self._conn.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS spending_floor DECIMAL(15,2)"
        )
        # v6 migration: projected Social Security COLA. NULL follows the
        # household's inflation assumption (floored at zero); 0 holds benefits
        # flat, the behaviour of every plan created before it existed.
        self._conn.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS ss_cola DECIMAL(6,4)"
        )
        # v7 migration: whether each person already receives Social Security.
        # NULL = unknown, the legacy reading (receiving once age reaches the
        # claim age), which fixed-age runs label and claim-age search refuses.
        for col in ("ss_receiving_self", "ss_receiving_spouse"):
            self._conn.execute(
                f"ALTER TABLE settings ADD COLUMN IF NOT EXISTS {col} BOOLEAN"
            )
        # v8 migration: capital gains already realized in the plan's first
        # year, and the loss carried into it (CapitalGainsIn as JSON). NULL =
        # none entered, which is how every earlier plan was modelled.
        self._conn.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS capital_gains_json TEXT"
        )
        logger.debug(
            "v2/v3/v5/v6/v7/v8 schema columns ensured (self_death_age, spouse_death_age, "
            "roth_opened_year, heir_tax_rate, estate_weight, spending_rule, "
            "spending_floor, ss_cola, ss_receiving_self, ss_receiving_spouse, "
            "capital_gains_json)"
        )

        # v4 migration: profiles + profile-scoped portfolio. Decouples the
        # portfolio from a single household so one uploaded snapshot serves
        # every plan/run (see DEFAULT_PROFILE_ID).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id          UUID       PRIMARY KEY,
                name        TEXT       NOT NULL DEFAULT 'Default',
                created_at  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Seed the single default profile exactly once.
        self._conn.execute(
            "INSERT INTO profiles (id, name) SELECT ?, 'Default' "
            "WHERE NOT EXISTS (SELECT 1 FROM profiles WHERE id = ?)",
            [DEFAULT_PROFILE_ID, DEFAULT_PROFILE_ID],
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_portfolios (
                profile_id     UUID       PRIMARY KEY REFERENCES profiles(id),
                uploaded_at    TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lots_json      TEXT       NOT NULL,
                warnings_json  TEXT       NOT NULL
            )
            """
        )
        # One-time carry-over: move the most recent legacy per-household
        # portfolio into the default profile so existing users keep their
        # upload. Idempotent — only runs when the profile store is still empty.
        self._conn.execute(
            """
            INSERT INTO profile_portfolios (profile_id, uploaded_at, lots_json, warnings_json)
            SELECT ?, uploaded_at, lots_json, warnings_json
            FROM portfolios
            WHERE NOT EXISTS (SELECT 1 FROM profile_portfolios)
            ORDER BY uploaded_at DESC
            LIMIT 1
            """,
            [DEFAULT_PROFILE_ID],
        )
        logger.debug("v4 profiles + profile_portfolios ensured")

    def close(self) -> None:
        """Close the underlying DuckDB connection and every thread's cursor."""
        with self._cursors_lock:
            for cursor in self._cursors:
                cursor.close()
            self._cursors.clear()
        self._local = threading.local()
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("closed connection to %s", self.db_path)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        """This thread's cursor on the shared database, created on first use.

        A DuckDB connection holds ONE pending result, and FastAPI runs sync
        endpoints on a thread pool. With every request on the shared
        connection, one thread's execute() could replace another's result
        before it was fetched — concurrent requests got each other's rows.
        A cursor is an independent connection to the same database, so each
        thread gets its own. Per THREAD, not per call: a sync endpoint runs
        start to finish on one thread, so a BEGIN/COMMIT spread across
        several execute() calls stays one transaction.
        """
        cursor = getattr(self._local, "cursor", None)
        if cursor is None:
            cursor = self._conn.cursor()
            self._local.cursor = cursor
            with self._cursors_lock:
                self._cursors.append(cursor)
        return cursor

    def execute(self, sql: str, params: list | None = None) -> None:
        """Execute a statement, discarding any result set."""
        self._cursor().execute(sql, params)

    def fetch_one(self, sql: str, params: list | None = None) -> tuple | None:
        """Return the first row of the result set, or ``None`` if empty."""
        return self._cursor().execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: list | None = None) -> list[tuple]:
        """Return all rows of the result set as a list of tuples."""
        return self._cursor().execute(sql, params).fetchall()
