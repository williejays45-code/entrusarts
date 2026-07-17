from dataclasses import dataclass
from datetime import datetime, timezone
@dataclass(frozen=True)
class TraceAssemblyInput:
    trace_id: str
    evidence_id: str
    evidence_reliability: str
    weight_id: str
    weight_version: str
    calibration_version: str
    methodology_id: str
    methodology_version: str
    contribution_id: str
@dataclass(frozen=True)
class DependencyTrace:
    trace_id: str
    recommendation_id: str
    recommendation_state: str
    confidence: str
    evidence_id: str
    evidence_reliability: str
    weight_id: str
    weight_version: str
    calibration_version: str
    methodology_id: str
    methodology_version: str
    contribution_id: str
    finalized: bool
    created_at: str
def utc_now():
    return datetime.now(timezone.utc).isoformat()
