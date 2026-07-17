from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.export.export_enums import ExportStatus, ExportFormat
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class ExportRequest:
    property_id: str
    decision: str
    policy_verdict: str
    provenance_complete: bool
    export_format: ExportFormat
    payload: dict
@dataclass(frozen=True)
class ExportPackage:
    export_id: str
    property_id: str
    decision: str
    policy_verdict: str
    export_format: ExportFormat
    status: ExportStatus
    payload: dict
    created_at: str = field(default_factory=utc_now)
