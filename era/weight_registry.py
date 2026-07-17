import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
@dataclass
class WeightRecord:
    weight_id: str
    engine: str
    metric: str
    evidence_type: str
    weight_value: float
    status: str
    source: str
    notes: str = ""
class WeightRegistry:
    def __init__(self, db_path: str = "eri_persistence.db"):
        self.db_path = db_path
    def save(self, record: WeightRecord) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO weight_registry (
                    weight_id,
                    engine,
                    metric,
                    evidence_type,
                    weight_value,
                    status,
                    source,
                    notes,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.weight_id,
                    record.engine,
                    record.metric,
                    record.evidence_type,
                    float(record.weight_value),
                    record.status,
                    record.source,
                    record.notes,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    def load_for_metric(self, engine: str, metric: str):
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT
                    weight_id,
                    engine,
                    metric,
                    evidence_type,
                    weight_value,
                    status,
                    source,
                    notes
                FROM weight_registry
                WHERE engine = ? AND metric = ?
                ORDER BY id
                """,
                (engine, metric),
            ).fetchall()
            return [
                WeightRecord(
                    weight_id=row[0],
                    engine=row[1],
                    metric=row[2],
                    evidence_type=row[3],
                    weight_value=row[4],
                    status=row[5],
                    source=row[6],
                    notes=row[7] or "",
                )
                for row in rows
            ]
        finally:
            conn.close()
def seed_default_ths_weights(db_path: str = "eri_persistence.db") -> None:
    registry = WeightRegistry(db_path)
    defaults = [
        WeightRecord(
            weight_id="ERA:THS:score_input",
            engine="ERA",
            metric="THS",
            evidence_type="score_input",
            weight_value=0.45,
            status="PLACEHOLDER",
            source="Founder draft weighting, pending validation",
            notes="Temporary reasoning weight for score-history evidence.",
        ),
        WeightRecord(
            weight_id="ERA:THS:decision_trace",
            engine="ERA",
            metric="THS",
            evidence_type="decision_trace",
            weight_value=0.25,
            status="PLACEHOLDER",
            source="Founder draft weighting, pending validation",
            notes="Temporary reasoning weight for recovery-action evidence.",
        ),
        WeightRecord(
            weight_id="ERA:THS:governance",
            engine="ERA",
            metric="THS",
            evidence_type="governance",
            weight_value=0.30,
            status="PLACEHOLDER",
            source="Founder draft weighting, pending validation",
            notes="Temporary reasoning weight for governance-law evidence.",
        ),
    ]
    for record in defaults:
        registry.save(record)
