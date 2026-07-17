import sys
from era.recommendation.recommendation_engine import RecommendationEngine
from era.recommendation.recommendation_models import SupportingEvidence, BlockingDependency
from era.recommendation.recommendation_states import RecommendationState
from era.sensitivity.contribution_models import ContributionAnalysis, utc_now
engine = RecommendationEngine()
good_evidence = [
    SupportingEvidence("EV-001", "Verified occupancy evidence exists.", "VERIFIED")
]
blocking = [
    BlockingDependency("BD-001", "Occupancy confidence remains limited.", "PARTIAL")
]
sensitivity_analysis = ContributionAnalysis(
    recommendation_id="REC-001",
    decision_trace_id="DT-001",
    methodology_version="METH-1",
    overall_confidence="PARTIAL",
    contributions=[],
    generated_at=utc_now(),
)
print("ERI-002 REGRESSION + AUDIT VERIFICATION")
print("=" * 70)
status, recommendation = engine.create_recommendation(
    good_evidence,
    blocking,
    "DT-001",
    sensitivity_analysis,
    RecommendationState.PARTIAL,
)
checks = {
    "recommendation_created": recommendation is not None,
    "state_is_partial": status == "PARTIAL",
    "decision_trace_linked": recommendation.decision_trace_id == "DT-001" if recommendation else False,
    "confidence_preserved": recommendation.confidence == "PARTIAL" if recommendation else False,
    "methodology_present": recommendation.methodology_version == "METH-1" if recommendation else False,
    "audit_events_present": len(engine.audit.events) >= 2,
    "trace_link_event_present": any(e["event_type"] == "RECOMMENDATION_TRACE_LINKED" for e in engine.audit.events),
    "created_event_present": any(e["event_type"] == "RECOMMENDATION_CREATED" for e in engine.audit.events),
}
passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print("AUDIT EVENTS")
for event in engine.audit.events:
    print(event)
print()
print("REGRESSION CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
_ERA_OVERALL_OK = (passed == len(checks))
if not _ERA_OVERALL_OK:
    sys.exit(1)
