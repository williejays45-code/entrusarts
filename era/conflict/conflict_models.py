from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.conflict.conflict_enums import ConflictType, ConflictStatus
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class ConflictEvidence:
    evidence_id: str
    property_id: str
    field_name: str
    normalized_value: str
    provider_id: str
    source_reference: str
@dataclass(frozen=True)
class ConflictReport:
    conflict_id: str
    property_id: str
    field_name: str
    conflict_type: ConflictType
    providers: list
    evidence_ids: list
    observed_values: list
    source_references: list
    status: ConflictStatus
    detected_at: str = field(default_factory=utc_now)
