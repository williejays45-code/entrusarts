from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
from era.recommendation.recommendation_states import RecommendationState
@dataclass(frozen=True)
class SupportingEvidence:
    evidence_id: str
    description: str
    status: str
@dataclass(frozen=True)
class BlockingDependency:
    dependency_id: str
    description: str
    status: str
@dataclass(frozen=True)
class Recommendation:
    recommendation_id: str
    recommendation: str
    state: RecommendationState
    supporting_evidence: List[SupportingEvidence]
    blocking_dependencies: List[BlockingDependency]
    sensitivity_trace_id: str
    decision_trace_id: str
    confidence: str
    methodology_version: str
    created_at: str
@dataclass(frozen=True)
class RecommendationResult:
    accepted: bool
    state: RecommendationState
    reason: str
    recommendation: Recommendation | None
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
