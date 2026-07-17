"""
LEGACY: original DCAD capture stub, built before any real DCAD file was
uploaded to this project. Superseded by
era.live_adapters.dcad_bulk_data_adapter.DCADBulkDataAdapter for actual
DCAD ingestion (real ACCOUNT_APPRL_YEAR + ACCOUNT_INFO join, live ZIP
parsing). Retained for regression coverage only -- see
era/acquisition/providers/county/verify_legacy_dcad_capture.py and
verify_legacy_dcad_to_upr.py.
"""
from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass
from era.acquisition.providers.county.dcad_capture_models import DCADPublicRecord
from era.acquisition.providers.county import dcad_capture_errors as errors
class DCADPublicRecordCapture:
    CONNECTOR_ID = "COUNTY_DALLAS_CAD"
    PROVIDER_NAME = "Dallas Central Appraisal District"
    NORMALIZATION_VERSION = "ECM-1.0"
    FIELD_CATEGORY = {
        "account_number": EvidenceCategory.IDENTITY,
        "address": EvidenceCategory.IDENTITY,
        "owner": EvidenceCategory.OWNERSHIP,
        "legal_description": EvidenceCategory.LEGAL,
        "property_class": EvidenceCategory.PARCEL,
        "year_built": EvidenceCategory.BUILDING,
        "living_area": EvidenceCategory.BUILDING,
        "appraised_value": EvidenceCategory.TAX,
        "land_value": EvidenceCategory.TAX,
        "improvement_value": EvidenceCategory.TAX,
        "exemptions": EvidenceCategory.TAX,
        "tax_year": EvidenceCategory.TAX,
    }
    REQUIRED_FIELDS = [
        "property_id",
        "account_number",
        "address",
        "owner",
        "legal_description",
        "property_class",
        "tax_year",
    ]
    def __init__(self, canonical_model=None):
        self.canonical = canonical_model or CanonicalEvidenceModel()
    def capture(self, record: DCADPublicRecord):
        if record is None:
            return errors.DCAD_RECORD_REQUIRED, []
        for field in self.REQUIRED_FIELDS:
            if not getattr(record, field, None):
                return errors.DCAD_FIELD_REQUIRED, []
        if record.legal_basis != "PUBLIC_RECORD":
            return errors.DCAD_NOT_PUBLIC_RECORD, []
        canonical_records = []
        provenance = Provenance(
            connector_id=self.CONNECTOR_ID,
            provider_name=self.PROVIDER_NAME,
            source_name=record.source_name,
            source_class=EvidenceSourceClass.PUBLIC_RECORD,
            retrieved_at=record.retrieved_at,
            legal_basis=record.legal_basis,
            normalization_version=self.NORMALIZATION_VERSION,
            audit_reference=f"AUD-DCAD-{record.account_number}",
        )
        for field_name, category in self.FIELD_CATEGORY.items():
            raw_value = getattr(record, field_name, "")
            if raw_value is None or str(raw_value).strip() == "":
                continue
            evidence = CanonicalEvidenceRecord(
                evidence_id=f"DCAD-{record.account_number}-{field_name}",
                property_id=record.property_id,
                category=category,
                field_name=field_name,
                raw_value=str(raw_value),
                normalized_value=str(raw_value).strip(),
                units=None,
                provenance=provenance,
            )
            status, normalized = self.canonical.normalize_record(evidence)
            if status != "PASS":
                return errors.CANONICALIZATION_FAILED, []
            canonical_records.append(normalized)
        return errors.PASS, canonical_records
    def attempt_write(self):
        return False, errors.READ_ONLY_DCAD_CAPTURE
    def assign_confidence(self):
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
