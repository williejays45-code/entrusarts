from dataclasses import dataclass, field
from datetime import datetime, timezone
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class ProviderEvidence:
    field_name: str
    raw_value: str
@dataclass(frozen=True)
class ProviderPackage:
    provider_id: str
    provider_name: str
    legal_basis: str
    source_reference: str
    property_id: str
    evidence: list
    connector_version: str
    adapter_version: str
    retrieved_at: str = field(default_factory=utc_now)
