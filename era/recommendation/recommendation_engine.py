from era.recommendation.doctrine_loader import DoctrineLoader
from era.recommendation.dependency_validator import DependencyValidator
from era.recommendation.recommendation_evaluator import RecommendationEvaluator
from era.recommendation.recommendation_builder import RecommendationBuilder
from era.recommendation.audit_publisher import AuditPublisher
from era.recommendation.recommendation_states import RecommendationState
from era.recommendation import recommendation_errors as errors
class RecommendationEngine:
    """
    Trust boundary (C2): this engine does not compute confidence, does not
    rank/interpret reliability, and does not accept confidence as a raw
    caller-supplied value. Confidence and methodology_version are read
    verbatim from a `sensitivity_analysis` object -- a
    era.sensitivity.contribution_models.ContributionAnalysis produced by
    ContributionAnalyzer, the module with actual authority over evidence
    trust. RecommendationEngine only:
      - verifies that the analysis was produced for the same decision
        trace this recommendation is being built against (rejects
        mismatched/fabricated trace linkage), and
      - applies its own downstream policy (dependency completeness,
        blocking-dependency gating, confidence-ceiling-vs-requested-state
        gating) using the confidence label as-given, without re-deriving
        or re-ranking it.
    """
    def __init__(self):
        self.doctrine_loader = DoctrineLoader()
        self.validator = DependencyValidator()
        self.evaluator = RecommendationEvaluator()
        self.builder = RecommendationBuilder()
        self.audit = AuditPublisher()
    def attempt_write(self, target: str):
        if target in {"evidence", "calibration", "weight_registry", "decision_trace", "confidence"}:
            return False, errors.READ_ONLY_ENGINE
        return True, "ALLOWED"
    def create_recommendation(
        self,
        supporting_evidence,
        blocking_dependencies,
        decision_trace_id: str,
        sensitivity_analysis,
        requested_state: RecommendationState = RecommendationState.PARTIAL,
    ):
        if sensitivity_analysis is None:
            self.audit.publish("RECOMMENDATION_BLOCKED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
            return errors.CONFIDENCE_AUTHORITY_VIOLATION, None
        if sensitivity_analysis.decision_trace_id != decision_trace_id:
            self.audit.publish("RECOMMENDATION_BLOCKED", {
                "reason": errors.TRACE_MISMATCH,
                "decision_trace_id": decision_trace_id,
                "analysis_trace_id": sensitivity_analysis.decision_trace_id,
            })
            return errors.TRACE_MISMATCH, None
        # Confidence and methodology_version are consumed verbatim from the
        # upstream analysis -- never computed, ranked, or reinterpreted here.
        confidence = sensitivity_analysis.overall_confidence
        methodology_version = sensitivity_analysis.methodology_version
        sensitivity_trace_id = sensitivity_analysis.decision_trace_id
        rules = self.doctrine_loader.load_rules()
        rule = rules[0]
        validation = self.validator.validate(
            supporting_evidence,
            blocking_dependencies,
            decision_trace_id,
            methodology_version,
        )
        if not validation.valid:
            self.audit.publish("RECOMMENDATION_BLOCKED", {"reason": validation.reason})
            return validation.reason, None
        final_state, reason = self.evaluator.evaluate(validation.state, confidence, requested_state)
        if reason == errors.CONFIDENCE_CEILING_VIOLATION:
            self.audit.publish("RECOMMENDATION_BLOCKED", {"reason": reason})
            return reason, None
        built = self.builder.build(
            recommendation_id="REC-001",
            recommendation_text=rule.recommendation,
            state=final_state,
            supporting_evidence=supporting_evidence,
            blocking_dependencies=blocking_dependencies,
            sensitivity_trace_id=sensitivity_trace_id,
            decision_trace_id=decision_trace_id,
            confidence=confidence,
            methodology_version=methodology_version,
        )
        if not built.accepted:
            self.audit.publish("RECOMMENDATION_BLOCKED", {"reason": built.reason})
            return built.reason, None
        self.audit.publish("RECOMMENDATION_TRACE_LINKED", {"decision_trace_id": decision_trace_id})
        self.audit.publish("RECOMMENDATION_CREATED", {"recommendation_id": built.recommendation.recommendation_id})
        return "SUPPORTED" if final_state == RecommendationState.SUPPORTED else final_state.value, built.recommendation
