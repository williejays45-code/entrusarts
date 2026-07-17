from era.recommendation.recommendation_models import Recommendation, RecommendationResult, utc_now
from era.recommendation.recommendation_states import RecommendationState
from era.recommendation import recommendation_errors as errors
class RecommendationBuilder:
    """
    Trust boundary (C2): confidence and sensitivity_trace_id arrive here
    only after RecommendationEngine has already sourced them verbatim
    from an upstream ContributionAnalysis and confirmed trace linkage.
    This builder does not accept a raw confidence override -- there is no
    "injected_confidence" bypass path anymore; confidence can only ever
    reach this class through the verified upstream analysis.
    """
    def build(
        self,
        recommendation_id: str,
        recommendation_text: str,
        state: RecommendationState,
        supporting_evidence,
        blocking_dependencies,
        sensitivity_trace_id: str,
        decision_trace_id: str,
        confidence: str,
        methodology_version: str,
    ) -> RecommendationResult:
        if not decision_trace_id:
            return RecommendationResult(False, RecommendationState.INCOMPLETE, errors.TRACE_REQUIRED, None)
        rec = Recommendation(
            recommendation_id=recommendation_id,
            recommendation=recommendation_text,
            state=state,
            supporting_evidence=supporting_evidence,
            blocking_dependencies=blocking_dependencies,
            sensitivity_trace_id=sensitivity_trace_id,
            decision_trace_id=decision_trace_id,
            confidence=confidence,
            methodology_version=methodology_version,
            created_at=utc_now(),
        )
        return RecommendationResult(True, state, "RECOMMENDATION_CREATED", rec)
