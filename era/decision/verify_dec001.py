import sys
from dataclasses import FrozenInstanceError
from era.decision.decision_engine import DecisionEngine
from era.decision.decision_models import DecisionInput
from era.decision.decision_enums import DecisionState, DecisionReason
from era.decision import decision_errors as errors
def decision_input(**overrides):
    data = {
        "property_id": "ERA-PR-2026-000001",
        "evidence_count": 5,
        "required_fields_present": True,
        "has_conflicts": False,
        "has_policy_violation": False,
        "manual_review_flag": False,
        "single_source_only": False,
        "export_ready": False,
        "supporting_evidence_ids": ["EV-001", "EV-002"],
    }
    data.update(overrides)
    return DecisionInput(**data)
engine = DecisionEngine()
tests = [
    ("EV-001", errors.PROPERTY_REQUIRED, lambda: engine.decide(decision_input(property_id=""))[0]),
    ("EV-002", errors.EVIDENCE_REQUIRED, lambda: engine.decide(decision_input(evidence_count=0, supporting_evidence_ids=[]))[0]),
    ("EV-003", DecisionState.ACCEPT, lambda: engine.decide(decision_input())[1].decision),
    ("EV-004", DecisionState.REJECT, lambda: engine.decide(decision_input(has_policy_violation=True))[1].decision),
    ("EV-005", DecisionState.MANUAL_REVIEW, lambda: engine.decide(decision_input(manual_review_flag=True))[1].decision),
    ("EV-006", DecisionState.PENDING_MORE_EVIDENCE, lambda: engine.decide(decision_input(single_source_only=True))[1].decision),
    ("EV-007", DecisionState.CONFLICT_RESOLUTION_REQUIRED, lambda: engine.decide(decision_input(has_conflicts=True))[1].decision),
    ("EV-008", DecisionState.READY_FOR_EXPORT, lambda: engine.decide(decision_input(export_ready=True))[1].decision),
    ("EV-009", errors.READ_ONLY_DECISION, lambda: engine.attempt_write()[1]),
    ("EV-010", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("DEC-001 DECISION ENGINE VERIFICATION")
print("=" * 70)
passed = 0
for ev_id, expected, fn in tests:
    actual = fn()
    ok = actual == expected
    if ok:
        passed += 1
    print(ev_id)
    print("  EXPECTED:", expected.value if hasattr(expected, "value") else expected)
    print("  ACTUAL:  ", actual.value if hasattr(actual, "value") else actual)
    print("  PASS:    ", ok)
    print()
det_engine_a = DecisionEngine()
status_a, record_a = det_engine_a.decide(decision_input())
det_engine_b = DecisionEngine()
status_b, record_b = det_engine_b.decide(decision_input())
deterministic = (
    status_a == status_b
    and record_a.decision_id == record_b.decision_id
    and record_a.property_id == record_b.property_id
    and record_a.decision == record_b.decision
    and record_a.reason == record_b.reason
    and record_a.requires_manual_review == record_b.requires_manual_review
    and record_a.supporting_evidence_ids == record_b.supporting_evidence_ids
)
print("EV-011")
print("  EXPECTED:", errors.DETERMINISTIC_DECISION)
print("  ACTUAL:  ", errors.DETERMINISTIC_DECISION if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
audit_ok = (
    len(det_engine_a.audit.events) == 2
    and det_engine_a.audit.events[0]["event_type"] == "DECISION_RULE_EVALUATED"
    and det_engine_a.audit.events[1]["event_type"] == "DECISION_RECORDED"
)
print("EV-012")
print("  EXPECTED:", errors.AUDIT_CHAIN_VERIFIED)
print("  ACTUAL:  ", errors.AUDIT_CHAIN_VERIFIED if audit_ok else "AUDIT_FAIL")
print("  PASS:    ", audit_ok)
print()
if audit_ok:
    passed += 1
immutable_ok = False
try:
    record_a.decision = DecisionState.REJECT
except FrozenInstanceError:
    immutable_ok = True
happy_engine = DecisionEngine()
happy_status, happy = happy_engine.decide(decision_input())
happy_ok = (
    happy_status == errors.PASS
    and happy.decision == DecisionState.ACCEPT
    and happy.reason == DecisionReason.NO_CONFLICTS_SUFFICIENT_EVIDENCE
    and not happy.requires_manual_review
    and immutable_ok
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  DECISION:", happy.decision.value if happy else None)
print("  REASON:", happy.reason.value if happy else None)
print("  MANUAL REVIEW:", happy.requires_manual_review if happy else None)
print("  IMMUTABLE:", immutable_ok)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(happy_engine.audit.events))
for event in happy_engine.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/12")
print("OVERALL:", "PASS" if passed == 12 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 12 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
