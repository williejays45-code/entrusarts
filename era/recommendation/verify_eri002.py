import sys
from era.recommendation.recommendation_engine import RecommendationEngine
from era.recommendation.recommendation_models import SupportingEvidence, BlockingDependency
from era.recommendation.recommendation_states import RecommendationState
from era.recommendation import recommendation_errors as errors
from era.sensitivity.contribution_models import ContributionAnalysis, utc_now
engine = RecommendationEngine()
good_evidence = [
    SupportingEvidence("EV-001", "Verified occupancy evidence exists.", "VERIFIED")
]
unsupported_evidence = [
    SupportingEvidence("EV-999", "Unknown source.", "UNSUPPORTED")
]
blocking = [
    BlockingDependency("BD-001", "Occupancy confidence remains limited.", "PARTIAL")
]
def analysis(trace_id="DT-001", confidence="PARTIAL", methodology="METH-1"):
    # Stands in for real output from era.sensitivity.ContributionAnalyzer.
    # RecommendationEngine trusts this object's fields verbatim -- it is
    # the only channel confidence can reach RecommendationEngine through.
    return ContributionAnalysis(
        recommendation_id="REC-001",
        decision_trace_id=trace_id,
        methodology_version=methodology,
        overall_confidence=confidence,
        contributions=[],
        generated_at=utc_now(),
    )
tests = []
# EV-001 Recommendation without trace
tests.append(("EV-001", errors.TRACE_REQUIRED, lambda: engine.create_recommendation(good_evidence, blocking, "", analysis(trace_id=""))[0]))
# EV-002 Recommendation exceeds confidence ceiling
tests.append(("EV-002", errors.CONFIDENCE_CEILING_VIOLATION, lambda: engine.create_recommendation(good_evidence, blocking, "DT-001", analysis(), RecommendationState.SUPPORTED)[0]))
# EV-003 Recommendation without evidence
tests.append(("EV-003", "INCOMPLETE", lambda: engine.create_recommendation([], blocking, "DT-001", analysis())[0]))
# EV-004 Hidden blocking dependency
tests.append(("EV-004", errors.BLOCKING_DEPENDENCY_REQUIRED, lambda: engine.create_recommendation(good_evidence, [], "DT-001", analysis())[0]))
# EV-005 Unsupported evidence
tests.append(("EV-005", errors.UNSUPPORTED, lambda: engine.create_recommendation(unsupported_evidence, blocking, "DT-001", analysis())[0]))
# EV-006 Recommendation modifies calibration
tests.append(("EV-006", errors.READ_ONLY_ENGINE, lambda: engine.attempt_write("calibration")[1]))
# EV-007 Recommendation modifies evidence
tests.append(("EV-007", errors.READ_ONLY_ENGINE, lambda: engine.attempt_write("evidence")[1]))
# EV-008 Recommendation without methodology version
tests.append(("EV-008", errors.DEPENDENCY_INCOMPLETE, lambda: engine.create_recommendation(good_evidence, blocking, "DT-001", analysis(methodology=""))[0]))
# EV-009 Recommendation without decision trace
tests.append(("EV-009", errors.TRACE_REQUIRED, lambda: engine.create_recommendation(good_evidence, blocking, "", analysis(trace_id=""))[0]))
# EV-010 No sensitivity analysis supplied (no confidence-authority input at all)
tests.append(("EV-010", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.create_recommendation(good_evidence, blocking, "DT-001", None)[0]))
# EV-011 Sensitivity analysis trace doesn't match the decision trace being recommended on (spoof/mismatch attempt)
tests.append(("EV-011", errors.TRACE_MISMATCH, lambda: engine.create_recommendation(good_evidence, blocking, "DT-001", analysis(trace_id="DT-999"))[0]))
print("ERI-002 RECOMMENDATION REASONER VERIFICATION")
print("=" * 70)
passed = 0
for test_id, expected, fn in tests:
    actual = fn()
    ok = actual == expected
    if ok:
        passed += 1
    print(test_id)
    print("  EXPECTED:", expected)
    print("  ACTUAL:  ", actual)
    print("  PASS:    ", ok)
    print()
# Happy path
status, recommendation = engine.create_recommendation(
    good_evidence,
    blocking,
    "DT-001",
    analysis(),
)
print("HAPPY PATH")
print("  STATUS:", status)
print("  RECOMMENDATION:", recommendation)
print()
print("AUDIT EVENTS:", len(engine.audit.events))
for event in engine.audit.events[-5:]:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/{len(tests)}")
print("OVERALL:", "PASS" if passed == len(tests) and recommendation is not None else "FAIL")
_ERA_OVERALL_OK = (passed == len(tests) and recommendation is not None)
if not _ERA_OVERALL_OK:
    sys.exit(1)
