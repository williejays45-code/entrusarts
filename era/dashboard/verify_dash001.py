import sys
from dataclasses import FrozenInstanceError
from era.dashboard.dashboard_engine import DashboardEngine
from era.dashboard.dashboard_enums import DashboardCardType
from era.dashboard import dashboard_errors as errors
PROPERTY_ID = "ERA-PR-2026-000001"
def dashboard_data(**overrides):
    data = {
        "property": {
            "property_id": PROPERTY_ID,
            "address": "5926 Sandhurst Ln Unit 224",
            "county": "Dallas",
        },
        "evidence": {
            "count": 5,
            "latest": "EV-001",
        },
        "conflicts": {
            "active": 1,
            "latest": "YEAR_BUILT_CONFLICT",
        },
        "decision": {
            "decision": "ACCEPT",
            "reason": "NO_CONFLICTS_SUFFICIENT_EVIDENCE",
        },
        "policy": {
            "verdict": "AUTHORIZED",
            "reason": "DECISION_ALLOWED",
        },
        "export": {
            "export_id": "EXP-ERA-PR-2026-000001-DASHBOARD",
            "status": "EXPORTED",
        },
        "audit": {
            "events": 12,
            "latest": "EXPORT_COMPLETED",
        },
        "health": {
            "api": "HEALTHY",
            "core": "HEALTHY",
            "providers": "DEGRADED",
        },
    }
    data.update(overrides)
    return data
engine = DashboardEngine()
tests = [
    ("EV-001", errors.PROPERTY_REQUIRED, lambda: engine.build_dashboard("", dashboard_data())[0]),
    ("EV-002", errors.DASHBOARD_DATA_REQUIRED, lambda: engine.build_dashboard(PROPERTY_ID, {})[0]),
    ("EV-003", errors.CARD_REQUIRED, lambda: engine.build_dashboard(PROPERTY_ID, dashboard_data(property=None))[0] if False else engine.build_dashboard(PROPERTY_ID, {k:v for k,v in dashboard_data().items() if k != "property"})[0]),
    ("EV-004", errors.READ_ONLY_DASHBOARD, lambda: engine.attempt_write()[1]),
    ("EV-005", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("DASH-001 DASHBOARD SERVICE VERIFICATION")
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
card_engine = DashboardEngine()
card_status, card_view = card_engine.build_dashboard(PROPERTY_ID, dashboard_data())
card_expectations = [
    ("EV-006", DashboardCardType.PROPERTY),
    ("EV-007", DashboardCardType.EVIDENCE),
    ("EV-008", DashboardCardType.CONFLICT),
    ("EV-009", DashboardCardType.DECISION),
    ("EV-010", DashboardCardType.POLICY),
    ("EV-011", DashboardCardType.EXPORT),
    ("EV-012", DashboardCardType.AUDIT),
    ("EV-013", DashboardCardType.HEALTH),
]
for ev_id, expected_type in card_expectations:
    exists = any(card.card_type == expected_type for card in card_view.cards)
    if exists:
        passed += 1
    print(ev_id)
    print("  EXPECTED:", expected_type.value)
    print("  ACTUAL:  ", expected_type.value if exists else "MISSING")
    print("  PASS:    ", exists)
    print()
det_a = DashboardEngine()
status_a, view_a = det_a.build_dashboard(PROPERTY_ID, dashboard_data())
det_b = DashboardEngine()
status_b, view_b = det_b.build_dashboard(PROPERTY_ID, dashboard_data())
deterministic = (
    status_a == status_b
    and view_a.property_id == view_b.property_id
    and [c.card_type for c in view_a.cards] == [c.card_type for c in view_b.cards]
    and [c.title for c in view_a.cards] == [c.title for c in view_b.cards]
    and [c.data for c in view_a.cards] == [c.data for c in view_b.cards]
)
print("EV-014")
print("  EXPECTED:", errors.DETERMINISTIC_DASHBOARD)
print("  ACTUAL:  ", errors.DETERMINISTIC_DASHBOARD if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
audit_ok = (
    len(det_a.audit.events) == 2
    and det_a.audit.events[0]["event_type"] == "DASHBOARD_BUILT"
    and det_a.audit.events[1]["event_type"] == "DASHBOARD_READY"
)
print("EV-015")
print("  EXPECTED:", errors.AUDIT_CHAIN_VERIFIED)
print("  ACTUAL:  ", errors.AUDIT_CHAIN_VERIFIED if audit_ok else "AUDIT_FAIL")
print("  PASS:    ", audit_ok)
print()
if audit_ok:
    passed += 1
immutable_ok = False
try:
    view_a.property_id = "CHANGED"
except FrozenInstanceError:
    immutable_ok = True
happy_engine = DashboardEngine()
happy_status, happy = happy_engine.build_dashboard(PROPERTY_ID, dashboard_data())
happy_ok = (
    happy_status == errors.PASS
    and happy.property_id == PROPERTY_ID
    and len(happy.cards) == 8
    and immutable_ok
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  PROPERTY:", happy.property_id if happy else None)
print("  CARD COUNT:", len(happy.cards) if happy else None)
print("  IMMUTABLE:", immutable_ok)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(happy_engine.audit.events))
for event in happy_engine.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/15")
print("OVERALL:", "PASS" if passed == 15 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 15 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
