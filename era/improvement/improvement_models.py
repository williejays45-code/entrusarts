from dataclasses import dataclass
from datetime import datetime, timezone
from era.improvement.improvement_states import ImpactLevel, ImprovementStatus
@dataclass(frozen=True)
class ImprovementInput:
    dependency_id: str
    dependency_status: str
    dependency_reference: str
    methodology_id: str
    methodology_reference: str
    evidence_id: str
    trace_id: str
    impact_level: str
    blocking_severity: str
    ease_of_resolution: str
    reason: str
@dataclass(frozen=True)
class ImprovementRecord:
    improvement_id: str
    source: str
    dependency_reference: str
    methodology_reference: str
    evidence_id: str
    impact_level: ImpactLevel
    priority_rank: int
    reason: str
    status: ImprovementStatus
    audit_reference: str
    created_at: str
@dataclass(frozen=True)
class ImprovementAnalysis:
    trace_id: str
    status: ImprovementStatus
    reason: str
    improvements: list
    total_generated: int
    displayed_count: int
    created_at: str
def utc_now():
    return datetime.now(timezone.utc).isoformat()
