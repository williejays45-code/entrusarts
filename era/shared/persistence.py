"""
First real persistence layer for the active ERA packages (C4).

Design mirrors the one working pattern already in the archive
(era/weight_registry.py, era/decision_trace.py, etc.) -- connect-per-call
sqlite3, no ORM -- but is generic instead of one bespoke table per
concept, so it can back any engine's state and/or audit trail without a
new schema being hand-written for each of the 20 active packages.

Two responsibilities, deliberately kept separate:

1. Record storage (`save_record` / `load_record` / `list_records`)
   -- JSON-blob storage keyed by (table_name, record_id). An engine
   persists its own domain objects by serializing them to a plain dict
   before calling save_record, and reconstructing them from the dict
   returned by load_record. This module does not know about
   ConnectorRecord, Recommendation, etc. -- keeping those serialization
   rules inside each engine's own package is what keeps this shared
   module from becoming a second, competing model layer.

2. Audit event storage (`event_sink` / `query_events`) -- this is what
   era.shared.audit.BaseAuditPublisher's optional `sink` parameter was
   built for. Pass `store.event_sink("your.namespace")` as the `sink=`
   argument to any *Audit class and its events now survive process exit
   and are queryable across engines via query_events(), which is the
   actual mechanism the "Cross-Engine Composition Audit" governance law
   needs. No existing *Audit class is forced onto this -- nothing
   persists unless a caller explicitly wires a store in.

Nothing in this module is wired into anything by default. Opting in is a
per-engine decision, same as MockTokenStore/TokenStore and
BaseAuditPublisher's sink parameter.

SCHEMA-001: both physical files (records, audit) carry their own
schema_meta (current version) and schema_migrations (applied-migration
history) tables, checked and advanced on every SqliteStore construction.
A file whose recorded version is newer than this code supports raises
SchemaVersionError immediately, before any table is touched -- see that
class's docstring for why this is a hard refusal rather than a retryable
PersistenceError.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional


DEFAULT_DB_PATH = "era_persistence.db"
AUDIT_DB_SUFFIX = ".audit.db"


class PersistenceError(Exception):
    """Raised for any failed persistence operation, with enough context
    for a caller to log/audit it meaningfully. Engines catch this at the
    _persist() boundary -- see each engine's _persist() method -- rather
    than letting a raw sqlite3.Error surface mid-pipeline."""

    def __init__(self, operation: str, table_or_namespace: str, record_id: str, original: Exception):
        self.operation = operation
        self.table_or_namespace = table_or_namespace
        self.record_id = record_id
        self.original = original
        super().__init__(
            f"PersistenceError during {operation} "
            f"(table/namespace={table_or_namespace!r}, record_id={record_id!r}): {original!r}"
        )


class Transaction:
    """
    TXN-001: a single SQLite connection/transaction shared across
    multiple engines' persistence calls during one run_property().

    Deliberately NOT used for audit events -- BaseAuditPublisher's sink
    still writes independently and immediately (see event_sink() below
    and its docstring). Audit is a side channel that should record what
    was *attempted*, including attempts that get rolled back; the
    business records (records table) are what this transaction protects.

    Usage:
        txn = store.transaction()
        try:
            engine_a._persist(record_a, conn=txn.conn)
            engine_b._persist(record_b, conn=txn.conn)
            txn.commit()
        except Exception:
            txn.rollback()
            raise
    """

    def __init__(self, store: "SqliteStore"):
        self._store = store
        self.conn = store._connect()
        self.conn.execute("BEGIN")
        self._closed = False

    def commit(self):
        if self._closed:
            return
        self.conn.commit()
        self.conn.close()
        self._closed = True

    def rollback(self):
        if self._closed:
            return
        self.conn.rollback()
        self.conn.close()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        return False


class SchemaVersionError(Exception):
    """
    SCHEMA-001: raised when a database file's recorded schema version is
    NEWER than what this build of the code supports. This is a hard
    refusal, not a PersistenceError -- it's not a transient I/O problem
    to retry, it's "this file was written by a newer version of ERA than
    what's running right now, and blindly reading/writing it could
    misinterpret or corrupt data this code doesn't understand." The only
    correct response is to stop before opening the file at all, which is
    why this is raised from SqliteStore.__init__ (via _ensure_schema),
    before any table is touched.
    """

    def __init__(self, label: str, found_version: int, max_supported_version: int):
        self.label = label
        self.found_version = found_version
        self.max_supported_version = max_supported_version
        super().__init__(
            f"{label} database schema is at version {found_version}, but this build of "
            f"ERA only supports up to version {max_supported_version}. Refusing to open -- "
            f"upgrade the application before using this database file."
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA_META_SQL = """
    CREATE TABLE IF NOT EXISTS schema_meta (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        version INTEGER NOT NULL
    )
"""
_SCHEMA_MIGRATIONS_SQL = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        description TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )
"""


