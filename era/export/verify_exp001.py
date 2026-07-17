import sys
from dataclasses import FrozenInstanceError
from era.export.export_engine import ExportEngine
from era.export.export_models import ExportRequest
from era.export.export_enums import ExportFormat, ExportStatus
from era.export import export_errors as errors
def request(**overrides):
    data = {
        "property_id": "ERA-PR-2026-000001",
        "decision": "ACCEPT",
        "policy_verdict": "AUTHORIZED",
        "provenance_complete": True,
        "export_format": ExportFormat.JSON,
        "payload": {
            "address": "5926 Sandhurst Ln Unit 224",
            "county": "Dallas",
            "decision": "ACCEPT",
        },
    }
    data.update(overrides)
    return ExportRequest(**data)
engine = ExportEngine()
tests = [
    ("EV-001", errors.PROPERTY_REQUIRED, lambda: engine.export(request(property_id=""))[0]),
    ("EV-002", errors.DECISION_REQUIRED, lambda: engine.export(request(decision=""))[0]),
    ("EV-003", errors.POLICY_REQUIRED, lambda: engine.export(request(policy_verdict=""))[0]),
    ("EV-004", errors.PROVENANCE_REQUIRED, lambda: engine.export(request(provenance_complete=False))[0]),
    ("EV-005", errors.EXPORT_BLOCKED, lambda: engine.export(request(policy_verdict="DENIED"))[0]),
    ("EV-006", errors.UNSUPPORTED_FORMAT, lambda: engine.export(request(export_format="XML"))[0]),
    ("EV-007", errors.READ_ONLY_EXPORT, lambda: engine.attempt_write()[1]),
    ("EV-008", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("EXP-001 EXPORT & DELIVERY ENGINE VERIFICATION")
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
json_engine = ExportEngine()
json_status, json_pkg = json_engine.export(request(export_format=ExportFormat.JSON))
json_ok = (
    json_status == errors.PASS
    and json_pkg.export_format == ExportFormat.JSON
    and json_pkg.status == ExportStatus.EXPORTED
)
print("EV-009")
print("  EXPECTED:", "JSON_EXPORT")
print("  ACTUAL:  ", "JSON_EXPORT" if json_ok else "JSON_FAIL")
print("  PASS:    ", json_ok)
print()
if json_ok:
    passed += 1
csv_engine = ExportEngine()
csv_status, csv_pkg = csv_engine.export(request(export_format=ExportFormat.CSV))
csv_ok = (
    csv_status == errors.PASS
    and csv_pkg.export_format == ExportFormat.CSV
    and csv_pkg.status == ExportStatus.EXPORTED
)
print("EV-010")
print("  EXPECTED:", "CSV_EXPORT")
print("  ACTUAL:  ", "CSV_EXPORT" if csv_ok else "CSV_FAIL")
print("  PASS:    ", csv_ok)
print()
if csv_ok:
    passed += 1
det_a = ExportEngine()
status_a, pkg_a = det_a.export(request(export_format=ExportFormat.API))
det_b = ExportEngine()
status_b, pkg_b = det_b.export(request(export_format=ExportFormat.API))
deterministic = (
    status_a == status_b
    and pkg_a.export_id == pkg_b.export_id
    and pkg_a.property_id == pkg_b.property_id
    and pkg_a.decision == pkg_b.decision
    and pkg_a.policy_verdict == pkg_b.policy_verdict
    and pkg_a.export_format == pkg_b.export_format
    and pkg_a.payload == pkg_b.payload
)
print("EV-011")
print("  EXPECTED:", errors.DETERMINISTIC_EXPORT)
print("  ACTUAL:  ", errors.DETERMINISTIC_EXPORT if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
audit_ok = (
    len(det_a.audit.events) == 2
    and det_a.audit.events[0]["event_type"] == "EXPORT_PACKAGE_CREATED"
    and det_a.audit.events[1]["event_type"] == "EXPORT_COMPLETED"
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
    pkg_a.status = ExportStatus.FAILED
except FrozenInstanceError:
    immutable_ok = True
happy_engine = ExportEngine()
happy_status, happy = happy_engine.export(request(export_format=ExportFormat.DASHBOARD))
happy_ok = (
    happy_status == errors.PASS
    and happy.status == ExportStatus.EXPORTED
    and happy.export_format == ExportFormat.DASHBOARD
    and immutable_ok
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  EXPORT ID:", happy.export_id if happy else None)
print("  FORMAT:", happy.export_format.value if happy else None)
print("  EXPORT STATUS:", happy.status.value if happy else None)
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
