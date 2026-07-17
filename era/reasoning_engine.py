from dataclasses import dataclass
from era.evidence_graph import EvidenceRepository
from era.weight_registry import WeightRegistry
from era.decision_trace import DecisionTraceRepository, create_decision_trace
from persistence.repository import ScoreEntryRepository, SimpleScoreEntry
CONFIDENCE_RANK = {
    "UNSUPPORTED": 0,
    "REJECTED": 0,
    "DRAFT": 1,
    "PLACEHOLDER": 1,
    "PARTIAL": 2,
    "ESTIMATED": 2,
    "VERIFIED": 3,
    "VALID": 3,
}
@dataclass
class ERAReasoningResult:
    engine: str
    metric: str
    base_score: float
    adjusted_score: float
    confidence: str
    reason: str
    recommended_action: str
    persisted: bool
def weakest_confidence(labels):
    if not labels:
        return "UNSUPPORTED"
    weakest = min(labels, key=lambda label: CONFIDENCE_RANK.get(label.upper(), 0))
    return weakest.upper()
def action_from_confidence(confidence: str) -> str:
    confidence = confidence.upper()
    if confidence in {"UNSUPPORTED", "REJECTED"}:
        return "REANCHOR_AND_REVIEW"
    if confidence in {"DRAFT", "PLACEHOLDER", "PARTIAL", "ESTIMATED"}:
        return "REANCHOR_AND_REVIEW"
    return "CONTINUE"
class ERAReasoningEngine:
    def __init__(self, db_path: str = "eri_persistence.db"):
        self.db_path = db_path
        self.evidence_repo = EvidenceRepository(db_path)
        self.weight_registry = WeightRegistry(db_path)
        self.score_repo = ScoreEntryRepository(db_path)
        self.trace_repo = DecisionTraceRepository(db_path)
    def evaluate(self, engine: str, metric: str, base_score: float) -> ERAReasoningResult:
        evidence_rows = self.evidence_repo.load_for_score(engine, metric)
        weights = self.weight_registry.load_for_metric(engine, metric)
        weight_by_type = {w.evidence_type: w for w in weights}
        if not evidence_rows:
            confidence = "UNSUPPORTED"
            adjusted_score = 0.0
            reason = "No evidence records found. Reasoning blocked."
            recommended_action = "REANCHOR_AND_REVIEW"
        else:
            weighted_total = 0.0
            applied_weight = 0.0
            confidence_inputs = []
            for row in evidence_rows:
                evidence_type = row[4]
                source_value = row[6]
                evidence_confidence = row[7]
                validator_status = row[8]
                weight = weight_by_type.get(evidence_type)
                if weight is None:
                    confidence_inputs.append("UNSUPPORTED")
                    continue
                confidence_inputs.append(evidence_confidence)
                confidence_inputs.append(validator_status)
                confidence_inputs.append(weight.status)
                weighted_total += float(base_score) * float(weight.weight_value)
                applied_weight += float(weight.weight_value)
            if applied_weight <= 0:
                confidence = "UNSUPPORTED"
                adjusted_score = 0.0
                reason = "Evidence exists, but no usable registered weights were found."
                recommended_action = "REANCHOR_AND_REVIEW"
            else:
                adjusted_score = round(weighted_total / applied_weight, 2)
                confidence = weakest_confidence(confidence_inputs)
                if confidence in {"PLACEHOLDER", "DRAFT", "PARTIAL", "ESTIMATED"}:
                    confidence = "PARTIAL"
                recommended_action = action_from_confidence(confidence)
                reason = (
                    f"{metric} evaluated from {len(evidence_rows)} evidence records. "
                    f"Applied weight total: {round(applied_weight, 4)}. "
                    f"Confidence capped at {confidence} by weakest evidence/weight status."
                )
        self.score_repo.save(SimpleScoreEntry(
            engine=engine,
            metric=metric,
            score=adjusted_score,
            confidence=confidence,
            assumption_type="PLACEHOLDER" if confidence != "VERIFIED" else "VERIFIED",
            notes=reason,
        ))
        trace = create_decision_trace(
            engine=engine,
            metric=metric,
            score_value=adjusted_score,
            confidence=confidence,
            decision_context="ERA reasoning engine evaluation",
            decision_impact="ACQUISITION",
            reason=reason,
        )
        self.trace_repo.save(trace)
        return ERAReasoningResult(
            engine=engine,
            metric=metric,
            base_score=base_score,
            adjusted_score=adjusted_score,
            confidence=confidence,
            reason=reason,
            recommended_action=recommended_action,
            persisted=True,
        )
