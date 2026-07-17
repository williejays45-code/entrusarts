import sys
from era.fusion.fusion_engine import MultiSourceFusionEngine
from era.fusion.fusion_models import FusionEvidence
from era.fusion.fusion_enums import FusionStatus
from era.fusion import fusion_errors as errors
def ev(evidence_id, field, value, provider="COUNTY_DALLAS_CAD", property_id="ERA-PR-2026-000001"):
    return FusionEvidence(
        evidence_id=evidence_id,
        property_id=property_id,
        field_name=field,
        normalized_value=value,
        provider_id=provider,
        source_reference=f"{provider}-SOURCE",
    )
engine = MultiSourceFusionEngine()
tests = [
    ("EV-001", errors.EVIDENCE_REQUIRED, lambda: engine.fuse([])[0]),
    ("EV-002", errors.DUPLICATE_EVIDENCE, lambda: engine.fuse([
        ev("EV-001", "owner", "John Smith"),
        ev("EV-001", "owner", "John Smith", provider="DALLAS_TAX_OFFICE"),
    ])[0]),
    ("EV-003", errors.PROVIDER_REQUIRED, lambda: engine.fuse([
        ev("EV-002", "owner", "John Smith", provider=""),
    ])[0]),
    ("EV-004", errors.PROPERTY_REQUIRED, lambda: engine.fuse([
        ev("EV-003", "owner", "John Smith", property_id=""),
    ])[0]),
    ("EV-005", errors.FIELD_REQUIRED, lambda: engine.fuse([
        ev("EV-004", "", "John Smith"),
    ])[0]),
    ("EV-006", errors.READ_ONLY_FUSION, lambda: engine.attempt_write()[1]),
    ("EV-007", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("MSF-001 MULTI-SOURCE FUSION VERIFICATION")
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
consensus_engine = MultiSourceFusionEngine()
consensus_status, consensus_package = consensus_engine.fuse([
    ev("EV-C1", "owner", "John Smith", "COUNTY_DALLAS_CAD"),
    ev("EV-C2", "owner", "John Smith", "DALLAS_TAX_OFFICE"),
    ev("EV-C3", "owner", "John Smith", "DALLAS_COUNTY_CLERK"),
])
consensus_ok = (
    consensus_status == errors.PASS
    and consensus_package.fields[0].status == FusionStatus.CONSENSUS
    and consensus_package.fields[0].source_count == 3
)
print("EV-008")
print("  EXPECTED:", errors.CONSENSUS_DETECTED)
print("  ACTUAL:  ", errors.CONSENSUS_DETECTED if consensus_ok else "NO_CONSENSUS")
print("  PASS:    ", consensus_ok)
print()
if consensus_ok:
    passed += 1
conflict_engine = MultiSourceFusionEngine()
conflict_status, conflict_package = conflict_engine.fuse([
    ev("EV-F1", "owner", "John Smith", "COUNTY_DALLAS_CAD"),
    ev("EV-F2", "owner", "Mary Smith", "DALLAS_COUNTY_CLERK"),
])
conflict_ok = (
    conflict_status == errors.PASS
    and conflict_package.fields[0].status == FusionStatus.CONFLICT
    and len(conflict_package.fields[0].unique_values) == 2
)
print("EV-009")
print("  EXPECTED:", errors.CONFLICT_DETECTED)
print("  ACTUAL:  ", errors.CONFLICT_DETECTED if conflict_ok else "NO_CONFLICT")
print("  PASS:    ", conflict_ok)
print()
if conflict_ok:
    passed += 1
det_engine_a = MultiSourceFusionEngine()
det_status_a, det_package_a = det_engine_a.fuse([
    ev("EV-D1", "address", "5926 Sandhurst Ln Unit 224", "COUNTY_DALLAS_CAD"),
    ev("EV-D2", "address", "5926 Sandhurst Ln Unit 224", "DALLAS_TAX_OFFICE"),
    ev("EV-D3", "owner", "John Smith", "COUNTY_DALLAS_CAD"),
])
det_engine_b = MultiSourceFusionEngine()
det_status_b, det_package_b = det_engine_b.fuse([
    ev("EV-D1", "address", "5926 Sandhurst Ln Unit 224", "COUNTY_DALLAS_CAD"),
    ev("EV-D2", "address", "5926 Sandhurst Ln Unit 224", "DALLAS_TAX_OFFICE"),
    ev("EV-D3", "owner", "John Smith", "COUNTY_DALLAS_CAD"),
])
deterministic = (
    det_status_a == det_status_b
    and [f.field_name for f in det_package_a.fields] == [f.field_name for f in det_package_b.fields]
    and [f.status for f in det_package_a.fields] == [f.status for f in det_package_b.fields]
    and [f.unique_values for f in det_package_a.fields] == [f.unique_values for f in det_package_b.fields]
)
print("EV-010")
print("  EXPECTED:", errors.DETERMINISTIC_FUSION)
print("  ACTUAL:  ", errors.DETERMINISTIC_FUSION if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
happy_engine = MultiSourceFusionEngine()
happy_status, happy = happy_engine.fuse([
    ev("EV-H1", "address", "5926 Sandhurst Ln Unit 224", "COUNTY_DALLAS_CAD"),
    ev("EV-H2", "address", "5926 Sandhurst Ln Unit 224", "DALLAS_TAX_OFFICE"),
    ev("EV-H3", "owner", "John Smith", "COUNTY_DALLAS_CAD"),
    ev("EV-H4", "year_built", "1973", "COUNTY_DALLAS_CAD"),
])
happy_ok = (
    happy_status == errors.PASS
    and happy.property_id == "ERA-PR-2026-000001"
    and happy.evidence_count == 4
    and len(happy.fields) == 3
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  PROPERTY:", happy.property_id if happy else None)
print("  EVIDENCE COUNT:", happy.evidence_count if happy else None)
print("  FIELD COUNT:", len(happy.fields) if happy else None)
print("  FIELD STATUSES:", [(f.field_name, f.status.value) for f in happy.fields] if happy else None)
print("  PASS:", happy_ok)
print()
if happy_ok:
    passed += 1
print("AUDIT EVENTS:", len(happy_engine.audit.events))
for event in happy_engine.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/11")
print("OVERALL:", "PASS" if passed == 11 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 11 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
