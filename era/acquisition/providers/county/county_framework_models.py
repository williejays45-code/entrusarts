from dataclasses import dataclass, field
from datetime import datetime, timezone
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class CountySearchRequest:
    property_id: str
    address: str
    city: str
    county: str
    state: str
    parcel_apn: str | None = None
@dataclass(frozen=True)
class CountyRawEvidence:
    evidence_id: str
    property_id: str
    connector_id: str
    county: str
    provider_name: str
    source_name: str
    legal_basis: str
    field_name: str
    raw_value: str
    retrieved_at: str = field(default_factory=utc_now)
