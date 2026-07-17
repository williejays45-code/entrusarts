import sys
from era.sensitivity.contribution_analyzer import ContributionAnalyzer
from era.sensitivity.contribution_models import ContributionInput
def good_input(**overrides):
    data = {
        "recommendation_id": "REC-001",
        "decision_trace_id": "DT-001",
        "evidence_id": "EV-001",
        "evidence_type": "occupancy",
        "evidence_status": "VERIFIED",
        "reliability_status": "VERIFIED",
        "calibration_status": "VALIDATED",
        "weight_id": "W-OCCUPANCY",
        "weight_version": "1.0",
        "weight_status": "VALIDATED",
        "methodology_version": "ERA_RELIABILITY_METHODOLOGY-1.0",
        "effective_confidence": "PARTIAL",
    }
    data.update(overrides)
    return ContributionInput(**data)
engine = ContributionAnalyzer()
status, analysis = engine.analyze("REC-001", [good_input()])
checks = [
    ("analysis_created", analysis is not None),
    ("status_pass", status == "PASS"),
    ("confidence_partial", analysis.overall_confidence == "PARTIAL" if analysis else False),
    ("contribution_count", len(analysis.contributions) == 1 if analysis else False),
    ("weight_id_preserved", analysis.contributions[0].weight_id == "W-OCCUPANCY" if analysis else False),
    ("weight_version_preserved", analysis.contributions[0].weight_version == "1.0" if analysis else False),
    ("contribution_level", analysis.contributions[0].contribution_level.value == "MODERATE" if analysis else False),
    ("decision_trace", analysis.decision_trace_id == "DT-001" if analysis else False),
    ("methodology", analysis.methodology_version == "ERA_RELIABILITY_METHODOLOGY-1.0" if analysis else False),
    ("audit_event_created", len(engine.audit.events) >= 1),
    ("contribution_event_present", any(e["event_type"] == "CONTRIBUTION_GENERATED" for e in engine.audit.events)),
]
passed = 0
print("ERI-003 PHASE 1 REGRESSION")
print("=" * 60)
for name, ok in checks:
    print(f"{name:<35} {'PASS' if ok else 'FAIL'}")
    if ok:
        passed += 1
print()
print("AUDIT EVENTS")
for event in engine.audit.events:
    print(event)
print()
print(f"REGRESSION CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
_ERA_OVERALL_OK = (passed == len(checks))
if not _ERA_OVERALL_OK:
    sys.exit(1)
