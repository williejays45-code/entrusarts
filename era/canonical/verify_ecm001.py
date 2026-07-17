import sys
from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance, utc_now
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass
from era.canonical import canonical_errors as errors
def provenance(**overrides):
    data = {
        "connector_id": "COUNTY_TARRANT_ASSESSOR",
        "provider_name": "Tarrant County Assessor",
        "source_name": "County Public Records",
        "source_class": EvidenceSourceClass.PUBLIC_RECORD,
        "retrieved_at": utc_now(),
        "legal_basis": "PUBLIC_RECORD",
        "normalization_version": "ECM-1.0",
        "audit_reference": "AUD-CAN-001",
    }
    data.update(overrides)
    return Provenance(**data)
def record(**overrides):
    data = {
        "evidence_id": "EV-CAN-001",
        "property_id": "ERA-PR-2026-000001",
        "category": EvidenceCategory.OWNERSHIP,
        "field_name": "owner_name",
        "raw_value": "JOHN A DOE",
        "normalized_value": "John A. Doe",
        "units": None,
        "provenance": provenance(),
    }
    data.update(overrides)
    return CanonicalEvidenceRecord(**data)
engine = CanonicalEvidenceModel()
tests = [
    ("EV-001", errors.CANONICAL_RECORD_REQUIRED, lambda: engine.normalize_record(None)[0]),
    ("EV-002", errors.INVALID_CATEGORY, lambda: engine.normalize_record(record(category="OWNER"))[0]),
    ("EV-003", errors.PROVENANCE_REQUIRED, lambda: engine.normalize_record(record(provenance=None))[0]),
    ("EV-004", errors.INVALID_SOURCE_CLASS, lambda: engine.normalize_record(record(provenance=provenance(source_class="PUBLIC")))[0]),
    ("EV-005", errors.RAW_VALUE_REQUIRED, lambda: engine.normalize_record(record(raw_value=""))[0]),
    ("EV-006", errors.NORMALIZED_VALUE_REQUIRED, lambda: engine.normalize_record(record(normalized_value=""))[0]),
    ("EV-007", errors.NUMERIC_LEAKAGE_DETECTED, lambda: engine.normalize_record(record(normalized_value="weight = 0.3187"))[0]),
    ("EV-008", errors.READ_ONLY_CANONICAL, lambda: engine.attempt_write("recommendation")[1]),
    ("EV-009", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.attempt_write("confidence")[1]),
]
print("ECM-001 CANONICAL EVIDENCE MODEL VERIFICATION")
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
status1, rec1 = engine.normalize_record(record(evidence_id="EV-DET"))
status2, rec2 = engine.normalize_record(record(evidence_id="EV-DET"))
deterministic = (
    status1 == status2
    and rec1 is not None
    and rec2 is not None
    and rec1.evidence_id == rec2.evidence_id
    and rec1.category == rec2.category
    and rec1.field_name == rec2.field_name
    and rec1.normalized_value == rec2.normalized_value
    and rec1.provenance.normalization_version == rec2.provenance.normalization_version
)
print("EV-010")
print("  EXPECTED:", errors.DETERMINISTIC_CANONICALIZATION)
print("  ACTUAL:  ", errors.DETERMINISTIC_CANONICALIZATION if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
happy_status, happy = engine.normalize_record(record())
happy_ok = (
    happy_status == errors.PASS
    and happy is not None
    and happy.normalized_value == "John A. Doe"
)
print("HAPPY PATH")
print("  STATUS:", happy_status)
print("  EVIDENCE:", happy.evidence_id if happy else None)
print("  FIELD:", happy.field_name if happy else None)
print("  VALUE:", happy.normalized_value if happy else None)
print("  SOURCE:", happy.provenance.provider_name if happy else None)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(engine.audit.events))
for event in engine.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/10")
print("OVERALL:", "PASS" if passed == 10 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 10 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
