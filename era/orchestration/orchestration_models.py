from dataclasses import dataclass, field
from datetime import datetime, timezone
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class OrchestrationRequest:
    property_id: str
    providers: list
@dataclass(frozen=True)
class OrchestrationResult:
    property_id: str
    providers_run: list
    evidence_count: int
    canonical_count: int
    status: str
    created_at: str = field(default_factory=utc_now)
