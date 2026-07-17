from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.jurisdiction.jurisdiction_enums import ProviderOperationalStatus, ProviderRole
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class JurisdictionProvider:
    provider_id: str
    provider_name: str
    role: ProviderRole
    status: ProviderOperationalStatus
@dataclass(frozen=True)
class JurisdictionRecord:
    state: str
    county: str
    providers: list
    created_at: str = field(default_factory=utc_now)
@dataclass(frozen=True)
class JurisdictionRequest:
    state: str
    county: str
