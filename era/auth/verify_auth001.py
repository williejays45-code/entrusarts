import sys
from dataclasses import FrozenInstanceError
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import MockTokenStore
from era.auth.auth_enums import AuthPermission
from era.auth import auth_errors as errors
engine = AuthEngine(token_store=MockTokenStore())
tests = [
    ("EV-001", errors.TOKEN_REQUIRED, lambda: engine.authenticate("")[0]),
    ("EV-002", errors.INVALID_TOKEN, lambda: engine.authenticate("bad-token")[0]),
    ("EV-003", errors.EXPIRED_TOKEN, lambda: engine.authenticate("expired-token")[0]),
    ("EV-004", errors.PASS, lambda: engine.authenticate("user-token")[0]),
    ("EV-005", errors.PASS, lambda: engine.authorize(engine.authenticate("user-token")[1], AuthPermission.READ)),
    ("EV-006", errors.PERMISSION_DENIED, lambda: engine.authorize(engine.authenticate("user-token")[1], AuthPermission.ADMIN)),
    ("EV-007", errors.PASS, lambda: engine.authorize(engine.authenticate("admin-token")[1], AuthPermission.ADMIN)),
    ("EV-008", errors.PASS, lambda: engine.authorize(engine.authenticate("founder-token")[1], AuthPermission.FOUNDER)),
    ("EV-009", errors.READ_ONLY_AUTH, lambda: engine.attempt_write()[1]),
    ("EV-010", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("AUTH-001 AUTHENTICATION ENGINE VERIFICATION")
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
auth_a = AuthEngine(token_store=MockTokenStore())
status_a, result_a = auth_a.authenticate("founder-token")
auth_a_status = auth_a.authorize(result_a, AuthPermission.FOUNDER)
auth_b = AuthEngine(token_store=MockTokenStore())
status_b, result_b = auth_b.authenticate("founder-token")
auth_b_status = auth_b.authorize(result_b, AuthPermission.FOUNDER)
deterministic = (
    status_a == status_b
    and auth_a_status == auth_b_status
    and result_a.user_id == result_b.user_id
    and result_a.role == result_b.role
    and result_a.permissions == result_b.permissions
)
print("EV-011")
print("  EXPECTED:", errors.DETERMINISTIC_AUTHORIZATION)
print("  ACTUAL:  ", errors.DETERMINISTIC_AUTHORIZATION if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
audit_ok = (
    len(auth_a.audit.events) == 2
    and auth_a.audit.events[0]["event_type"] == "AUTHENTICATED"
    and auth_a.audit.events[1]["event_type"] == "AUTHORIZED"
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
    result_a.authorized = False
except FrozenInstanceError:
    immutable_ok = True
happy_engine = AuthEngine(token_store=MockTokenStore())
happy_status, happy = happy_engine.authenticate("founder-token")
happy_permission = happy_engine.authorize(happy, AuthPermission.FOUNDER)
happy_ok = (
    happy_status == errors.PASS
    and happy_permission == errors.PASS
    and happy.user_id == "FOUNDER-001"
    and "FOUNDER" in happy.permissions
    and immutable_ok
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  USER:", happy.user_id if happy else None)
print("  ROLE:", happy.role if happy else None)
print("  PERMISSIONS:", happy.permissions if happy else None)
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
