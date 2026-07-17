from dataclasses import dataclass, field
from datetime import datetime, timezone
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class CountyConnectorRequest:
    property_id: str
    address: str
    county: str
    state: str
    parcel_apn: str | None = None
@dataclass(frozen=True)
class RawCountyEvidence:
    evidence_id: str
    property_id: str
    connector_id: str
    provider_name: str
    source_name: str
    legal_basis: str
    field_name: str
    raw_value: str
    retrieved_at: str = field(default_factory=utc_now)
