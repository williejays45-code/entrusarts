from dataclasses import dataclass
from datetime import datetime, timezone
CALIBRATION_POLICY_VERSION = "ERA_CALIBRATION_POLICY-1.1"
RELIABILITY_METHODOLOGY_VERSION = "ERA_RELIABILITY_METHODOLOGY-1.0"
STATUS_ORDER = {
    "PLACEHOLDER": 0,
    "ESTIMATED": 1,
    "VALIDATED": 2,
    "VERIFIED": 3,
}
NEXT_STATUS = {
    "PLACEHOLDER": "ESTIMATED",
    "ESTIMATED": "VALIDATED",
    "VALIDATED": "VERIFIED",
}
PREVIOUS_STATUS = {
    "VERIFIED": "VALIDATED",
    "VALIDATED": "ESTIMATED",
    "ESTIMATED": "PLACEHOLDER",
}
@dataclass
class CalibrationRequest:
    weight_id: str
    current_status: str
    requested_status: str
    policy_version: str
    methodology_version: str
    evidence_count: int
    has_supporting_evidence: bool
    has_contradiction: bool
    regression_passed: bool
    audit_available: bool
    founder_approved: bool
    reason: str = ""
@dataclass
class CalibrationResult:
    weight_id: str
    previous_status: str
    new_status: str
    accepted: bool
    reason: str
    policy_version: str
    methodology_version: str
    effective_confidence: str
    created_at: str
def effective_confidence(*labels: str) -> str:
    if not labels:
        return "PLACEHOLDER"
    normalized = [str(label).upper() for label in labels]
    return min(normalized, key=lambda label: STATUS_ORDER.get(label, 0))
def _is_one_step_transition(current_status: str, requested_status: str) -> bool:
    current = current_status.upper()
    requested = requested_status.upper()
    return NEXT_STATUS.get(current) == requested or PREVIOUS_STATUS.get(current) == requested
def evaluate_calibration(request: CalibrationRequest) -> CalibrationResult:
    current = request.current_status.upper()
    requested = request.requested_status.upper()
    if request.policy_version != CALIBRATION_POLICY_VERSION:
        return _reject(request, "POLICY_VERSION_MISMATCH")
    if request.methodology_version != RELIABILITY_METHODOLOGY_VERSION:
        return _reject(request, "METHODOLOGY_VERSION_MISMATCH")
    if current not in STATUS_ORDER or requested not in STATUS_ORDER:
        return _reject(request, "UNKNOWN_STATUS")
    if not _is_one_step_transition(current, requested) and current != requested:
        return _reject(request, "STATUS_SKIP_REJECTED")
    if not request.audit_available:
        return _reject(request, "AUDIT_REQUIRED")
    if request.has_contradiction:
        downgrade = PREVIOUS_STATUS.get(current, current)
        return _accept(request, downgrade, "CONTRADICTION_DOWNGRADE")
    if not request.regression_passed:
        downgrade = PREVIOUS_STATUS.get(current, current)
        return _accept(request, downgrade, "REGRESSION_FAILURE_DOWNGRADE")
    if STATUS_ORDER[requested] > STATUS_ORDER[current]:
        if not request.has_supporting_evidence:
            return _reject(request, "SUPPORTING_EVIDENCE_REQUIRED")
        if request.evidence_count <= 0:
            return _reject(request, "EVIDENCE_COUNT_REQUIRED")
        if not request.founder_approved:
            return _reject(request, "FOUNDER_REVIEW_REQUIRED")
    confidence = effective_confidence(current, requested)
    return CalibrationResult(
        weight_id=request.weight_id,
        previous_status=current,
        new_status=requested,
        accepted=True,
        reason="CALIBRATION_ACCEPTED",
        policy_version=request.policy_version,
        methodology_version=request.methodology_version,
        effective_confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
def _reject(request: CalibrationRequest, reason: str) -> CalibrationResult:
    return CalibrationResult(
        weight_id=request.weight_id,
        previous_status=request.current_status.upper(),
        new_status=request.current_status.upper(),
        accepted=False,
        reason=reason,
        policy_version=request.policy_version,
        methodology_version=request.methodology_version,
        effective_confidence=request.current_status.upper(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
def _accept(request: CalibrationRequest, new_status: str, reason: str) -> CalibrationResult:
    confidence = effective_confidence(request.current_status, new_status)
    return CalibrationResult(
        weight_id=request.weight_id,
        previous_status=request.current_status.upper(),
        new_status=new_status.upper(),
        accepted=True,
        reason=reason,
        policy_version=request.policy_version,
        methodology_version=request.methodology_version,
        effective_confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
