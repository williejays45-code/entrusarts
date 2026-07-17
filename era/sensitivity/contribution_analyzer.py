from era.sensitivity.contribution_levels import ContributionLevel
from era.sensitivity.contribution_models import ContributionRecord, ContributionAnalysis, utc_now
from era.sensitivity.sensitivity_audit import SensitivityAuditPublisher
from era.sensitivity import sensitivity_errors as errors
from era.shared.confidence import CONFIDENCE_ORDER, effective_confidence
class ContributionAnalyzer:
    def __init__(self):
        self.audit = SensitivityAuditPublisher()
    def attempt_write(self, target: str):
        if target in {
            "evidence",
            "calibration",
            "weight_registry",
            "decision_trace",
            "recommendation",
            "confidence",
        }:
            self.audit.publish("SENSITIVITY_BLOCKED", {
                "reason": errors.READ_ONLY_ENGINE,
                "target": target,
            })
            return False, errors.READ_ONLY_ENGINE
        return True, errors.PASS
    def attempt_confidence_calculation(self):
        self.audit.publish("SENSITIVITY_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
    def analyze(self, recommendation_id: str, inputs: list):
        if not inputs:
            self.audit.publish("SENSITIVITY_BLOCKED", {
                "reason": errors.DEPENDENCY_INCOMPLETE,
            })
            return errors.DEPENDENCY_INCOMPLETE, None
        first = inputs[0]
        if not first.decision_trace_id:
            self.audit.publish("SENSITIVITY_BLOCKED", {
                "reason": errors.TRACE_REQUIRED,
            })
            return errors.TRACE_REQUIRED, None
        if not first.methodology_version:
            self.audit.publish("SENSITIVITY_BLOCKED", {
                "reason": errors.METHODOLOGY_REQUIRED,
            })
            return errors.METHODOLOGY_REQUIRED, None
        records = []
        for item in inputs:
            # Dependency fields describe required upstream evidence/calibration state.
            # Missing calibration_status must return DEPENDENCY_INCOMPLETE, not TRACE_INCOMPLETE.
            dependency_required = [
                item.evidence_id,
                item.evidence_type,
                item.reliability_status,
                item.calibration_status,
                item.weight_status,
            ]
            if any(value is None or value == "" for value in dependency_required):
                self.audit.publish("SENSITIVITY_BLOCKED", {
                    "reason": errors.DEPENDENCY_INCOMPLETE,
                    "evidence_id": item.evidence_id,
                })
                return errors.DEPENDENCY_INCOMPLETE, None
            # Trace fields identify reproducibility references.
            # Missing weight_id/version means the contribution cannot be traced.
            trace_required = [
                item.weight_id,
                item.weight_version,
                item.decision_trace_id,
            ]
            if any(value is None or value == "" for value in trace_required):
                self.audit.publish("SENSITIVITY_BLOCKED", {
                    "reason": errors.TRACE_INCOMPLETE,
                    "evidence_id": item.evidence_id,
                })
                return errors.TRACE_INCOMPLETE, None
            if str(item.evidence_status).upper() == "UNSUPPORTED":
                self.audit.publish("SENSITIVITY_BLOCKED", {
                    "reason": errors.UNSUPPORTED,
                    "evidence_id": item.evidence_id,
                })
                return errors.UNSUPPORTED, None
            if str(item.weight_status).upper() == "PLACEHOLDER" and str(item.calibration_status).upper() != "PLACEHOLDER":
                self.audit.publish("SENSITIVITY_BLOCKED", {
                    "reason": errors.PLACEHOLDER_VISIBILITY_VIOLATION,
                    "evidence_id": item.evidence_id,
                })
                return errors.PLACEHOLDER_VISIBILITY_VIOLATION, None
            contribution_level = self._derive_contribution_level(item)
            record = ContributionRecord(
                evidence_id=item.evidence_id,
                evidence_type=item.evidence_type,
                evidence_reliability=item.reliability_status,
                calibration_status=item.calibration_status,
                weight_id=item.weight_id,
                weight_version=item.weight_version,
                weight_status=item.weight_status,
                contribution_level=contribution_level,
                supporting_explanation=f"{item.evidence_type} contributed at {contribution_level.value} level.",
                decision_trace_id=item.decision_trace_id,
                audit_reference=f"AUD-{item.evidence_id}",
            )
            records.append(record)
        confidence = effective_confidence(*[item.effective_confidence for item in inputs])
        analysis = ContributionAnalysis(
            recommendation_id=recommendation_id,
            decision_trace_id=first.decision_trace_id,
            methodology_version=first.methodology_version,
            overall_confidence=confidence,
            contributions=records,
            generated_at=utc_now(),
        )
        self.audit.publish("CONTRIBUTION_GENERATED", {
            "recommendation_id": recommendation_id,
            "decision_trace_id": first.decision_trace_id,
            "methodology_version": first.methodology_version,
            "count": len(records),
        })
        return errors.PASS, analysis
    def _derive_contribution_level(self, item):
        status = effective_confidence(
            item.reliability_status,
            item.calibration_status,
            item.weight_status,
            item.effective_confidence,
        )
        if status in {"VERIFIED", "SUPPORTED"}:
            return ContributionLevel.CRITICAL
        if status == "VALIDATED":
            return ContributionLevel.HIGH
        if status in {"PARTIAL", "ESTIMATED"}:
            return ContributionLevel.MODERATE
        if status in {"DRAFT", "PLACEHOLDER"}:
            return ContributionLevel.LOW
        return ContributionLevel.MINIMAL
