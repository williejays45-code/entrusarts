from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.fusion.fusion_enums import FusionStatus
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class FusionEvidence:
    evidence_id: str
    property_id: str
    field_name: str
    normalized_value: str
    provider_id: str
    source_reference: str
@dataclass(frozen=True)
class FieldFusionResult:
    property_id: str
    field_name: str
    status: FusionStatus
    source_count: int
    unique_values: list
    evidence_ids: list
@dataclass(frozen=True)
class EvidenceFusionPackage:
    property_id: str
    fields: list
    evidence_count: int
    created_at: str = field(default_factory=utc_now)
