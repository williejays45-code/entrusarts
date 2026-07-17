from dataclasses import dataclass, field
from datetime import datetime, timezone
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class ApiResponse:
    status: str
    endpoint: str
    property_id: str | None
    data: dict
    created_at: str = field(default_factory=utc_now)
