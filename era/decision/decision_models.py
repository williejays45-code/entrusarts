from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.decision.decision_enums import DecisionState, DecisionReason
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class DecisionInput:
    property_id: str
    evidence_count: int
    required_fields_present: bool
    has_conflicts: bool
    has_policy_violation: bool
    manual_review_flag: bool
    single_source_only: bool
    export_ready: bool
    supporting_evidence_ids: list
@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    property_id: str
    decision: DecisionState
    reason: DecisionReason
    requires_manual_review: bool
    supporting_evidence_ids: list
    created_at: str = field(default_factory=utc_now)
