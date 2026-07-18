from dataclasses import dataclass
from era.fusion.fusion_enums import FusionStatus

CANONICAL_TIME_FALLBACK = "1970-01-01T00:00:00Z"
@dataclass(frozen=True)
class FusionEvidence:
    evidence_id: str
    property_id: str
    field_name: str
    normalized_value: str
    provider_id: str
    source_reference: str
    value_type: str = ""
    units: str = ""
    evidence_type: str = ""
    observation_utc: str = ""
    applicable_period: str = ""
    item_identity: str = ""
    semantic_comparison_key: str = ""
@dataclass(frozen=True)
class FieldFusionResult:
    property_id: str
    field_name: str
    status: FusionStatus
    source_count: int
    unique_values: list
    evidence_ids: list
    semantic_comparison_key: str = ""
@dataclass(frozen=True)
class EvidenceFusionPackage:
    property_id: str
    fields: list
    evidence_count: int
    # Canonical bytes include this field.  The engine derives it from the
    # governed input observations, with a fixed fallback for legacy evidence.
    created_at: str = CANONICAL_TIME_FALLBACK
