import sqlite3
from era.calibration_engine import CalibrationResult
class CalibrationStore:
    def __init__(self, db_path: str = "eri_persistence.db"):
        self.db_path = db_path
        self._ensure_tables()
    def _ensure_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS calibration_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weight_id TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                reason TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                methodology_version TEXT NOT NULL,
                effective_confidence TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS calibration_weight_registry (
                weight_id TEXT PRIMARY KEY,
                current_status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            conn.commit()
        finally:
            conn.close()
    def apply_result_atomic(self, result: CalibrationResult) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("BEGIN")
            conn.execute("""
            INSERT INTO calibration_audit (
                weight_id,
                previous_status,
                new_status,
                accepted,
                reason,
                policy_version,
                methodology_version,
                effective_confidence,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.weight_id,
                result.previous_status,
                result.new_status,
                1 if result.accepted else 0,
                result.reason,
                result.policy_version,
                result.methodology_version,
                result.effective_confidence,
                result.created_at,
            ))
            if result.accepted:
                conn.execute("""
                INSERT OR REPLACE INTO calibration_weight_registry (
                    weight_id,
                    current_status,
                    updated_at
                )
                VALUES (?, ?, ?)
                """, (
                    result.weight_id,
                    result.new_status,
                    result.created_at,
                ))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    def load_status(self, weight_id: str):
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("""
            SELECT current_status
            FROM calibration_weight_registry
            WHERE weight_id = ?
            """, (weight_id,)).fetchone()
            return None if row is None else row[0]
        finally:
            conn.close()
    def load_audit(self, weight_id: str):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("""
            SELECT weight_id, previous_status, new_status, accepted, reason, effective_confidence
            FROM calibration_audit
            WHERE weight_id = ?
            ORDER BY id
            """, (weight_id,)).fetchall()
        finally:
            conn.close()
