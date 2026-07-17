"""
LEGACY VERIFICATION

Purpose:
    Verifies the original stub capture model (DCADPublicRecordCapture),
    built before any real DCAD file was ever uploaded to this project.

This does NOT validate:
    - DCADBulkDataAdapter
    - ACCOUNT_INFO join
    - ACCOUNT_APPRL_YEAR ingestion
    - live ZIP parsing

See instead:
    era/live_adapters/verify_live_adapter001b.py
    era/live_adapters/verify_dcad_join001.py

Retained (not deleted) for regression coverage of the original stub
model, which some other legacy code may still reference. A passing
result here says only that DCADPublicRecordCapture's own hardcoded
fixture still round-trips correctly -- nothing about it should be
read as evidence about the real DCAD adapter.
"""
import sys
from era.acquisition.providers.county.dcad_public_record_capture import DCADPublicRecordCapture
from era.acquisition.providers.county.dcad_capture_models import DCADPublicRecord
from era.acquisition.providers.county import dcad_capture_errors as errors
def sample_record(**overrides):
    data = {
        "property_id": "ERA-PR-2026-000001",
        "account_number": "DCAD-TEST-001",
        "address": "5926 Sandhurst Ln Unit 224, Dallas, TX 75206",
        "owner": "PUBLIC RECORD OWNER",
        "legal_description": "THE TUSCANY CONDOS UNIT 224",
        "property_class": "CONDOMINIUM",
        "year_built": "AWAITING OFFICIAL ENTRY",
        "living_area": "1046",
        "appraised_value": "AWAITING OFFICIAL ENTRY",
        "land_value": "AWAITING OFFICIAL ENTRY",
        "improvement_value": "AWAITING OFFICIAL ENTRY",
        "exemptions": "AWAITING OFFICIAL ENTRY",
        "tax_year": "2025",
    }
    data.update(overrides)
    return DCADPublicRecord(**data)
engine = DCADPublicRecordCapture()
tests = [
    ("EV-001", errors.DCAD_RECORD_REQUIRED, lambda: engine.capture(None)[0]),
    ("EV-002", errors.DCAD_FIELD_REQUIRED, lambda: engine.capture(sample_record(account_number=""))[0]),
    ("EV-003", errors.DCAD_NOT_PUBLIC_RECORD, lambda: engine.capture(sample_record(legal_basis="LISTING_SITE"))[0]),
    ("EV-004", errors.READ_ONLY_DCAD_CAPTURE, lambda: engine.attempt_write()[1]),
    ("EV-005", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.assign_confidence()[1]),
]
print("DCAD PUBLIC RECORD CAPTURE VERIFICATION")
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
status, records = engine.capture(sample_record())
happy_ok = (
    status == errors.PASS
    and len(records) >= 7
    and records[0].property_id == "ERA-PR-2026-000001"
)
print("HAPPY PATH")
print("  STATUS:", status)
print("  CANONICAL COUNT:", len(records))
print("  FIRST FIELD:", records[0].field_name if records else None)
print("  FIRST VALUE:", records[0].normalized_value if records else None)
print("  SOURCE:", records[0].provenance.provider_name if records else None)
print("  PASS:", happy_ok)
print()
print("CANONICAL AUDIT EVENTS:", len(engine.canonical.audit.events))
for event in engine.canonical.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/5")
print("OVERALL:", "PASS" if passed == 5 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 5 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
