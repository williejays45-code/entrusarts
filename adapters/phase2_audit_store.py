import sqlite3
from adapters.phase2_contract import AdapterIntent, AdapterOutcome, now_utc
class AdapterAuditStore:
    def __init__(self, db_path: str = "eri_persistence.db"):
        self.db_path = db_path
        self._ensure_table()
    def _ensure_table(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS adapter_phase2_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                source_engine TEXT NOT NULL,
                target_engine TEXT NOT NULL,
                adapter_version TEXT NOT NULL,
                target_interface_version TEXT NOT NULL,
                request_type TEXT NOT NULL,
                request_payload TEXT NOT NULL,
                response_payload TEXT,
                translated_confidence TEXT,
                outcome TEXT NOT NULL,
                failure_state TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_adapter_phase2_request
            ON adapter_phase2_audit(request_id)
            """)
            conn.commit()
        finally:
            conn.close()
    def write_intent(self, intent: AdapterIntent):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
            INSERT INTO adapter_phase2_audit (
                request_id,
                stage,
                source_engine,
                target_engine,
                adapter_version,
                target_interface_version,
                request_type,
                request_payload,
                response_payload,
                translated_confidence,
                outcome,
                failure_state,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                intent.request_id,
                "REQUEST_CREATED",
                intent.source_engine,
                intent.target_engine,
                intent.adapter_version,
                intent.target_interface_version,
                intent.request_type,
                str(intent.payload),
                None,
                None,
                "PENDING",
                "NONE",
                now_utc(),
            ))
            conn.commit()
        finally:
            conn.close()
    def write_outcome(self, intent: AdapterIntent, outcome: AdapterOutcome):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
            INSERT INTO adapter_phase2_audit (
                request_id,
                stage,
                source_engine,
                target_engine,
                adapter_version,
                target_interface_version,
                request_type,
                request_payload,
                response_payload,
                translated_confidence,
                outcome,
                failure_state,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                intent.request_id,
                "REQUEST_FINALIZED",
                intent.source_engine,
                intent.target_engine,
                intent.adapter_version,
                intent.target_interface_version,
                intent.request_type,
                str(intent.payload),
                str(outcome.response_payload),
                outcome.translated_confidence,
                outcome.outcome,
                outcome.failure_state,
                outcome.created_at,
            ))
            conn.commit()
        finally:
            conn.close()
    def prior_final_outcome(self, request_id: str):
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("""
            SELECT translated_confidence, outcome, failure_state, response_payload
            FROM adapter_phase2_audit
            WHERE request_id = ? AND stage = 'REQUEST_FINALIZED'
            ORDER BY id DESC
            LIMIT 1
            """, (request_id,)).fetchone()
            if row is None:
                return None
            return {
                "translated_confidence": row[0],
                "outcome": row[1],
                "failure_state": row[2],
                "response_payload": row[3],
            }
        finally:
            conn.close()
