from era.trace.trace_models import DependencyTrace, utc_now
from era.trace.trace_audit import TraceAuditPublisher
from era.trace import trace_errors as errors
class DependencyTraceEngine:
    def __init__(self):
        self.audit = TraceAuditPublisher()
        self._assembled = {}
    def attempt_write(self, target: str):
        if target in {"evidence", "calibration", "weight_registry", "methodology", "recommendation", "confidence"}:
            self.audit.publish("TRACE_BLOCKED", {"reason": errors.READ_ONLY_ENGINE, "target": target})
            return False, errors.READ_ONLY_ENGINE
        return True, errors.PASS
    def attempt_confidence_override(self):
        self.audit.publish("TRACE_BLOCKED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
    def assemble(self, item):
        required = [
            item.trace_id,
            item.evidence_id,
            item.evidence_reliability,
            item.weight_id,
            item.weight_version,
            item.calibration_version,
            item.methodology_id,
            item.methodology_version,
            item.contribution_id,
        ]
        if any(value is None or value == "" for value in required):
            self.audit.publish("TRACE_BLOCKED", {"reason": errors.TRACE_INCOMPLETE})
            return errors.TRACE_INCOMPLETE, None
        if str(item.evidence_id).upper().startswith("UNKNOWN"):
            self.audit.publish("TRACE_BLOCKED", {"reason": errors.UNKNOWN_EVIDENCE_REFERENCE})
            return errors.UNKNOWN_EVIDENCE_REFERENCE, None
        if str(item.weight_id).upper().startswith("UNKNOWN"):
            self.audit.publish("TRACE_BLOCKED", {"reason": errors.UNKNOWN_WEIGHT_REFERENCE})
            return errors.UNKNOWN_WEIGHT_REFERENCE, None
        self._assembled[item.trace_id] = item
        self.audit.publish("TRACE_ASSEMBLED", {"trace_id": item.trace_id})
        return errors.PASS, item
    def finalize(self, trace_id: str, recommendation_id: str, recommendation_state: str, confidence: str):
        if not trace_id or trace_id not in self._assembled:
            self.audit.publish("TRACE_BLOCKED", {"reason": errors.TRACE_REQUIRED})
            return errors.TRACE_REQUIRED, None
        if not recommendation_id or not recommendation_state:
            self.audit.publish("TRACE_BLOCKED", {"reason": errors.TRACE_REQUIRED})
            return errors.TRACE_REQUIRED, None
        item = self._assembled[trace_id]
        trace = DependencyTrace(
            trace_id=item.trace_id,
            recommendation_id=recommendation_id,
            recommendation_state=recommendation_state,
            confidence=confidence,
            evidence_id=item.evidence_id,
            evidence_reliability=item.evidence_reliability,
            weight_id=item.weight_id,
            weight_version=item.weight_version,
            calibration_version=item.calibration_version,
            methodology_id=item.methodology_id,
            methodology_version=item.methodology_version,
            contribution_id=item.contribution_id,
            finalized=True,
            created_at=utc_now(),
        )
        self.audit.publish("TRACE_CREATED", {"trace_id": trace.trace_id, "recommendation_id": recommendation_id})
        self.audit.publish("TRACE_VALIDATED", {"trace_id": trace.trace_id})
        return errors.PASS, trace
    def modify_trace(self, trace):
        self.audit.publish("TRACE_BLOCKED", {"reason": errors.TRACE_IMMUTABLE})
        return False, errors.TRACE_IMMUTABLE
