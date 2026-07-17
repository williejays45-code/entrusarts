import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
@dataclass
class DecisionTrace:
    trace_id: str
    score_entry_id: str
    engine: str
    metric: str
    score_value: float
    confidence: str
    decision_context: str
    decision_impact: str
    reason: str
    recovery_action: str
def determine_recovery_action(confidence: str, decision_impact: str) -> str:
    confidence = confidence.upper()
    impact = decision_impact.upper()
    if confidence in {"REJECTED", "UNSUPPORTED"}:
        return "REANCHOR_AND_REVIEW"
    if confidence in {"DRAFT", "PLACEHOLDER"}:
        return "REANCHOR"
    if confidence == "PARTIAL" and impact in {"HIGH", "CAPITAL_DECISION", "ACQUISITION"}:
        return "REANCHOR_AND_REVIEW"
    if confidence == "PARTIAL":
        return "MONITOR"
    return "CONTINUE"
class DecisionTraceRepository:
    def __init__(self, db_path: str = "eri_persistence.db"):
        self.db_path = db_path
    def save(self, trace: DecisionTrace) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO decision_trace (
                    trace_id,
                    score_entry_id,
                    engine,
                    metric,
                    score_value,
                    confidence,
                    decision_context,
                    decision_impact,
                    reason,
                    recovery_action,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.score_entry_id,
                    trace.engine,
                    trace.metric,
                    float(trace.score_value),
                    trace.confidence,
                    trace.decision_context,
                    trace.decision_impact,
                    trace.reason,
                    trace.recovery_action,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    def load_all(self):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                """
                SELECT
                    trace_id,
                    score_entry_id,
                    engine,
                    metric,
                    score_value,
                    confidence,
                    decision_context,
                    decision_impact,
                    reason,
                    recovery_action,
                    created_at
                FROM decision_trace
                ORDER BY id
                """
            ).fetchall()
        finally:
            conn.close()
def create_decision_trace(
    engine: str,
    metric: str,
    score_value: float,
    confidence: str,
    decision_context: str,
    decision_impact: str,
    reason: str,
) -> DecisionTrace:
    score_entry_id = f"{engine}:{metric}"
    recovery_action = determine_recovery_action(confidence, decision_impact)
    trace_id = f"{score_entry_id}:{datetime.now(timezone.utc).isoformat()}"
    return DecisionTrace(
        trace_id=trace_id,
        score_entry_id=score_entry_id,
        engine=engine,
        metric=metric,
        score_value=score_value,
        confidence=confidence,
        decision_context=decision_context,
        decision_impact=decision_impact,
        reason=reason,
        recovery_action=recovery_action,
    )
