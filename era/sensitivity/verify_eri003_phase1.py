import sys
from era.sensitivity.contribution_analyzer import ContributionAnalyzer
from era.sensitivity.contribution_models import ContributionInput
from era.sensitivity import sensitivity_errors as errors
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
analyzer = ContributionAnalyzer()
tests = [
    ("EV-001", errors.TRACE_REQUIRED, lambda: analyzer.analyze("REC-001", [good_input(decision_trace_id="")])[0]),
    ("EV-002", errors.METHODOLOGY_REQUIRED, lambda: analyzer.analyze("REC-001", [good_input(methodology_version="")])[0]),
    ("EV-003", errors.UNSUPPORTED, lambda: analyzer.analyze("REC-001", [good_input(evidence_status="UNSUPPORTED")])[0]),
    ("EV-004", errors.PLACEHOLDER_VISIBILITY_VIOLATION, lambda: analyzer.analyze("REC-001", [good_input(weight_status="PLACEHOLDER", calibration_status="VALIDATED")])[0]),
    ("EV-005", errors.READ_ONLY_ENGINE, lambda: analyzer.attempt_write("weight_registry")[1]),
    ("EV-006", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: analyzer.attempt_confidence_calculation()[1]),
    ("EV-007", errors.DEPENDENCY_INCOMPLETE, lambda: analyzer.analyze("REC-001", [good_input(calibration_status="")])[0]),
    ("EV-008", errors.TRACE_INCOMPLETE, lambda: analyzer.analyze("REC-001", [good_input(weight_id="")])[0]),
]
print("ERI-003.1 CONTRIBUTION ANALYZER VERIFICATION")
print("=" * 70)
passed = 0
for ev_id, expected, fn in tests:
    actual = fn()
    ok = actual == expected
    if ok:
        passed += 1
    print(ev_id)
    print("  EXPECTED:", expected)
    print("  ACTUAL:  ", actual)
    print("  PASS:    ", ok)
    print()
status1, analysis1 = analyzer.analyze("REC-001", [good_input()])
status2, analysis2 = analyzer.analyze("REC-001", [good_input()])
deterministic = (
    status1 == status2
    and analysis1 is not None
    and analysis2 is not None
    and analysis1.contributions[0].contribution_level == analysis2.contributions[0].contribution_level
    and analysis1.contributions[0].weight_id == analysis2.contributions[0].weight_id
    and analysis1.contributions[0].weight_version == analysis2.contributions[0].weight_version
)
print("EV-009")
print("  EXPECTED: deterministic outputs match")
print("  ACTUAL:  ", "match" if deterministic else errors.DETERMINISM_VIOLATION)
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
print("HAPPY PATH")
print("  STATUS:", status1)
print("  CONFIDENCE:", analysis1.overall_confidence if analysis1 else None)
print("  CONTRIBUTION:", analysis1.contributions[0].contribution_level.value if analysis1 else None)
print("  INTERNAL WEIGHT ID:", analysis1.contributions[0].weight_id if analysis1 else None)
print("  INTERNAL WEIGHT VERSION:", analysis1.contributions[0].weight_version if analysis1 else None)
print()
print("AUDIT EVENTS:", len(analyzer.audit.events))
for event in analyzer.audit.events[-5:]:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/9")
print("OVERALL:", "PASS" if passed == 9 and status1 == errors.PASS else "FAIL")
_ERA_OVERALL_OK = (passed == 9 and status1 == errors.PASS)
if not _ERA_OVERALL_OK:
    sys.exit(1)
