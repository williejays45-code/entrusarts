import sqlite3
from dataclasses import dataclass
@dataclass
class SimpleScoreEntry:
    engine: str
    metric: str
    score: float
    confidence: str
    assumption_type: str
    notes: str = ""
class ScoreEntryRepository:
    def __init__(self, db_path: str = "eri_persistence.db"):
        self.db_path = db_path
    def save(self, entry: SimpleScoreEntry) -> None:
        entry_id = f"{entry.engine}:{entry.metric}"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT OR REPLACE INTO score_entries (
                    id,
                    engine,
                    score_name,
                    value,
                    confidence,
                    validator_status,
                    weight_table,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    entry_id,
                    entry.engine,
                    entry.metric,
                    float(entry.score),
                    entry.confidence,
                    entry.assumption_type,
                    entry.notes,
                ),
            )
            conn.execute(
                """
                INSERT INTO score_history (
                    score_entry_id,
                    engine,
                    score_name,
                    value,
                    confidence,
                    validator_status,
                    weight_table,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    entry_id,
                    entry.engine,
                    entry.metric,
                    float(entry.score),
                    entry.confidence,
                    entry.assumption_type,
                    entry.notes,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    def load(self, engine: str, metric: str) -> SimpleScoreEntry:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT
                    engine,
                    score_name,
                    value,
                    confidence,
                    validator_status,
                    weight_table
                FROM score_entries
                WHERE id = ?
                """,
                (f"{engine}:{metric}",),
            ).fetchone()
            if row is None:
                raise KeyError(f"No score entry found for {engine}:{metric}")
            return SimpleScoreEntry(
                engine=row[0],
                metric=row[1],
                score=row[2],
                confidence=row[3],
                assumption_type=row[4],
                notes=row[5] or "",
            )
        finally:
            conn.close()
