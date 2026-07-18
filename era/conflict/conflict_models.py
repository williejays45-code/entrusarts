from dataclasses import dataclass
from era.conflict.conflict_enums import ConflictType, ConflictStatus

CANONICAL_TIME_FALLBACK = "1970-01-01T00:00:00Z"
@dataclass(frozen=True)
class ConflictEvidence:
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
    semantic_comparison_key: str = ""
    # Canonical bytes include this field.  The resolver must derive it from
    # governed evidence observations, never from the wall clock.
    detected_at: str = CANONICAL_TIME_FALLBACK
