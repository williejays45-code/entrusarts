"""
DCAD-INDEX-001: disk-backed index for DCAD's certified tables.

Replaces the in-memory Python dict index DCADBulkDataAdapter originally
used. Measured directly against the real uploaded files: indexing just
Account_Apprl_Year (858,533 rows, 47 columns) into a Python dict
consumed 2.9 GB of RSS; the process was killed by the OS attempting to
also index Account_Info. That was a real, reproduced failure, not a
theoretical one -- this module exists specifically to fix it.

Design:
- Two tables (dcad_appraisal_index, dcad_info_index), each keyed by a
  composite (account_num, appraisal_yr) PRIMARY KEY. account_num is
  stored as TEXT throughout -- never parsed as a number anywhere in
  this module -- so leading zeros (e.g. a real DCAD ACCOUNT_NUM like
  "00000416479000000") survive exactly.
- Each row is stored as a JSON blob of the full CSV row, same shape the
  old in-memory dict held, so retrieval semantics (row.get(column))
  are unchanged for callers.
- Rows are streamed from the CSV and inserted in bounded batches
  (executemany, not one row at a time and not the whole file at once)
  -- this is what keeps memory bounded regardless of source file size.
- The ENTIRE build (both tables, when both are being loaded) happens
  inside one SQLite transaction. build_complete is only ever set to 1
  as the very last statement before commit. Any failure at any point
  -- mid-appraisal-table, mid-info-table, or in between -- rolls the
  whole transaction back, so a partial/incomplete index can never be
  observed as ready. This is the same atomic-commit discipline
  DCAD-JOIN-001's own bug fix already established at the Python level
  (era/live_adapters/dcad_bulk_data_adapter.py's _fetch_and_index),
  now expressed as a real SQL transaction for the bulk data itself.
- A SHA-256 fingerprint of the downloaded ZIP's raw bytes is stored
  alongside the completed build. A caller can check
  needs_rebuild(fingerprint) before re-downloading/re-indexing --  if
  the fingerprint matches a complete prior build, the on-disk index is
  reused as-is, no rebuild, no wasted work. If the source has actually
  changed, the fingerprint won't match and a rebuild is forced.
"""

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone


DEFAULT_BATCH_SIZE = 2000


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def compute_fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class DCADIndexBuildError(Exception):
    """Raised when a build fails partway through. The caller (the
    adapter) treats this as a clean failure status, not a crash --
    same discipline as PersistenceError elsewhere in this codebase."""

    def __init__(self, stage: str, detail: str):
        self.stage = stage
        self.detail = detail
        super().__init__(f"DCAD index build failed at {stage}: {detail}")


