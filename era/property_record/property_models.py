from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.property_record.property_enums import PropertyType, StrategyType
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class PropertyIdentity:
    property_id: str
    address: str
    city: str
    state: str
    zip_code: str
    county: str
    parcel_apn: str
    latitude: float | None
    longitude: float | None
    property_type: PropertyType
    strategy_type: StrategyType
@dataclass(frozen=True)
class EvidenceEntry:
    evidence_id: str
    property_id: str
    category: str
    value: str
    connector: str
    original_source: str
    retrieved_at: str
    normalization_version: str
    audit_reference: str
    supersedes_evidence_id: str | None = None
    correction_reason: str | None = None
@dataclass
class UnifiedPropertyRecord:
    identity: PropertyIdentity
    evidence: list = field(default_factory=list)
    evaluations: list = field(default_factory=list)
    audit_events: list = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
