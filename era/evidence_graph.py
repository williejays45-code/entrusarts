import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
@dataclass
class EvidenceRecord:
    evidence_id: str
    score_entry_id: str
    engine: str
    metric: str
    evidence_type: str
    source_name: str
    source_value: str
    confidence: str
    validator_status: str
    notes: str = ""
class EvidenceRepository:
    def __init__(self, db_path: str = "eri_persistence.db"):
        self.db_path = db_path
    def save(self, record: EvidenceRecord) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_records (
                    evidence_id,
                    score_entry_id,
                    engine,
                    metric,
                    evidence_type,
                    source_name,
                    source_value,
                    confidence,
                    validator_status,
                    notes,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.evidence_id,
                    record.score_entry_id,
                    record.engine,
                    record.metric,
                    record.evidence_type,
                    record.source_name,
                    record.source_value,
                    record.confidence,
                    record.validator_status,
                    record.notes,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    def load_for_score(self, engine: str, metric: str):
        score_entry_id = f"{engine}:{metric}"
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                """
                SELECT
                    evidence_id,
                    score_entry_id,
                    engine,
                    metric,
                    evidence_type,
                    source_name,
                    source_value,
                    confidence,
                    validator_status,
                    notes,
                    created_at
                FROM evidence_records
                WHERE score_entry_id = ?
                ORDER BY id
                """,
                (score_entry_id,),
            ).fetchall()
        finally:
            conn.close()
def create_evidence_record(
    engine: str,
    metric: str,
    evidence_type: str,
    source_name: str,
    source_value: str,
    confidence: str,
    validator_status: str,
    notes: str = "",
) -> EvidenceRecord:
    score_entry_id = f"{engine}:{metric}"
    stamp = datetime.now(timezone.utc).isoformat()
    evidence_id = f"{score_entry_id}:{evidence_type}:{source_name}:{stamp}"
    return EvidenceRecord(
        evidence_id=evidence_id,
        score_entry_id=score_entry_id,
        engine=engine,
        metric=metric,
        evidence_type=evidence_type,
        source_name=source_name,
        source_value=source_value,
        confidence=confidence,
        validator_status=validator_status,
        notes=notes,
    )
