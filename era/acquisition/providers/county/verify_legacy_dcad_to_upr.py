"""
LEGACY VERIFICATION

Purpose:
    Verifies the original stub capture model (DCADPublicRecordCapture)
    through to UnifiedPropertyRecordEngine, built before any real DCAD
    file was ever uploaded to this project.

This does NOT validate:
    - DCADBulkDataAdapter
    - ACCOUNT_INFO join
    - ACCOUNT_APPRL_YEAR ingestion
    - live ZIP parsing

See instead:
    era/live_adapters/verify_live_adapter001b.py
    era/live_adapters/verify_dcad_join001.py

Retained (not deleted) for regression coverage of the original stub
model. A passing result here says only that the old stub's hardcoded
fixture still flows into UPR correctly -- it does not exercise the
real DCAD adapter, the real join, or any uploaded production data.
"""
import sys
from era.acquisition.providers.county.dcad_public_record_capture import DCADPublicRecordCapture
from era.acquisition.providers.county.dcad_capture_models import DCADPublicRecord
from era.property_record.unified_property_record import UnifiedPropertyRecordEngine
from era.property_record.property_models import PropertyIdentity, EvidenceEntry
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record import property_errors as property_errors
def create_identity():
    return PropertyIdentity(
        property_id="ERA-PR-2026-000001",
        address="5926 Sandhurst Ln Unit 224",
        city="Dallas",
        state="TX",
        zip_code="75206",
        county="Dallas",
        parcel_apn="DCAD-PENDING",
        latitude=None,
        longitude=None,
        property_type=PropertyType.CONDO,
        strategy_type=StrategyType.BUY_HOLD,
    )
def dcad_record():
    return DCADPublicRecord(
        property_id="ERA-PR-2026-000001",
        account_number="DCAD-TEST-001",
        address="5926 Sandhurst Ln Unit 224, Dallas, TX 75206",
        owner="PUBLIC RECORD OWNER",
        legal_description="THE TUSCANY CONDOS UNIT 224",
        property_class="CONDOMINIUM",
        year_built="AWAITING OFFICIAL ENTRY",
        living_area="1046",
        appraised_value="AWAITING OFFICIAL ENTRY",
        land_value="AWAITING OFFICIAL ENTRY",
        improvement_value="AWAITING OFFICIAL ENTRY",
        exemptions="AWAITING OFFICIAL ENTRY",
        tax_year="2025",
    )
print("DCAD ? ECM ? UPR INTEGRATION VERIFICATION")
print("=" * 70)
upr = UnifiedPropertyRecordEngine()
capture = DCADPublicRecordCapture()
property_status, property_record = upr.create_property(create_identity())
capture_status, canonical_records = capture.capture(dcad_record())
added = 0
if capture_status == "PASS":
    for rec in canonical_records:
        evidence = EvidenceEntry(
            evidence_id=rec.evidence_id,
            property_id=rec.property_id,
            category=rec.category.value,
            value=rec.normalized_value,
            connector=rec.provenance.connector_id,
            original_source=rec.provenance.provider_name,
            retrieved_at=rec.provenance.retrieved_at,
            normalization_version=rec.provenance.normalization_version,
            audit_reference=rec.provenance.audit_reference,
        )
        status, _ = upr.add_evidence(rec.property_id, evidence)
        if status == property_errors.PASS:
            added += 1
happy_ok = (
    property_status == property_errors.PASS
    and capture_status == "PASS"
    and added == len(canonical_records)
    and len(property_record.evidence) == len(canonical_records)
)
print("PROPERTY CREATE:", property_status)
print("DCAD CAPTURE:", capture_status)
print("CANONICAL RECORDS:", len(canonical_records))
print("UPR EVIDENCE ADDED:", added)
print("UPR EVIDENCE COUNT:", len(property_record.evidence))
print("PASS:", happy_ok)
print()
print("UPR AUDIT EVENTS:", len(upr.audit.events))
for event in upr.audit.events:
    print(event)
print()
print("OVERALL:", "PASS" if happy_ok else "FAIL")
_ERA_OVERALL_OK = (happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
