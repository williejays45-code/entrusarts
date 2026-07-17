import sys
from era.property_record.unified_property_record import UnifiedPropertyRecordEngine
from era.property_record.property_models import PropertyIdentity, EvidenceEntry, utc_now
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record import property_errors as errors
def identity(**overrides):
    data = {
        "property_id": "ERA-PR-2026-000001",
        "address": "123 Main St",
        "city": "Fort Worth",
        "state": "TX",
        "zip_code": "76102",
        "county": "Tarrant",
        "parcel_apn": "APN-001",
        "latitude": 32.7555,
        "longitude": -97.3308,
        "property_type": PropertyType.SINGLE_FAMILY,
        "strategy_type": StrategyType.BUY_HOLD,
    }
    data.update(overrides)
    return PropertyIdentity(**data)
def evidence(**overrides):
    data = {
        "evidence_id": "EV-001",
        "property_id": "ERA-PR-2026-000001",
        "category": "TAX",
        "value": "2025 assessed value available",
        "connector": "COUNTY_RECORDS",
        "original_source": "County Assessor",
        "retrieved_at": utc_now(),
        "normalization_version": "UPR-NORM-1.0",
        "audit_reference": "AUD-EV-001",
        "supersedes_evidence_id": None,
        "correction_reason": None,
    }
    data.update(overrides)
    return EvidenceEntry(**data)
engine = UnifiedPropertyRecordEngine()
tests = [
    ("EV-001", errors.PROPERTY_REQUIRED, lambda: engine.create_property(identity(property_id=""))[0]),
    ("EV-002", errors.INVALID_PROPERTY_TYPE, lambda: engine.create_property(identity(property_id="BAD-001", property_type="HOUSE"))[0]),
    ("EV-003", errors.INVALID_STRATEGY_TYPE, lambda: engine.create_property(identity(property_id="BAD-002", strategy_type="RENT"))[0]),
    ("EV-004", errors.PROPERTY_REQUIRED, lambda: engine.add_evidence("MISSING", evidence())[0]),
    ("EV-005", errors.READ_ONLY_PROPERTY, lambda: engine.attempt_reasoning_write("evidence")[1]),
]
print("UPR-001 UNIFIED PROPERTY RECORD VERIFICATION")
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
status, record = engine.create_property(identity())
e_status, ev = engine.add_evidence("ERA-PR-2026-000001", evidence())
sup_status, sup = engine.add_evidence(
    "ERA-PR-2026-000001",
    evidence(
        evidence_id="EV-002",
        value="Corrected assessed value available",
        supersedes_evidence_id="EV-001",
        correction_reason="Corrected county record import.",
        audit_reference="AUD-EV-002",
    )
)
found = engine.find_existing_property("APN-001", "Tarrant", "123 Main St")
happy_ok = (
    status == errors.PASS
    and e_status == errors.PASS
    and sup_status == errors.PASS
    and found is not None
    and len(record.evidence) == 2
    and record.evidence[1].supersedes_evidence_id == "EV-001"
)
print("HAPPY PATH")
print("  PROPERTY CREATE:", status)
print("  EVIDENCE ADD:", e_status)
print("  SUPERSEDES:", sup_status)
print("  EVIDENCE COUNT:", len(record.evidence) if record else None)
print("  DEDUP FOUND:", found.identity.property_id if found else None)
print("  PASS:", happy_ok)
print()
if happy_ok:
    passed += 1
print("AUDIT EVENTS:", len(engine.audit.events))
for event in engine.audit.events:
    print(event)
print()
print("CHECKS PASSED:", f"{passed}/6")
print("OVERALL:", "PASS" if passed == 6 else "FAIL")
_ERA_OVERALL_OK = (passed == 6)
if not _ERA_OVERALL_OK:
    sys.exit(1)
