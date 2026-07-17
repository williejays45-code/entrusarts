from dataclasses import dataclass
from typing import List
from era.recommendation.recommendation_states import RecommendationState
from era.recommendation import recommendation_errors as errors
@dataclass(frozen=True)
class DependencyValidationResult:
    valid: bool
    state: RecommendationState
    reason: str
class DependencyValidator:
    def validate(
        self,
        supporting_evidence: List,
        blocking_dependencies: List,
        decision_trace_id: str,
        methodology_version: str,
    ) -> DependencyValidationResult:
        if not decision_trace_id:
            return DependencyValidationResult(False, RecommendationState.INCOMPLETE, errors.TRACE_REQUIRED)
        if not methodology_version:
            return DependencyValidationResult(False, RecommendationState.INCOMPLETE, errors.DEPENDENCY_INCOMPLETE)
        if not supporting_evidence:
            return DependencyValidationResult(False, RecommendationState.INCOMPLETE, "INCOMPLETE")
        if any(str(ev.status).upper() == "UNSUPPORTED" for ev in supporting_evidence):
            return DependencyValidationResult(False, RecommendationState.UNSUPPORTED, errors.UNSUPPORTED)
        if not blocking_dependencies:
            return DependencyValidationResult(False, RecommendationState.INCOMPLETE, errors.BLOCKING_DEPENDENCY_REQUIRED)
        return DependencyValidationResult(True, RecommendationState.PARTIAL, "VALID")
