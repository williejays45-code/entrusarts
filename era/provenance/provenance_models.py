from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.provenance.provenance_enums import EvidenceStatus
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class ProvenanceInput:
    evidence_id: str
    property_id: str
    canonical_field: str
    canonical_value: str
    original_value: str
    provider_id: str
    provider_name: str
    legal_basis: str
    source_reference: str
    retrieved_at: str
    connector_version: str
    adapter_version: str
    normalization_version: str
    previous_evidence_id: str | None = None
    evidence_hash: str | None = None
    artifact_sha256: str = ""
    package_id: str = ""
    execution_id: str = ""
    canonical_source_id: str = ""
    parser_id: str = ""
    parser_version: str = ""
    schema_profile_id: str = ""
    schema_profile_version: str = ""
    source_location: str = ""
    trace_contract_version: str = ""
    candidate_id: str = ""
    candidate_validation_status: str = ""
    artifact_algorithm: str = ""
    artifact_digest: str = ""
    artifact_byte_length: int = 0
    artifact_media_type: str = ""
    artifact_content_uri: str = ""
    original_lexical_value: str = ""
    parsed_value: str = ""
    proposed_value_type: str = ""
    source_class: str = ""
    verification_status: str = ""
    submitted_evidence_digest: str = ""
    evidence_type: str = ""
    semantic_comparison_key: str = ""
    applicable_period: str = ""
    item_identity: str = ""
@dataclass(frozen=True)
class ProvenanceRecord:
    evidence_id: str
    property_id: str
    canonical_field: str
    canonical_value: str
    original_value: str
    provider_id: str
    provider_name: str
    legal_basis: str
    source_reference: str
    retrieved_at: str
    connector_version: str
    adapter_version: str
    normalization_version: str
    evidence_hash: str
    previous_evidence_id: str | None
    superseded_by: str | None
    chain_position: int
    status: EvidenceStatus
    created_at: str = field(default_factory=utc_now)
    artifact_sha256: str = ""
    package_id: str = ""
    execution_id: str = ""
    canonical_source_id: str = ""
    parser_id: str = ""
    parser_version: str = ""
    schema_profile_id: str = ""
    schema_profile_version: str = ""
    source_location: str = ""
    trace_contract_version: str = ""
    candidate_id: str = ""
    candidate_validation_status: str = ""
    artifact_algorithm: str = ""
    artifact_digest: str = ""
    artifact_byte_length: int = 0
    artifact_media_type: str = ""
    artifact_content_uri: str = ""
    original_lexical_value: str = ""
    parsed_value: str = ""
    proposed_value_type: str = ""
    source_class: str = ""
    verification_status: str = ""
    submitted_evidence_digest: str = ""
    evidence_type: str = ""
    semantic_comparison_key: str = ""
    applicable_period: str = ""
    item_identity: str = ""
