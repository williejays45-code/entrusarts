from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.policy.policy_enums import PolicyVerdict, PolicyReason
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class PolicyRuleSet:
    policy_id: str
    policy_version: str
    allowed_decisions: list
    export_allowed: bool
    require_manual_review_on_conflict: bool
@dataclass(frozen=True)
class PolicyDecisionInput:
    property_id: str
    decision: str
    has_conflicts: bool
    export_requested: bool
    policy_violation: bool
    supporting_evidence_ids: list
@dataclass(frozen=True)
class PolicyResult:
    policy_id: str
    policy_version: str
    property_id: str
    decision: str
    verdict: PolicyVerdict
    reason: PolicyReason
    supporting_evidence_ids: list
    created_at: str = field(default_factory=utc_now)
