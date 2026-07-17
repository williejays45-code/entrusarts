import sys
from dataclasses import FrozenInstanceError
from era.conflict.conflict_resolver import EvidenceConflictResolver
from era.conflict.conflict_models import ConflictEvidence
from era.conflict.conflict_enums import ConflictType
from era.conflict import conflict_errors as errors
def ev(evidence_id, field, value, provider="COUNTY_DALLAS_CAD", property_id="ERA-PR-2026-000001"):
    return ConflictEvidence(
        evidence_id=evidence_id,
        property_id=property_id,
        field_name=field,
        normalized_value=value,
        provider_id=provider,
        source_reference=f"{provider}-SOURCE",
    )
engine = EvidenceConflictResolver()
tests = [
    ("EV-001", errors.EVIDENCE_REQUIRED, lambda: engine.resolve([])[0]),
    ("EV-002", errors.DUPLICATE_EVIDENCE, lambda: engine.resolve([
        ev("EV-001", "owner", "John Smith"),
        ev("EV-001", "owner", "Mary Smith", provider="DALLAS_COUNTY_CLERK"),
    ])[0]),
    ("EV-003", errors.FIELD_REQUIRED, lambda: engine.resolve([
        ev("EV-002", "", "John Smith"),
    ])[0]),
    ("EV-004", errors.PROPERTY_REQUIRED, lambda: engine.resolve([
        ev("EV-003", "owner", "John Smith", property_id=""),
    ])[0]),
    ("EV-005", errors.PROVIDER_REQUIRED, lambda: engine.resolve([
        ev("EV-004", "owner", "John Smith", provider=""),
    ])[0]),
    ("EV-006", errors.READ_ONLY_CONFLICT, lambda: engine.attempt_write()[1]),
    ("EV-007", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("ECR-001 EVIDENCE CONFLICT RESOLVER VERIFICATION")
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
owner_engine = EvidenceConflictResolver()
owner_status, owner_reports = owner_engine.resolve([
    ev("EV-O1", "owner", "John Smith", "COUNTY_DALLAS_CAD"),
    ev("EV-O2", "owner", "Mary Smith", "DALLAS_COUNTY_CLERK"),
])
owner_ok = (
    owner_status == errors.PASS
    and owner_reports
    and owner_reports[0].conflict_type == ConflictType.OWNER_CONFLICT
)
print("EV-008")
print("  EXPECTED:", "OWNER_CONFLICT")
print("  ACTUAL:  ", owner_reports[0].conflict_type.value if owner_reports else None)
print("  PASS:    ", owner_ok)
print()
if owner_ok:
    passed += 1
address_engine = EvidenceConflictResolver()
address_status, address_reports = address_engine.resolve([
    ev("EV-A1", "address", "5926 Sandhurst Ln Unit 224", "COUNTY_DALLAS_CAD"),
    ev("EV-A2", "address", "5926 Sandhurst Lane Apt 224", "DALLAS_TAX_OFFICE"),
])
address_ok = (
    address_status == errors.PASS
    and address_reports
    and address_reports[0].conflict_type == ConflictType.ADDRESS_CONFLICT
)
print("EV-009")
print("  EXPECTED:", "ADDRESS_CONFLICT")
print("  ACTUAL:  ", address_reports[0].conflict_type.value if address_reports else None)
print("  PASS:    ", address_ok)
print()
if address_ok:
    passed += 1
det_engine_a = EvidenceConflictResolver()
det_status_a, det_reports_a = det_engine_a.resolve([
    ev("EV-D1", "year_built", "1967", "REALTOR"),
    ev("EV-D2", "year_built", "1973", "AUCTION"),
])
det_engine_b = EvidenceConflictResolver()
det_status_b, det_reports_b = det_engine_b.resolve([
    ev("EV-D1", "year_built", "1967", "REALTOR"),
    ev("EV-D2", "year_built", "1973", "AUCTION"),
])
deterministic = (
    det_status_a == det_status_b
    and [r.conflict_id for r in det_reports_a] == [r.conflict_id for r in det_reports_b]
    and [r.conflict_type for r in det_reports_a] == [r.conflict_type for r in det_reports_b]
    and [r.observed_values for r in det_reports_a] == [r.observed_values for r in det_reports_b]
)
print("EV-010")
print("  EXPECTED:", errors.DETERMINISTIC_CONFLICT)
print("  ACTUAL:  ", errors.DETERMINISTIC_CONFLICT if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
immutable_ok = False
try:
    det_reports_a[0].field_name = "changed"
except FrozenInstanceError:
    immutable_ok = True
print("EV-011")
print("  EXPECTED:", errors.IMMUTABLE_REPORT)
print("  ACTUAL:  ", errors.IMMUTABLE_REPORT if immutable_ok else "MUTABLE_REPORT")
print("  PASS:    ", immutable_ok)
print()
if immutable_ok:
    passed += 1
multi_engine = EvidenceConflictResolver()
multi_status, multi_reports = multi_engine.resolve([
    ev("EV-M1", "owner", "John Smith", "COUNTY_DALLAS_CAD"),
    ev("EV-M2", "owner", "Mary Smith", "DALLAS_COUNTY_CLERK"),
    ev("EV-M3", "year_built", "1967", "REALTOR"),
    ev("EV-M4", "year_built", "1973", "AUCTION"),
])
multi_ok = (
    multi_status == errors.PASS
    and len(multi_reports) == 2
)
print("EV-012")
print("  EXPECTED:", errors.MULTIPLE_CONFLICTS_DETECTED)
print("  ACTUAL:  ", errors.MULTIPLE_CONFLICTS_DETECTED if multi_ok else "MULTIPLE_CONFLICT_FAIL")
print("  PASS:    ", multi_ok)
print()
if multi_ok:
    passed += 1
happy_engine = EvidenceConflictResolver()
happy_status, happy_reports = happy_engine.resolve([
    ev("EV-H1", "year_built", "1967", "REALTOR"),
    ev("EV-H2", "year_built", "1973", "AUCTION"),
    ev("EV-H3", "address", "5926 Sandhurst Ln Unit 224", "COUNTY_DALLAS_CAD"),
    ev("EV-H4", "address", "5926 Sandhurst Ln Unit 224", "DALLAS_TAX_OFFICE"),
])
happy_ok = (
    happy_status == errors.PASS
    and len(happy_reports) == 1
    and happy_reports[0].field_name == "year_built"
    and happy_reports[0].conflict_type == ConflictType.YEAR_BUILT_CONFLICT
    and len(happy_reports[0].evidence_ids) == 2
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  CONFLICT COUNT:", len(happy_reports))
print("  FIELD:", happy_reports[0].field_name if happy_reports else None)
print("  TYPE:", happy_reports[0].conflict_type.value if happy_reports else None)
print("  VALUES:", happy_reports[0].observed_values if happy_reports else None)
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