class DCADIndexStore:
    APPRAISAL_TABLE = "dcad_appraisal_index"
    INFO_TABLE = "dcad_info_index"

    def __init__(self, db_path: str = "dcad_index.db", batch_size: int = DEFAULT_BATCH_SIZE):
        self.db_path = db_path
        self.batch_size = batch_size
        # Operational benchmark instrumentation: configured_batch_size
        # is the same value as self.batch_size under a name matching
        # the benchmark contract; max_observed_batch_size is updated on
        # every flush and never reset, so a caller can inspect it after
        # a build to prove the streaming insert never silently
        # accumulated more than one batch's worth of rows in memory at
        # once, rather than just trusting the code review.
        self.configured_batch_size = batch_size
        self.max_observed_batch_size = 0
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self):
        conn = self._connect()
        try:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.APPRAISAL_TABLE} (
                    account_num TEXT NOT NULL,
                    appraisal_yr TEXT NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY (account_num, appraisal_yr)
                )
            """)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.INFO_TABLE} (
                    account_num TEXT NOT NULL,
                    appraisal_yr TEXT NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY (account_num, appraisal_yr)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dcad_index_build_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    source_fingerprint TEXT,
                    has_info_table INTEGER NOT NULL DEFAULT 0,
                    build_complete INTEGER NOT NULL DEFAULT 0,
                    built_at TEXT,
                    row_count_appraisal INTEGER NOT NULL DEFAULT 0,
                    row_count_info INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ---- readiness / fingerprint checks (cheap, no CSV involved) -----

    def get_build_meta(self) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT source_fingerprint, has_info_table, build_complete, built_at, "
                "row_count_appraisal, row_count_info FROM dcad_index_build_meta WHERE id = 1"
            ).fetchone()
            if row is None:
                return None
            return {
                "source_fingerprint": row[0],
                "has_info_table": bool(row[1]),
                "build_complete": bool(row[2]),
                "built_at": row[3],
                "row_count_appraisal": row[4],
                "row_count_info": row[5],
            }
        finally:
            conn.close()

    def is_ready(self, require_info_table: bool = False) -> bool:
        """An incomplete build is never treated as ready -- this checks
        the durable build_complete flag, not merely "some rows exist"."""
        meta = self.get_build_meta()
        if meta is None or not meta["build_complete"]:
            return False
        if require_info_table and not meta["has_info_table"]:
            return False
        return True

    def needs_rebuild(self, fingerprint: str, require_info_table: bool = False) -> bool:
        meta = self.get_build_meta()
        if meta is None or not meta["build_complete"]:
            return True
        if require_info_table and not meta["has_info_table"]:
            return True
        return meta["source_fingerprint"] != fingerprint

    # ---- the build itself: streaming, chunked, one transaction -------

    def build(self, appraisal_reader, info_reader, fingerprint: str,
              appraisal_required_columns: set, info_required_columns: set = None):
        """appraisal_reader / info_reader: callables returning an
        iterable of csv.DictReader rows (or any dict-yielding iterable)
        -- called lazily, streamed, never materialized as a list.
        info_reader may be None (Phase 1, no join).

        Any exception raised while iterating either reader rolls the
        WHOLE transaction back -- no partial appraisal rows, no partial
        info rows, and build_complete is never set. This is what
        satisfies "partial appraisal import rolls back cleanly" and
        "partial info import rolls back cleanly" as one guarantee, not
        two separate code paths to keep in sync.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(f"DELETE FROM {self.APPRAISAL_TABLE}")
            conn.execute(f"DELETE FROM {self.INFO_TABLE}")
            conn.execute("DELETE FROM dcad_index_build_meta WHERE id = 1")

            appraisal_streamed, appraisal_stored = self._stream_insert(
                conn, self.APPRAISAL_TABLE, appraisal_reader(),
                appraisal_required_columns, "appraisal_year",
            )

            info_streamed, info_stored = 0, 0
            has_info = info_reader is not None
            if has_info:
                info_streamed, info_stored = self._stream_insert(
                    conn, self.INFO_TABLE, info_reader(),
                    info_required_columns or set(), "account_info",
                )

            conn.execute(
                "INSERT INTO dcad_index_build_meta "
                "(id, source_fingerprint, has_info_table, build_complete, built_at, "
                " row_count_appraisal, row_count_info) "
                "VALUES (1, ?, ?, 1, ?, ?, ?)",
                (fingerprint, int(has_info), _utc_now(), appraisal_stored, info_stored),
            )
            conn.commit()
            return {
                "appraisal_streamed": appraisal_streamed, "appraisal_stored": appraisal_stored,
                "appraisal_duplicates": appraisal_streamed - appraisal_stored,
                "info_streamed": info_streamed, "info_stored": info_stored,
                "info_duplicates": info_streamed - info_stored,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _stream_insert(self, conn, table: str, rows_iterable, required_columns: set, label: str) -> tuple:
        """Returns (rows_streamed, rows_actually_stored). A duplicate
        (account_num, appraisal_yr) key is handled with INSERT OR
        IGNORE -- same first-seen-wins semantics the original in-memory
        dict index had (a dict assignment to an existing key would
        normally overwrite, but the original code explicitly checked
        `if key in index: continue` before inserting, i.e. first-seen
        wins, later duplicates dropped -- OR IGNORE reproduces that
        exactly, since it's a no-op against an existing PRIMARY KEY)."""
        batch = []
        streamed = 0
        first_row = True
        for row in rows_iterable:
            if first_row:
                if required_columns and not required_columns.issubset(set(row.keys())):
                    raise DCADIndexBuildError(label, "missing required columns in source header")
                first_row = False
            account_num = row.get("ACCOUNT_NUM")
            appraisal_yr = row.get("APPRAISAL_YR")
            batch.append((account_num, appraisal_yr, json.dumps(row)))
            streamed += 1
            if len(batch) >= self.batch_size:
                self._flush_batch(conn, table, batch)
                batch = []
        if batch:
            self._flush_batch(conn, table, batch)
        stored = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return streamed, stored

    def _flush_batch(self, conn, table: str, batch: list):
        if len(batch) > self.configured_batch_size:
            raise AssertionError(
                f"DCAD index batch exceeded configured size: "
                f"{len(batch)} > {self.configured_batch_size}"
            )
        self.max_observed_batch_size = max(self.max_observed_batch_size, len(batch))
        conn.executemany(
            f"INSERT OR IGNORE INTO {table} (account_num, appraisal_yr, row_json) VALUES (?, ?, ?)",
            batch,
        )

    # ---- lookups -------------------------------------------------------

    def lookup(self, table: str, account_num: str, appraisal_yr: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT row_json FROM {table} WHERE account_num = ? AND appraisal_yr = ?",
                (account_num, appraisal_yr),
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def lookup_appraisal(self, account_num: str, appraisal_yr: str) -> dict | None:
        return self.lookup(self.APPRAISAL_TABLE, account_num, appraisal_yr)

    def lookup_info(self, account_num: str, appraisal_yr: str) -> dict | None:
        return self.lookup(self.INFO_TABLE, account_num, appraisal_yr)
