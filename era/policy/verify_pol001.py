import sys
from dataclasses import FrozenInstanceError
from era.policy.policy_engine import PolicyEngine
from era.policy.policy_models import PolicyRuleSet, PolicyDecisionInput
from era.policy.policy_enums import PolicyVerdict, PolicyReason
from era.policy import policy_errors as errors
def policy(**overrides):
    data = {
        "policy_id": "POL-ERA-001",
        "policy_version": "1.0",
        "allowed_decisions": [
            "ACCEPT",
            "READY_FOR_EXPORT",
            "PENDING_MORE_EVIDENCE",
            "CONFLICT_RESOLUTION_REQUIRED",
        ],
        "export_allowed": True,
        "require_manual_review_on_conflict": True,
    }
    data.update(overrides)
    return PolicyRuleSet(**data)
def decision(**overrides):
    data = {
        "property_id": "ERA-PR-2026-000001",
        "decision": "ACCEPT",
        "has_conflicts": False,
        "export_requested": False,
        "policy_violation": False,
        "supporting_evidence_ids": ["EV-001", "EV-002"],
    }
    data.update(overrides)
    return PolicyDecisionInput(**data)
engine = PolicyEngine()
tests = [
    ("EV-001", errors.POLICY_REQUIRED, lambda: engine.evaluate(None, decision())[0]),
    ("EV-002", errors.POLICY_VERSION_REQUIRED, lambda: engine.evaluate(policy(policy_version=""), decision())[0]),
    ("EV-003", errors.DECISION_REQUIRED, lambda: engine.evaluate(policy(), decision(property_id=""))[0]),
    ("EV-004", PolicyVerdict.AUTHORIZED, lambda: engine.evaluate(policy(), decision())[1].verdict),
    ("EV-005", PolicyVerdict.DENIED, lambda: engine.evaluate(policy(allowed_decisions=["REJECT"]), decision(decision="ACCEPT"))[1].verdict),
    ("EV-006", PolicyVerdict.REQUIRES_REVIEW, lambda: engine.evaluate(policy(), decision(has_conflicts=True))[1].verdict),
    ("EV-007", PolicyVerdict.EXPORT_APPROVED, lambda: engine.evaluate(policy(), decision(decision="READY_FOR_EXPORT", export_requested=True))[1].verdict),
    ("EV-008", PolicyVerdict.EXPORT_DENIED, lambda: engine.evaluate(policy(export_allowed=False), decision(decision="READY_FOR_EXPORT", export_requested=True))[1].verdict),
    ("EV-009", PolicyVerdict.POLICY_VIOLATION, lambda: engine.evaluate(policy(), decision(policy_violation=True))[1].verdict),
    ("EV-010", errors.READ_ONLY_POLICY, lambda: engine.attempt_write()[1]),
    ("EV-011", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("POL-001 POLICY ENGINE VERIFICATION")
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
det_engine_a = PolicyEngine()
status_a, result_a = det_engine_a.evaluate(policy(), decision())
det_engine_b = PolicyEngine()
status_b, result_b = det_engine_b.evaluate(policy(), decision())
deterministic = (
    status_a == status_b
    and result_a.policy_id == result_b.policy_id
    and result_a.policy_version == result_b.policy_version
    and result_a.property_id == result_b.property_id
    and result_a.decision == result_b.decision
    and result_a.verdict == result_b.verdict
    and result_a.reason == result_b.reason
    and result_a.supporting_evidence_ids == result_b.supporting_evidence_ids
)
print("EV-012")
print("  EXPECTED:", errors.DETERMINISTIC_POLICY)
print("  ACTUAL:  ", errors.DETERMINISTIC_POLICY if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
audit_ok = (
    len(det_engine_a.audit.events) == 2
    and det_engine_a.audit.events[0]["event_type"] == "POLICY_RULE_EVALUATED"
    and det_engine_a.audit.events[1]["event_type"] == "POLICY_RESULT_RECORDED"
)
print("EV-013")
print("  EXPECTED:", errors.AUDIT_CHAIN_VERIFIED)
print("  ACTUAL:  ", errors.AUDIT_CHAIN_VERIFIED if audit_ok else "AUDIT_FAIL")
print("  PASS:    ", audit_ok)
print()
if audit_ok:
    passed += 1
immutable_ok = False
try:
    result_a.verdict = PolicyVerdict.DENIED
except FrozenInstanceError:
    immutable_ok = True
happy_engine = PolicyEngine()
happy_status, happy = happy_engine.evaluate(policy(), decision())
happy_ok = (
    happy_status == errors.PASS
    and happy.verdict == PolicyVerdict.AUTHORIZED
    and happy.reason == PolicyReason.DECISION_ALLOWED
    and immutable_ok
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  VERDICT:", happy.verdict.value if happy else None)
print("  REASON:", happy.reason.value if happy else None)
print("  IMMUTABLE:", immutable_ok)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(happy_engine.audit.events))
for event in happy_engine.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/13")
print("OVERALL:", "PASS" if passed == 13 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 13 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
