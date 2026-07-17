from era.recommendation.recommendation_states import RecommendationState
from era.recommendation import recommendation_errors as errors
class RecommendationEvaluator:
    """
    Trust boundary (C2): this evaluator does not rank or compute
    confidence. It only reads the confidence label handed to it (already
    resolved upstream by ContributionAnalyzer via
    era.shared.confidence.effective_confidence) and applies
    recommendation-domain policy: whether the requested state is allowed
    given that label. Case normalization below is string hygiene, not a
    trust judgment -- it does not consult era.shared.confidence or any
    ranking table.
    """
    def evaluate(self, dependency_state: RecommendationState, confidence: str, requested_state: RecommendationState):
        actual_confidence = str(confidence).upper()
        if requested_state == RecommendationState.SUPPORTED and actual_confidence not in {"VERIFIED", "SUPPORTED"}:
            return RecommendationState.PARTIAL, errors.CONFIDENCE_CEILING_VIOLATION
        if dependency_state in {RecommendationState.INCOMPLETE, RecommendationState.UNSUPPORTED}:
            return dependency_state, dependency_state.value
        if actual_confidence in {"UNSUPPORTED", "PLACEHOLDER", "DRAFT"}:
            return RecommendationState.UNSUPPORTED, errors.UNSUPPORTED
        if actual_confidence in {"ESTIMATED", "PARTIAL"}:
            return RecommendationState.PARTIAL, "PARTIAL"
        return requested_state, "SUPPORTED"
