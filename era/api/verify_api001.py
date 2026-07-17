import sys
from dataclasses import FrozenInstanceError
from era.api.api_engine import EraApiEngine
from era.api import api_errors as errors
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import MockTokenStore
PROPERTY_ID = "ERA-PR-2026-000001"
FOUNDER_TOKEN = "founder-token"
def store():
    return {
        "properties": {
            PROPERTY_ID: {
                "property_id": PROPERTY_ID,
                "address": "5926 Sandhurst Ln Unit 224",
                "county": "Dallas",
            }
        },
        "evidence": {
            PROPERTY_ID: [
                {"evidence_id": "EV-001", "field": "address"},
                {"evidence_id": "EV-002", "field": "county"},
            ]
        },
        "decisions": {
            PROPERTY_ID: {
                "decision": "ACCEPT",
                "reason": "NO_CONFLICTS_SUFFICIENT_EVIDENCE",
            }
        },
        "policies": {
            PROPERTY_ID: {
                "verdict": "AUTHORIZED",
                "reason": "DECISION_ALLOWED",
            }
        },
        "exports": {
            PROPERTY_ID: {
                "export_id": "EXP-ERA-PR-2026-000001-DASHBOARD",
                "status": "EXPORTED",
            }
        },
        "audits": {
            PROPERTY_ID: [
                "PROPERTY_CREATED",
                "EVIDENCE_ADDED",
                "DECISION_RECORDED",
                "POLICY_RESULT_RECORDED",
                "EXPORT_COMPLETED",
            ]
        },
    }
def new_engine():
    # AUTH-WIRE-001: every EraApiEngine below is built with a real
    # AuthEngine, same as the container wires it. A founder token is
    # used for the non-auth-focused checks in this file (not-found,
    # property-required, determinism, immutability, read-only,
    # confidence-authority) so those checks exercise the same behavior
    # they always did, just past the auth gate. Auth-specific behavior
    # (missing/invalid/expired token, per-role permission checks) is
    # covered exhaustively in era/verify_auth_wire001.py.
    return EraApiEngine(store(), auth=AuthEngine(token_store=MockTokenStore()))
engine = new_engine()
tests = [
    ("EV-001", errors.PASS, lambda: engine.health()[0]),
    ("EV-002", errors.PROPERTY_REQUIRED, lambda: engine.get_property(FOUNDER_TOKEN, "")[0]),
    ("EV-003", errors.API_NOT_FOUND, lambda: engine.get_property(FOUNDER_TOKEN, "UNKNOWN")[0]),
    ("EV-004", errors.PASS, lambda: engine.get_property(FOUNDER_TOKEN, PROPERTY_ID)[0]),
    ("EV-005", errors.PASS, lambda: engine.get_evidence(FOUNDER_TOKEN, PROPERTY_ID)[0]),
    ("EV-006", errors.PASS, lambda: engine.get_decision(FOUNDER_TOKEN, PROPERTY_ID)[0]),
    ("EV-007", errors.PASS, lambda: engine.get_policy(FOUNDER_TOKEN, PROPERTY_ID)[0]),
    ("EV-008", errors.PASS, lambda: engine.get_export(FOUNDER_TOKEN, PROPERTY_ID)[0]),
    ("EV-009", errors.PASS, lambda: engine.get_audit(FOUNDER_TOKEN, PROPERTY_ID)[0]),
    ("EV-010", errors.READ_ONLY_API, lambda: engine.attempt_write()[1]),
    ("EV-011", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
    ("EV-014", errors.AUTH_ENGINE_REQUIRED, lambda: EraApiEngine(store()).get_property(FOUNDER_TOKEN, PROPERTY_ID)[0]),
]
print("API-001 ERA API ENGINE VERIFICATION (post AUTH-WIRE-001)")
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
api_a = new_engine()
status_a, response_a = api_a.get_property(FOUNDER_TOKEN, PROPERTY_ID)
api_b = new_engine()
status_b, response_b = api_b.get_property(FOUNDER_TOKEN, PROPERTY_ID)
deterministic = (
    status_a == status_b
    and response_a.endpoint == response_b.endpoint
    and response_a.property_id == response_b.property_id
    and response_a.data == response_b.data
)
print("EV-012")
print("  EXPECTED:", errors.DETERMINISTIC_RESPONSE)
print("  ACTUAL:  ", errors.DETERMINISTIC_RESPONSE if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
# Auth now publishes its own AUTHENTICATED/AUTHORIZED events on
# api_a.auth.audit as well as api_a.audit's own API_REQUEST_RECORDED --
# check the API-level audit specifically, same shape check as before.
audit_ok = (
    len(api_a.audit.events) == 1
    and api_a.audit.events[0]["event_type"] == "API_REQUEST_RECORDED"
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
    response_a.status = "CHANGED"
except FrozenInstanceError:
    immutable_ok = True
happy_engine = new_engine()
happy_status, happy = happy_engine.get_export(FOUNDER_TOKEN, PROPERTY_ID)
happy_ok = (
    happy_status == errors.PASS
    and happy.property_id == PROPERTY_ID
    and happy.data["status"] == "EXPORTED"
    and immutable_ok
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  ENDPOINT:", happy.endpoint if happy else None)
print("  PROPERTY:", happy.property_id if happy else None)
print("  EXPORT:", happy.data if happy else None)
print("  IMMUTABLE:", immutable_ok)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(happy_engine.audit.events))
for event in happy_engine.audit.events:
    print(event)
print()
total = len(tests) + 2  # +determinism +audit
print("VIOLATION TESTS PASSED:", f"{passed}/{total}")
print("OVERALL:", "PASS" if passed == total and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == total and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
