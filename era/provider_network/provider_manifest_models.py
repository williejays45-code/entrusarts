from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.provider_network.provider_manifest_enums import ProviderNetworkStatus, ProviderNetworkRole
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class ProviderHealth:
    success_rate: float
    latency_ms: int
    failures: int
    last_success: str | None = None
@dataclass(frozen=True)
class ProviderManifestEntry:
    provider_id: str
    provider_name: str
    state: str
    county: str
    role: ProviderNetworkRole
    status: ProviderNetworkStatus
    public: bool
    read_only: bool
    legal_basis: str
    version: str
    health: ProviderHealth
    created_at: str = field(default_factory=utc_now)
