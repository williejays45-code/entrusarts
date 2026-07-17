import sys
from era.sensitivity.contribution_analyzer import ContributionAnalyzer
from era.sensitivity.contribution_models import ContributionInput
engine = ContributionAnalyzer()
good = ContributionInput(
    recommendation_id="REC-001",
    decision_trace_id="DT-001",
    evidence_id="EV-001",
    evidence_type="occupancy",
    evidence_status="VERIFIED",
    reliability_status="VERIFIED",
    calibration_status="VALIDATED",
    weight_id="W-OCCUPANCY",
    weight_version="1.0",
    weight_status="VALIDATED",
    methodology_version="ERA_RELIABILITY_METHODOLOGY-1.0",
    effective_confidence="PARTIAL",
)
engine.analyze("REC-001", [good])
events = engine.audit.events
created = sum(e["event_type"] == "CONTRIBUTION_GENERATED" for e in events)
blocked = sum(e["event_type"] == "SENSITIVITY_BLOCKED" for e in events)
checks = [
    ("created_event_exists", created == 1),
    ("blocked_events_zero", blocked == 0),
    ("audit_count_matches", len(events) == created + blocked),
    ("no_unknown_events",
     all(e["event_type"] in {
         "CONTRIBUTION_GENERATED",
         "SENSITIVITY_BLOCKED"
     } for e in events)),
]
passed = 0
print("ERI-003 AUDIT RECONCILIATION")
print("=" * 60)
for name, ok in checks:
    print(f"{name:<35} {'PASS' if ok else 'FAIL'}")
    if ok:
        passed += 1
print()
print("AUDIT EVENTS:", len(events))
print("CREATED:", created)
print("BLOCKED:", blocked)
print()
print(f"AUDIT CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
_ERA_OVERALL_OK = (passed == len(checks))
if not _ERA_OVERALL_OK:
    sys.exit(1)
