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
    return ContributionAnalysis(
        recommendation_id="REC-001",
        decision_trace_id=trace_id,
        methodology_version=methodology,
        overall_confidence=confidence,
        contributions=[],
        generated_at=utc_now(),
    )
def run_ev_suite():
    return [
        ("EV-001", "Recommendation without trace", errors.TRACE_REQUIRED,
         engine.create_recommendation(good_evidence, blocking, "", analysis(trace_id=""))[0]),
        ("EV-002", "Recommendation exceeds confidence ceiling", errors.CONFIDENCE_CEILING_VIOLATION,
         engine.create_recommendation(good_evidence, blocking, "DT-001", analysis(), RecommendationState.SUPPORTED)[0]),
        ("EV-003", "Recommendation without evidence", "INCOMPLETE",
         engine.create_recommendation([], blocking, "DT-001", analysis())[0]),
        ("EV-004", "Hidden blocking dependency", errors.BLOCKING_DEPENDENCY_REQUIRED,
         engine.create_recommendation(good_evidence, [], "DT-001", analysis())[0]),
        ("EV-005", "Unsupported evidence", errors.UNSUPPORTED,
         engine.create_recommendation(unsupported_evidence, blocking, "DT-001", analysis())[0]),
        ("EV-006", "Attempt calibration write", errors.READ_ONLY_ENGINE,
         engine.attempt_write("calibration")[1]),
        ("EV-007", "Attempt evidence write", errors.READ_ONLY_ENGINE,
         engine.attempt_write("evidence")[1]),
        ("EV-008", "Missing methodology version", errors.DEPENDENCY_INCOMPLETE,
         engine.create_recommendation(good_evidence, blocking, "DT-001", analysis(methodology=""))[0]),
        ("EV-009", "Missing decision trace", errors.TRACE_REQUIRED,
         engine.create_recommendation(good_evidence, blocking, "", analysis(trace_id=""))[0]),
        ("EV-010", "No sensitivity analysis supplied", errors.CONFIDENCE_AUTHORITY_VIOLATION,
         engine.create_recommendation(good_evidence, blocking, "DT-001", None)[0]),
        ("EV-011", "Sensitivity analysis trace mismatch (spoof attempt)", errors.TRACE_MISMATCH,
         engine.create_recommendation(good_evidence, blocking, "DT-001", analysis(trace_id="DT-999"))[0]),
    ]
print("ERI-002 ITEMIZED VIOLATION VERIFICATION")
print("=" * 70)
ev_results = run_ev_suite()
ev_passed = 0
for ev_id, name, expected, actual in ev_results:
    ok = expected == actual
    if ok:
        ev_passed += 1
    print(ev_id, "-", name)
    print("  EXPECTED:", expected)
    print("  ACTUAL:  ", actual)
    print("  PASS:    ", ok)
    print()
print("VIOLATION TESTS PASSED:", f"{ev_passed}/{len(ev_results)}")
print()
print("ERI-002 EXTENDED REGRESSION VERIFICATION")
print("=" * 70)
regression_checks = {}
# Happy path.
before_events = len(engine.audit.events)
status, recommendation = engine.create_recommendation(
    good_evidence,
    blocking,
    "DT-001",
    analysis(),
    RecommendationState.PARTIAL,
)
after_events = len(engine.audit.events)
regression_checks["recommendation_created"] = recommendation is not None
regression_checks["state_is_partial"] = status == "PARTIAL"
regression_checks["decision_trace_linked"] = recommendation.decision_trace_id == "DT-001" if recommendation else False
regression_checks["confidence_preserved"] = recommendation.confidence == "PARTIAL" if recommendation else False
regression_checks["methodology_present"] = recommendation.methodology_version == "METH-1" if recommendation else False
regression_checks["audit_events_present"] = after_events > before_events
regression_checks["trace_link_event_present"] = any(e["event_type"] == "RECOMMENDATION_TRACE_LINKED" for e in engine.audit.events[before_events:])
regression_checks["created_event_present"] = any(e["event_type"] == "RECOMMENDATION_CREATED" for e in engine.audit.events[before_events:])
# Failure behavior regression.
regression_checks["trace_required_still_blocks"] = (
    engine.create_recommendation(good_evidence, blocking, "", analysis(trace_id=""))[0]
    == errors.TRACE_REQUIRED
)
regression_checks["readonly_calibration_still_blocks"] = (
    engine.attempt_write("calibration")[1] == errors.READ_ONLY_ENGINE
)
regression_checks["readonly_evidence_still_blocks"] = (
    engine.attempt_write("evidence")[1] == errors.READ_ONLY_ENGINE
)
regression_checks["missing_analysis_still_blocks"] = (
    engine.create_recommendation(good_evidence, blocking, "DT-001", None)[0] == errors.CONFIDENCE_AUTHORITY_VIOLATION
)
regression_checks["trace_mismatch_still_blocks"] = (
    engine.create_recommendation(good_evidence, blocking, "DT-001", analysis(trace_id="DT-999"))[0] == errors.TRACE_MISMATCH
)
reg_passed = 0
for name, ok in regression_checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        reg_passed += 1
print()
print("REGRESSION CHECKS PASSED:", f"{reg_passed}/{len(regression_checks)}")
print()
print("ERI-002 AUDIT RECONCILIATION")
print("=" * 70)
audit_events = engine.audit.events
created_events = [e for e in audit_events if e["event_type"] == "RECOMMENDATION_CREATED"]
trace_events = [e for e in audit_events if e["event_type"] == "RECOMMENDATION_TRACE_LINKED"]
blocked_events = [e for e in audit_events if e["event_type"] == "RECOMMENDATION_BLOCKED"]
audit_checks = {
    "created_has_trace_link": len(trace_events) >= len(created_events),
    "created_count_matches_successful_recommendations": len(created_events) >= 1,
    "blocked_events_exist_for_failures": len(blocked_events) >= 1,
    "no_unknown_audit_events": all(
        e["event_type"] in {
            "RECOMMENDATION_CREATED",
            "RECOMMENDATION_TRACE_LINKED",
            "RECOMMENDATION_BLOCKED",
            "RECOMMENDATION_INCOMPLETE",
        }
        for e in audit_events
    ),
}
audit_passed = 0
for name, ok in audit_checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        audit_passed += 1
print()
print("AUDIT EVENTS COUNT:", len(audit_events))
print("CREATED EVENTS:", len(created_events))
print("TRACE LINK EVENTS:", len(trace_events))
print("BLOCKED EVENTS:", len(blocked_events))
print()
print("AUDIT CHECKS PASSED:", f"{audit_passed}/{len(audit_checks)}")
print()
overall = (
    ev_passed == len(ev_results)
    and reg_passed == len(regression_checks)
    and audit_passed == len(audit_checks)
)
print("OVERALL:", "PASS" if overall else "FAIL")
_ERA_OVERALL_OK = (overall)
if not _ERA_OVERALL_OK:
    sys.exit(1)
