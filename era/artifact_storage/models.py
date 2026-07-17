"""Immutable ART-001 admission, storage, recovery, and audit models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GovernanceProfilePin:
    profile_id: str
    profile_version: str
    profile_sha256: str


@dataclass(frozen=True)
class AuthorityProjection:
    subject_id: str
    issuer_reference: str
    permissions: tuple[str, ...]
    purpose_codes: tuple[str, ...]
    environment: str
    projection_digest: str


@dataclass(frozen=True)
class RetentionProjection:
    retention_class_id: str
    retention_policy_version: str
    authority_reference: str
    retain_until: str
    legal_basis: str
    environment: str
    projection_digest: str


@dataclass(frozen=True)
class QuotaProjection:
    quota_id: str
    authority_reference: str
    maximum_artifact_bytes: int
    maximum_total_bytes: int
    current_total_bytes: int
    storage_identifier: str
    environment: str
    projection_digest: str


@dataclass(frozen=True)
class AdmissionRequest:
    artifact: object
    observation_id: str
    governance_profile: GovernanceProfilePin
    admission_authority: AuthorityProjection
    retention: RetentionProjection
    quota: QuotaProjection


@dataclass(frozen=True)
class GovernanceMetadata:
    profile_id: str
    profile_version: str
    profile_sha256: str
    retention_class_id: str
    retention_policy_version: str
    retention_authority_reference: str
    retain_until: str
    retention_legal_basis: str
    retention_projection_digest: str
    quota_id: str
    quota_projection_digest: str


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_identity: str
    sha256: str
    media_type: str
    byte_length: int
    governance: GovernanceMetadata
    admission_timestamp: str
    admission_decision: str
    quarantine_status: str
    integrity_status: str


@dataclass(frozen=True)
class AdmissionResult:
    artifact: ArtifactRecord
    observation_id: str
    physical_content_created: bool


@dataclass(frozen=True)
class IntegrityVerification:
    status: str
    expected_sha256: str
    observed_sha256: str
    expected_byte_length: int
    observed_byte_length: int
    expected_media_type: str
    observed_media_type: str


@dataclass(frozen=True)
class RecoveredArtifact:
    artifact_identity: str
    original_bytes: bytes
    sha256: str
    media_type: str
    byte_length: int
    governance_metadata: GovernanceMetadata
    integrity_verification: IntegrityVerification


@dataclass(frozen=True)
class EncryptedEnvelope:
    algorithm: str
    nonce: bytes
    ciphertext: bytes
    wrapped_data_key: bytes
    key_authority_id: str


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    operation_id: str
    requester_id: str
    service_id: str
    purpose_code: str
    artifact_identity: str
    outcome: str
    reason_code: str
    observed_at: str

