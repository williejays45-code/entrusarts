import sys
from era.trace.dependency_trace_engine import DependencyTraceEngine
from era.trace.trace_models import TraceAssemblyInput
from era.trace import trace_errors as errors
def good_input(**overrides):
    data = {
        "trace_id": "TR-001",
        "evidence_id": "EV-001",
        "evidence_reliability": "VERIFIED",
        "weight_id": "W-OCCUPANCY",
        "weight_version": "1.0",
        "calibration_version": "CAL-1.0",
        "methodology_id": "RML-RES-INV",
        "methodology_version": "1.0",
        "contribution_id": "CONTRIB-001",
    }
    data.update(overrides)
    return TraceAssemblyInput(**data)
engine = DependencyTraceEngine()
tests = [
    ("EV-001", errors.TRACE_REQUIRED, lambda: engine.finalize("", "REC-001", "PARTIAL", "PARTIAL")[0]),
    ("EV-002", errors.TRACE_INCOMPLETE, lambda: engine.assemble(good_input(weight_id=""))[0]),
    ("EV-003", errors.TRACE_INCOMPLETE, lambda: engine.assemble(good_input(methodology_version=""))[0]),
    ("EV-004", errors.TRACE_IMMUTABLE, lambda: engine.modify_trace(None)[1]),
    ("EV-005", errors.READ_ONLY_ENGINE, lambda: engine.attempt_write("evidence")[1]),
    ("EV-006", errors.READ_ONLY_ENGINE, lambda: engine.attempt_write("calibration")[1]),
    ("EV-007", errors.UNKNOWN_EVIDENCE_REFERENCE, lambda: engine.assemble(good_input(evidence_id="UNKNOWN-EV"))[0]),
    ("EV-008", errors.UNKNOWN_WEIGHT_REFERENCE, lambda: engine.assemble(good_input(weight_id="UNKNOWN-W"))[0]),
    ("EV-010", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.attempt_confidence_override()[1]),
]
print("ERI-003 PHASE 2 DEPENDENCY TRACE VERIFICATION")
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
status_a, assembled_a = engine.assemble(good_input(trace_id="TR-DET"))
status_f, trace_1 = engine.finalize("TR-DET", "REC-001", "PARTIAL", "PARTIAL")
engine2 = DependencyTraceEngine()
status_b, assembled_b = engine2.assemble(good_input(trace_id="TR-DET"))
status_g, trace_2 = engine2.finalize("TR-DET", "REC-001", "PARTIAL", "PARTIAL")
deterministic = (
    trace_1 is not None
    and trace_2 is not None
    and trace_1.trace_id == trace_2.trace_id
    and trace_1.recommendation_id == trace_2.recommendation_id
    and trace_1.weight_version == trace_2.weight_version
    and trace_1.methodology_version == trace_2.methodology_version
    and trace_1.calibration_version == trace_2.calibration_version
)
print("EV-009")
print("  EXPECTED:", errors.DETERMINISTIC_TRACE)
print("  ACTUAL:  ", errors.DETERMINISTIC_TRACE if deterministic else "DETERMINISM_FAILED")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
print("HAPPY PATH")
print("  ASSEMBLY:", status_a)
print("  FINALIZE:", status_f)
print("  TRACE ID:", trace_1.trace_id if trace_1 else None)
print("  RECOMMENDATION:", trace_1.recommendation_id if trace_1 else None)
print("  FINALIZED:", trace_1.finalized if trace_1 else None)
print()
print("AUDIT EVENTS:", len(engine.audit.events))
for event in engine.audit.events[-6:]:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/10")
print("OVERALL:", "PASS" if passed == 10 and status_f == errors.PASS else "FAIL")
_ERA_OVERALL_OK = (passed == 10 and status_f == errors.PASS)
if not _ERA_OVERALL_OK:
    sys.exit(1)
