from era.improvement.improvement_models import ImprovementRecord, ImprovementAnalysis, utc_now
from era.improvement.improvement_states import ImpactLevel, ImprovementStatus
from era.improvement.improvement_audit import ImprovementAuditPublisher
from era.improvement import improvement_errors as errors
IMPACT_SCORE = {
    "CRITICAL": 5,
    "HIGH": 4,
    "MODERATE": 3,
    "LOW": 2,
    "MINIMAL": 1,
}
SEVERITY_SCORE = {
    "BLOCKING": 3,
    "HIGH": 3,
    "MODERATE": 2,
    "LOW": 1,
    "NONE": 0,
}
EASE_SCORE = {
    "EASY": 3,
    "MODERATE": 2,
    "HARD": 1,
    "UNKNOWN": 0,
}
class ImprovementAnalyzer:
    MAX_DISPLAYED = 5
    def __init__(self):
        self.audit = ImprovementAuditPublisher()
    def attempt_write(self, target: str):
        if target in {"recommendation", "evidence", "weights", "calibration", "methodology"}:
            self.audit.publish("IMPROVEMENT_BLOCKED", {
                "reason": errors.READ_ONLY_ENGINE,
                "target": target,
            })
            return False, errors.READ_ONLY_ENGINE
        if target == "confidence":
            self.audit.publish("IMPROVEMENT_BLOCKED", {
                "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
                "target": target,
            })
            return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
        return True, errors.PASS
    def attempt_weight_disclosure(self):
        self.audit.publish("IMPROVEMENT_BLOCKED", {
            "reason": errors.WEIGHT_DISCLOSURE_VIOLATION,
        })
        return False, errors.WEIGHT_DISCLOSURE_VIOLATION
    def analyze(self, trace_id: str, items: list):
        if not trace_id:
            self.audit.publish("IMPROVEMENT_BLOCKED", {
                "reason": errors.TRACE_REQUIRED,
            })
            return errors.TRACE_REQUIRED, None
        if items is None:
            self.audit.publish("IMPROVEMENT_BLOCKED", {
                "reason": errors.UNKNOWN_DEPENDENCY_REFERENCE,
            })
            return errors.UNKNOWN_DEPENDENCY_REFERENCE, None
        unresolved_items = [
            item for item in items
            if str(item.dependency_status).upper() != "RESOLVED"
        ]
        if len(unresolved_items) == 0:
            analysis = ImprovementAnalysis(
                trace_id=trace_id,
                status=ImprovementStatus.VALIDATED,
                reason=errors.NO_IMPROVEMENTS_REQUIRED,
                improvements=[],
                total_generated=0,
                displayed_count=0,
                created_at=utc_now(),
            )
            self.audit.publish("IMPROVEMENT_VALIDATED", {
                "trace_id": trace_id,
                "reason": errors.NO_IMPROVEMENTS_REQUIRED,
                "total_generated": 0,
                "displayed_count": 0,
            })
            return errors.PASS, analysis
        records = []
        for index, item in enumerate(unresolved_items, start=1):
            if not item.dependency_reference:
                self.audit.publish("IMPROVEMENT_BLOCKED", {
                    "reason": errors.UNKNOWN_DEPENDENCY_REFERENCE,
                })
                return errors.UNKNOWN_DEPENDENCY_REFERENCE, None
            if not item.methodology_reference:
                self.audit.publish("IMPROVEMENT_BLOCKED", {
                    "reason": errors.UNKNOWN_METHODOLOGY_REFERENCE,
                })
                return errors.UNKNOWN_METHODOLOGY_REFERENCE, None
            if not item.methodology_id:
                self.audit.publish("IMPROVEMENT_BLOCKED", {
                    "reason": errors.METHODOLOGY_REQUIRED,
                })
                return errors.METHODOLOGY_REQUIRED, None
            if not item.evidence_id:
                self.audit.publish("IMPROVEMENT_BLOCKED", {
                    "reason": errors.UNKNOWN_EVIDENCE_REFERENCE,
                })
                return errors.UNKNOWN_EVIDENCE_REFERENCE, None
            if str(item.dependency_reference).upper().startswith("UNKNOWN"):
                self.audit.publish("IMPROVEMENT_BLOCKED", {
                    "reason": errors.UNKNOWN_DEPENDENCY_REFERENCE,
                })
                return errors.UNKNOWN_DEPENDENCY_REFERENCE, None
            if str(item.methodology_reference).upper().startswith("UNKNOWN"):
                self.audit.publish("IMPROVEMENT_BLOCKED", {
                    "reason": errors.UNKNOWN_METHODOLOGY_REFERENCE,
                })
                return errors.UNKNOWN_METHODOLOGY_REFERENCE, None
            if str(item.evidence_id).upper().startswith("UNKNOWN"):
                self.audit.publish("IMPROVEMENT_BLOCKED", {
                    "reason": errors.UNKNOWN_EVIDENCE_REFERENCE,
                })
                return errors.UNKNOWN_EVIDENCE_REFERENCE, None
            impact = ImpactLevel(str(item.impact_level).upper())
            record = ImprovementRecord(
                improvement_id=f"IMP-{index:03d}",
                source="DEPENDENCY_TRACE",
                dependency_reference=item.dependency_reference,
                methodology_reference=item.methodology_reference,
                evidence_id=item.evidence_id,
                impact_level=impact,
                priority_rank=self._priority_score(item),
                reason=item.reason,
                status=ImprovementStatus.VALIDATED,
                audit_reference=f"AUD-IMP-{index:03d}",
                created_at=utc_now(),
            )
            records.append(record)
        records = sorted(records, key=lambda rec: (-rec.priority_rank, rec.improvement_id))
        displayed = records[:self.MAX_DISPLAYED]
        analysis = ImprovementAnalysis(
            trace_id=trace_id,
            status=ImprovementStatus.VALIDATED,
            reason=errors.IMPROVEMENT_VALIDATED,
            improvements=displayed,
            total_generated=len(records),
            displayed_count=len(displayed),
            created_at=utc_now(),
        )
        self.audit.publish("IMPROVEMENT_GENERATED", {
            "trace_id": trace_id,
            "total_generated": len(records),
            "displayed_count": len(displayed),
        })
        self.audit.publish("IMPROVEMENT_VALIDATED", {
            "trace_id": trace_id,
            "total_generated": len(records),
            "displayed_count": len(displayed),
        })
        return errors.PASS, analysis
    def _priority_score(self, item):
        return (
            IMPACT_SCORE.get(str(item.impact_level).upper(), 0) * 100
            + SEVERITY_SCORE.get(str(item.blocking_severity).upper(), 0) * 10
            + EASE_SCORE.get(str(item.ease_of_resolution).upper(), 0)
        )
