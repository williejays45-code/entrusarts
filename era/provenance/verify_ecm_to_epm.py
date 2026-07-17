import sys
from era.provenance.provenance_manager import EvidenceProvenanceManager
from era.provenance.provenance_models import ProvenanceInput
from era.provenance import provenance_errors as errors
class CanonicalEvidenceRecord:
    def __init__(self):
        self.evidence_id = "EV-CAN-001"
        self.property_id = "ERA-PR-2026-000001"
        self.category = "IDENTITY"
        self.field_name = "address"
        self.raw_value = "5926 SANDHURST LN UNIT 224"
        self.normalized_value = "5926 Sandhurst Ln Unit 224"
        self.units = None
        self.provenance = {
            "provider_id": "COUNTY_DALLAS_CAD",
            "provider_name": "Dallas Central Appraisal District",
            "legal_basis": "PUBLIC_RECORD",
            "source_reference": "DCAD-PUBLIC-SEARCH",
            "retrieved_at": "2026-07-08T00:00:00",
            "connector_version": "1.0",
            "adapter_version": "LPA-001.0",
            "normalization_version": "ECM-001.0",
        }
def to_provenance_input(canonical):
    return ProvenanceInput(
        evidence_id=canonical.evidence_id,
        property_id=canonical.property_id,
        canonical_field=canonical.field_name,
        canonical_value=canonical.normalized_value,
        original_value=canonical.raw_value,
        provider_id=canonical.provenance["provider_id"],
        provider_name=canonical.provenance["provider_name"],
        legal_basis=canonical.provenance["legal_basis"],
        source_reference=canonical.provenance["source_reference"],
        retrieved_at=canonical.provenance["retrieved_at"],
        connector_version=canonical.provenance["connector_version"],
        adapter_version=canonical.provenance["adapter_version"],
        normalization_version=canonical.provenance["normalization_version"],
        previous_evidence_id=None,
        evidence_hash=None,
    )
print("ECM -> EPM BOUNDARY VERIFICATION")
print("=" * 70)
manager = EvidenceProvenanceManager()
canonical = CanonicalEvidenceRecord()
status, record = manager.register_evidence(to_provenance_input(canonical))
happy_ok = (
    status == errors.PASS
    and record is not None
    and record.evidence_id == canonical.evidence_id
    and record.property_id == canonical.property_id
    and record.canonical_field == canonical.field_name
    and record.canonical_value == canonical.normalized_value
    and record.original_value == canonical.raw_value
    and record.provider_id == "COUNTY_DALLAS_CAD"
    and record.evidence_hash is not None
)
print("STATUS:", status)
print("EVIDENCE:", record.evidence_id if record else None)
print("PROPERTY:", record.property_id if record else None)
print("FIELD:", record.canonical_field if record else None)
print("VALUE:", record.canonical_value if record else None)
print("PROVIDER:", record.provider_id if record else None)
print("HASH:", record.evidence_hash if record else None)
print("PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(manager.audit.events))
for event in manager.audit.events:
    print(event)
print()
print("OVERALL:", "PASS" if happy_ok else "FAIL")
_ERA_OVERALL_OK = (happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
