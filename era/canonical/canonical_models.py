from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class Provenance:
    connector_id: str
    provider_name: str
    source_name: str
    source_class: EvidenceSourceClass
    retrieved_at: str
    legal_basis: str
    normalization_version: str
    audit_reference: str
@dataclass(frozen=True)
class CanonicalEvidenceRecord:
    evidence_id: str
    property_id: str
    category: EvidenceCategory
    field_name: str
    raw_value: str
    normalized_value: str
    units: str | None
    provenance: Provenance
    # ECM-TYPE-001: defaults to TEXT so every existing construction of
    # this record (Dallas/Tarrant/Manual adapters, every prior test)
    # is unaffected without being touched -- only a caller that
    # explicitly knows a field is DECIMAL/CURRENCY/IDENTIFIER/DATE/etc.
    # needs to say so.
    value_type: EvidenceValueType = EvidenceValueType.TEXT
    created_at: str = field(default_factory=utc_now)
