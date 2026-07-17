import sys
from era.improvement.improvement_analyzer import ImprovementAnalyzer
from era.improvement.improvement_models import ImprovementInput
from era.improvement import improvement_errors as errors
def good_input(**overrides):
    data = {
        "dependency_id": "DEP-001",
        "dependency_status": "UNRESOLVED",
        "dependency_reference": "DEPREF-001",
        "methodology_id": "RML-RES-INV",
        "methodology_reference": "METH-REQ-001",
        "evidence_id": "EV-001",
        "trace_id": "TR-001",
        "impact_level": "HIGH",
        "blocking_severity": "HIGH",
        "ease_of_resolution": "EASY",
        "reason": "Professional inspection would reduce uncertainty.",
    }
    data.update(overrides)
    return ImprovementInput(**data)
engine = ImprovementAnalyzer()
tests = [
    ("EV-001", errors.UNKNOWN_DEPENDENCY_REFERENCE, lambda: engine.analyze("TR-001", [good_input(dependency_reference="UNKNOWN-DEP")])[0]),
    ("EV-002", errors.UNKNOWN_METHODOLOGY_REFERENCE, lambda: engine.analyze("TR-001", [good_input(methodology_reference="UNKNOWN-METH")])[0]),
    ("EV-003", errors.READ_ONLY_ENGINE, lambda: engine.attempt_write("recommendation")[1]),
    ("EV-004", errors.READ_ONLY_ENGINE, lambda: engine.attempt_write("evidence")[1]),
    ("EV-005", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.attempt_write("confidence")[1]),
    ("EV-006", errors.TRACE_REQUIRED, lambda: engine.analyze("", [good_input()])[0]),
    ("EV-007", errors.METHODOLOGY_REQUIRED, lambda: engine.analyze("TR-001", [good_input(methodology_id="")])[0]),
    ("EV-008", errors.WEIGHT_DISCLOSURE_VIOLATION, lambda: engine.attempt_weight_disclosure()[1]),
    ("EV-010", errors.UNKNOWN_EVIDENCE_REFERENCE, lambda: engine.analyze("TR-001", [good_input(evidence_id="UNKNOWN-EV")])[0]),
    ("EV-011", errors.IMPROVEMENT_VALIDATED, lambda: engine.analyze("TR-001", [good_input()])[1].reason),
]
print("ERI-003 PHASE 3 IMPROVEMENT ANALYZER VERIFICATION")
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
status1, analysis1 = engine.analyze("TR-DET", [good_input()])
status2, analysis2 = engine.analyze("TR-DET", [good_input()])
deterministic = (
    status1 == status2
    and analysis1 is not None
    and analysis2 is not None
    and len(analysis1.improvements) == len(analysis2.improvements)
    and analysis1.improvements[0].impact_level == analysis2.improvements[0].impact_level
    and analysis1.improvements[0].priority_rank == analysis2.improvements[0].priority_rank
    and analysis1.improvements[0].reason == analysis2.improvements[0].reason
)
print("EV-009")
print("  EXPECTED:", errors.DETERMINISTIC_IMPROVEMENT)
print("  ACTUAL:  ", errors.DETERMINISTIC_IMPROVEMENT if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
many = [
    good_input(
        dependency_id=f"DEP-{i:03d}",
        dependency_reference=f"DEPREF-{i:03d}",
        evidence_id=f"EV-{i:03d}",
        reason=f"Improvement {i}",
    )
    for i in range(1, 8)
]
trunc_status, trunc_analysis = engine.analyze("TR-MANY", many)
truncation_ok = (
    trunc_status == errors.PASS
    and trunc_analysis is not None
    and trunc_analysis.total_generated == 7
    and trunc_analysis.displayed_count == 5
    and len(trunc_analysis.improvements) == 5
)
print("EV-012")
print("  EXPECTED:", errors.TRUNCATION_RECORDED)
print("  ACTUAL:  ", errors.TRUNCATION_RECORDED if truncation_ok else "TRUNCATION_FAILED")
print("  PASS:    ", truncation_ok)
print()
if truncation_ok:
    passed += 1
empty_status, empty_analysis = engine.analyze("TR-EMPTY", [])
print("EMPTY STATE")
print("  STATUS:", empty_status)
print("  REASON:", empty_analysis.reason if empty_analysis else None)
print("  COUNT:", len(empty_analysis.improvements) if empty_analysis else None)
print("  TOTAL GENERATED:", empty_analysis.total_generated if empty_analysis else None)
print("  DISPLAYED COUNT:", empty_analysis.displayed_count if empty_analysis else None)
print()
resolved_status, resolved_analysis = engine.analyze("TR-RESOLVED", [
    good_input(dependency_status="RESOLVED")
])
print("RESOLVED DEPENDENCY STATE")
print("  STATUS:", resolved_status)
print("  REASON:", resolved_analysis.reason if resolved_analysis else None)
print("  COUNT:", len(resolved_analysis.improvements) if resolved_analysis else None)
print()
happy_status, happy = engine.analyze("TR-001", [good_input()])
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  ANALYSIS STATUS:", happy.status.value if happy else None)
print("  IMPROVEMENTS:", len(happy.improvements) if happy else None)
print("  TOTAL GENERATED:", happy.total_generated if happy else None)
print("  DISPLAYED COUNT:", happy.displayed_count if happy else None)
print("  TOP IMPACT:", happy.improvements[0].impact_level.value if happy else None)
print("  PRIORITY:", happy.improvements[0].priority_rank if happy else None)
print()
print("AUDIT EVENTS:", len(engine.audit.events))
for event in engine.audit.events[-10:]:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/12")
print("OVERALL:", "PASS" if passed == 12 and happy_status == errors.PASS else "FAIL")
_ERA_OVERALL_OK = (passed == 12 and happy_status == errors.PASS)
if not _ERA_OVERALL_OK:
    sys.exit(1)
