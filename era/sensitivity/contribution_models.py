from dataclasses import dataclass
from datetime import datetime, timezone
from era.sensitivity.contribution_levels import ContributionLevel
@dataclass(frozen=True)
class ContributionInput:
    recommendation_id: str
    decision_trace_id: str
    evidence_id: str
    evidence_type: str
    evidence_status: str
    reliability_status: str
    calibration_status: str
    weight_id: str
    weight_version: str
    weight_status: str
    methodology_version: str
    effective_confidence: str
@dataclass(frozen=True)
class ContributionRecord:
    evidence_id: str
    evidence_type: str
    evidence_reliability: str
    calibration_status: str
    weight_id: str
    weight_version: str
    weight_status: str
    contribution_level: ContributionLevel
    supporting_explanation: str
    decision_trace_id: str
    audit_reference: str
@dataclass(frozen=True)
class ContributionAnalysis:
    recommendation_id: str
    decision_trace_id: str
    methodology_version: str
    overall_confidence: str
    contributions: list
    generated_at: str
def utc_now():
    return datetime.now(timezone.utc).isoformat()
