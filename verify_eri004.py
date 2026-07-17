from era.calibration_engine import (
    CalibrationRequest,
    CALIBRATION_POLICY_VERSION,
    RELIABILITY_METHODOLOGY_VERSION,
    evaluate_calibration,
)
from era.calibration_store import CalibrationStore
def make_request(**overrides):
    data = {
        "weight_id": "ERA:THS:score_input",
        "current_status": "PLACEHOLDER",
        "requested_status": "ESTIMATED",
        "policy_version": CALIBRATION_POLICY_VERSION,
        "methodology_version": RELIABILITY_METHODOLOGY_VERSION,
        "evidence_count": 3,
        "has_supporting_evidence": True,
        "has_contradiction": False,
        "regression_passed": True,
        "audit_available": True,
        "founder_approved": True,
        "reason": "Verification run",
    }
    data.update(overrides)
    return CalibrationRequest(**data)
tests = []
tests.append(("VALID_PROMOTION", make_request()))
tests.append(("SKIP_REJECT", make_request(requested_status="VERIFIED")))
tests.append(("NO_EVIDENCE_REJECT", make_request(has_supporting_evidence=False)))
tests.append(("POLICY_VERSION_REJECT", make_request(policy_version="OLD_POLICY")))
tests.append(("METHODOLOGY_VERSION_REJECT", make_request(methodology_version="OLD_METHOD")))
tests.append(("AUDIT_REQUIRED_REJECT", make_request(audit_available=False)))
tests.append(("FOUNDER_REQUIRED_REJECT", make_request(founder_approved=False)))
tests.append(("CONTRADICTION_DOWNGRADE", make_request(current_status="VALIDATED", requested_status="VERIFIED", has_contradiction=True)))
tests.append(("REGRESSION_DOWNGRADE", make_request(current_status="VERIFIED", requested_status="VERIFIED", regression_passed=False)))
print("ERI-004 CALIBRATION ENGINE VERIFICATION")
print("=" * 70)
store = CalibrationStore("eri_persistence.db")
for name, request in tests:
    result = evaluate_calibration(request)
    store.apply_result_atomic(result)
    print(name)
    print("  ACCEPTED:", result.accepted)
    print("  PREVIOUS:", result.previous_status)
    print("  NEW:", result.new_status)
    print("  REASON:", result.reason)
    print("  EFFECTIVE_CONFIDENCE:", result.effective_confidence)
    print()
print("REGISTRY STATUS")
print(store.load_status("ERA:THS:score_input"))
print()
print("AUDIT HISTORY")
for row in store.load_audit("ERA:THS:score_input"):
    print(row)
