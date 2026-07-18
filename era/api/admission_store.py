"""Transactional API admission and privacy-safe audit-intent outbox."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone


class AdmissionExpired(RuntimeError):
    pass


class AdmissionCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class AdmissionIntent:
    admission_id: str
    correlation_id: str
    candidate_digest: str
    response_json: str
    audit_event_type: str
    audit_payload: dict


class AdmissionStore:
    """One SQLite transaction commits ADMITTED state plus its audit intent."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._memory = None
        if path == ":memory:":
            self._memory = sqlite3.connect(":memory:", check_same_thread=False)
        self._ensure_schema()

    def _connect(self):
        if self._memory is not None:
            return self._memory
        return sqlite3.connect(self.path, timeout=0.0)

    def _ensure_schema(self):
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS api_admissions (
                        admission_id TEXT PRIMARY KEY,
                        correlation_id TEXT NOT NULL,
                        candidate_digest TEXT NOT NULL,
                        response_json TEXT NOT NULL,
                        admitted_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS api_audit_outbox (
                        event_id TEXT PRIMARY KEY,
                        admission_id TEXT NOT NULL UNIQUE,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        delivery_state TEXT NOT NULL CHECK(delivery_state IN ('PENDING','DELIVERED')),
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(admission_id) REFERENCES api_admissions(admission_id)
                    );
                """)
                conn.commit()
            finally:
                if self._memory is None:
                    conn.close()

    def admit(self, intent, deadline, monotonic, authorized, cancelled):
        """Transition PREPARED -> ADMITTED exactly once or commit nothing."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if cancelled():
                    raise AdmissionCancelled("ADMISSION_CANCELLED")
                if monotonic() >= deadline:
                    raise AdmissionExpired("ADMISSION_EXPIRED")
                if not authorized():
                    raise PermissionError("AUTHENTICATION_FAILED")
                existing = conn.execute(
                    "SELECT candidate_digest, response_json FROM api_admissions WHERE admission_id = ?",
                    (intent.admission_id,),
                ).fetchone()
                if existing is not None:
                    if existing == (intent.candidate_digest, intent.response_json):
                        conn.rollback()
                        return "ALREADY_ADMITTED"
                    raise RuntimeError("DUPLICATE_ADMISSION_REJECTED")
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO api_admissions VALUES (?, ?, ?, ?, ?)",
                    (intent.admission_id, intent.correlation_id, intent.candidate_digest,
                     intent.response_json, now),
                )
                event_id = f"{intent.admission_id}:API_ANALYZE_ALLOWED"
                conn.execute(
                    "INSERT INTO api_audit_outbox VALUES (?, ?, ?, ?, 'PENDING', ?)",
                    (event_id, intent.admission_id, intent.audit_event_type,
                     json.dumps(intent.audit_payload, sort_keys=True, separators=(",", ":")), now),
                )
                if cancelled():
                    raise AdmissionCancelled("ADMISSION_CANCELLED")
                if monotonic() >= deadline:
                    raise AdmissionExpired("ADMISSION_EXPIRED")
                if not authorized():
                    raise PermissionError("AUTHENTICATION_FAILED")
                conn.commit()
                return "ADMITTED"
            except Exception:
                conn.rollback()
                raise
            finally:
                if self._memory is None:
                    conn.close()

    def claim_pending(self, admission_id):
        """Atomically claim once before external best-effort publication."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT event_type, payload_json FROM api_audit_outbox "
                    "WHERE admission_id = ? AND delivery_state = 'PENDING'",
                    (admission_id,),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    return None
                conn.execute(
                    "UPDATE api_audit_outbox SET delivery_state = 'DELIVERED' WHERE admission_id = ?",
                    (admission_id,),
                )
                conn.commit()
                return row[0], json.loads(row[1])
            except Exception:
                conn.rollback()
                raise
            finally:
                if self._memory is None:
                    conn.close()

    def counts(self):
        with self._lock:
            conn = self._connect()
            try:
                return (
                    conn.execute("SELECT COUNT(*) FROM api_admissions").fetchone()[0],
                    conn.execute("SELECT COUNT(*) FROM api_audit_outbox").fetchone()[0],
                )
            finally:
                if self._memory is None:
                    conn.close()