def _migrate_records_v1(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (table_name, record_id)
        )
        """
    )


def _migrate_records_v2(conn):
    # A real, non-business-logic schema improvement (query performance
    # on updated_at range lookups) -- exists so SCHEMA-001 has more than
    # one real version to apply in order, not a synthetic test fixture.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_updated_at ON records(updated_at)")


RECORDS_MIGRATIONS = [
    (1, "create records table", _migrate_records_v1),
    (2, "add index on records.updated_at", _migrate_records_v2),
]
RECORDS_SCHEMA_VERSION = 2


def _migrate_audit_v1(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            published_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_namespace ON audit_events(namespace)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type)")


def _migrate_audit_v2(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_published_at ON audit_events(published_at)")


AUDIT_MIGRATIONS = [
    (1, "create audit_events table + namespace/event_type indexes", _migrate_audit_v1),
    (2, "add index on audit_events.published_at", _migrate_audit_v2),
]
AUDIT_SCHEMA_VERSION = 2


def _apply_schema(conn, migrations, target_version: int, label: str):
    """Ensures the bookkeeping tables exist, refuses to proceed if the
    file's recorded version is newer than target_version, then applies
    every migration strictly greater than the current version, in
    order, recording each one in schema_migrations before moving on."""
    conn.execute(_SCHEMA_META_SQL)
    conn.execute(_SCHEMA_MIGRATIONS_SQL)
    row = conn.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
    current = row[0] if row else 0
    if current > target_version:
        raise SchemaVersionError(label, current, target_version)
    for version, description, migrate_fn in migrations:
        if version <= current:
            continue
        migrate_fn(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (version, description, _utc_now()),
        )
        current = version
    if row is None:
        conn.execute("INSERT INTO schema_meta (id, version) VALUES (1, ?)", (current,))
    elif current != row[0]:
        conn.execute("UPDATE schema_meta SET version = ? WHERE id = 1", (current,))


class SqliteStore:
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 0.05

    def __init__(self, db_path: str = DEFAULT_DB_PATH, audit_db_path: str = None):
        self.db_path = db_path
        # TXN-001: audit events live in a separate physical file from
        # business records. A Transaction (see below) can hold the
        # single-writer lock on db_path for an entire run_property() --
        # if audit_events lived in the same file, every audit event
        # published during that window would contend for the same lock
        # and (by design) fail fast and be dropped from durable storage,
        # for the ENTIRE duration of every transactional pipeline run.
        # Splitting the file removes the contention rather than papering
        # over it with a shorter timeout.
        self.audit_db_path = audit_db_path or f"{db_path}{AUDIT_DB_SUFFIX}"
        self._ensure_schema()

    def _connect(self, timeout: float = 5.0, audit: bool = False):
        path = self.audit_db_path if audit else self.db_path
        conn = sqlite3.connect(path, timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def transaction(self) -> "Transaction":
        """TXN-001: open a transaction whose connection can be threaded
        through save_record(conn=...) calls across multiple engines."""
        return Transaction(self)

    def _run(self, operation: str, table_or_namespace: str, record_id: str, fn, conn=None):
        """Runs fn(conn) against a connection, retrying a bounded number
        of times on transient lock contention, and always converting any
        failure into a PersistenceError with context.

        If `conn` is given (TXN-001: caller is inside a Transaction),
        that connection is used directly and is NOT committed or closed
        here -- the Transaction owns that lifecycle. This is what lets
        several engines' writes land in one atomic unit.

        If `conn` is None (the default -- every existing call site
        before TXN-001, and every standalone/single-engine call site
        after it), behavior is byte-for-byte what it was before this
        patch: a fresh connection per call, committed and closed
        immediately. This is what preserves single-engine rollback
        behavior exactly as already verified.
        """
        if conn is not None:
            try:
                return fn(conn)
            except sqlite3.Error as exc:
                raise PersistenceError(operation, table_or_namespace, record_id, exc) from exc
            except Exception as exc:
                raise PersistenceError(operation, table_or_namespace, record_id, exc) from exc
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            owned_conn = None
            try:
                owned_conn = self._connect()
                result = fn(owned_conn)
                owned_conn.commit()
                return result
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    time.sleep(self.RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                raise PersistenceError(operation, table_or_namespace, record_id, exc) from exc
            except sqlite3.Error as exc:
                raise PersistenceError(operation, table_or_namespace, record_id, exc) from exc
            except Exception as exc:
                raise PersistenceError(operation, table_or_namespace, record_id, exc) from exc
            finally:
                if owned_conn is not None:
                    owned_conn.close()
        raise PersistenceError(operation, table_or_namespace, record_id, last_error)

    def _ensure_schema(self):
        records_conn = None
        try:
            records_conn = self._connect()
            _apply_schema(records_conn, RECORDS_MIGRATIONS, RECORDS_SCHEMA_VERSION, "records")
            records_conn.commit()
        except SchemaVersionError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceError("ensure_schema", "records", "-", exc) from exc
        finally:
            if records_conn is not None:
                records_conn.close()

        audit_conn = None
        try:
            audit_conn = self._connect(audit=True)
            _apply_schema(audit_conn, AUDIT_MIGRATIONS, AUDIT_SCHEMA_VERSION, "audit")
            audit_conn.commit()
        except SchemaVersionError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceError("ensure_schema", "audit_events", "-", exc) from exc
        finally:
            if audit_conn is not None:
                audit_conn.close()

    # ---- schema introspection ----

    def get_schema_version(self, audit: bool = False) -> int:
        conn = self._connect(audit=audit)
        try:
            row = conn.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def get_migration_history(self, audit: bool = False) -> list:
        conn = self._connect(audit=audit)
        try:
            rows = conn.execute(
                "SELECT version, description, applied_at FROM schema_migrations ORDER BY version"
            ).fetchall()
            return [{"version": r[0], "description": r[1], "applied_at": r[2]} for r in rows]
        finally:
            conn.close()

    # ---- record storage ----

    def save_record(self, table_name: str, record_id: str, data: dict, conn=None) -> None:
        def fn(c):
            c.execute(
                """
                INSERT INTO records (table_name, record_id, data, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(table_name, record_id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (table_name, record_id, json.dumps(data), datetime.now(timezone.utc).isoformat()),
            )
        self._run("save_record", table_name, record_id, fn, conn=conn)

    def load_record(self, table_name: str, record_id: str, conn=None) -> Optional[dict]:
        def fn(c):
            row = c.execute(
                "SELECT data FROM records WHERE table_name = ? AND record_id = ?",
                (table_name, record_id),
            ).fetchone()
            return json.loads(row[0]) if row else None
        return self._run("load_record", table_name, record_id, fn, conn=conn)

    def list_records(self, table_name: str, conn=None) -> list:
        def fn(c):
            rows = c.execute(
                "SELECT record_id, data FROM records WHERE table_name = ? ORDER BY record_id",
                (table_name,),
            ).fetchall()
            return [json.loads(row[1]) for row in rows]
        return self._run("list_records", table_name, "*", fn, conn=conn)

    def delete_record(self, table_name: str, record_id: str, conn=None) -> None:
        def fn(c):
            c.execute(
                "DELETE FROM records WHERE table_name = ? AND record_id = ?",
                (table_name, record_id),
            )
        self._run("delete_record", table_name, record_id, fn, conn=conn)

    # ---- audit event storage ----

    def event_sink(self, namespace: str):
        """Return a callable(event: dict) -> None suitable for
        era.shared.audit.BaseAuditPublisher(sink=...).

        TXN-001 note: audit writes use a short, non-retrying connection
        (fail fast) rather than the business-write retry path. A
        Transaction (see Transaction above) can hold the write lock on
        this same file for the duration of an entire run_property() --
        if audit used the same 3-retry/5-second-busy-timeout path as
        business writes, every audit event published during an open
        transaction would block for seconds at a time waiting on a lock
        it has no real chance of acquiring until the transaction ends.
        Since audit-write failure is already meant to be invisible to
        the caller (see BaseAuditPublisher.publish()), failing fast here
        instead of retrying loses nothing observable -- the event is
        still kept in the publisher's own self.events for this process.
        """

        def _sink(event: dict) -> None:
            conn = None
            try:
                conn = self._connect(timeout=0.0, audit=True)
                conn.execute(
                    """
                    INSERT INTO audit_events (namespace, event_type, payload, published_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        namespace,
                        event["event_type"],
                        json.dumps(event["payload"]),
                        event.get("published_at", datetime.now(timezone.utc).isoformat()),
                    ),
                )
                conn.commit()
            except Exception:
                # Fail fast and silent -- see docstring above. This
                # intentionally does not raise PersistenceError up to
                # the caller; audit sink failures are swallowed here
                # directly rather than relying on BaseAuditPublisher's
                # backstop, precisely so a busy business transaction on
                # the same file never has to wait on this at all.
                pass
            finally:
                if conn is not None:
                    conn.close()

        return _sink

    def query_events(self, namespace: str = None, event_type: str = None, limit: int = 500) -> list:
        def fn(conn):
            clauses, params = [], []
            if namespace is not None:
                clauses.append("namespace = ?")
                params.append(namespace)
            if event_type is not None:
                clauses.append("event_type = ?")
                params.append(event_type)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = conn.execute(
                f"""
                SELECT namespace, event_type, payload, published_at
                FROM audit_events
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [
                {
                    "namespace": row[0],
                    "event_type": row[1],
                    "payload": json.loads(row[2]),
                    "published_at": row[3],
                }
                for row in rows
            ]
        conn = self._connect(audit=True)
        try:
            return fn(conn)
        except sqlite3.Error as exc:
            raise PersistenceError("query_events", namespace or "*", event_type or "*", exc) from exc
        finally:
            conn.close()
