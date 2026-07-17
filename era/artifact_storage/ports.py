"""Backend-neutral ART-001 authority ports."""

from __future__ import annotations

from typing import Protocol

from .models import (
    ArtifactRecord, AuditEvent, AuthorityProjection, EncryptedEnvelope,
    QuotaProjection, RetentionProjection,
)


class GovernanceProjectionVerifier(Protocol):
    def verify_authority(self, projection: AuthorityProjection) -> bool: ...
    def verify_retention(self, projection: RetentionProjection) -> bool: ...
    def verify_quota(self, projection: QuotaProjection) -> bool: ...


class EnvelopeCipher(Protocol):
    algorithm: str
    key_authority_id: str

    def encrypt(self, plaintext: bytes, authenticated_metadata: bytes) -> EncryptedEnvelope: ...
    def decrypt(self, envelope: EncryptedEnvelope, authenticated_metadata: bytes) -> bytes: ...


class ArtifactBackend(Protocol):
    storage_identifier: str

    def total_plaintext_bytes(self) -> int: ...
    def write_once(self, record: ArtifactRecord, envelope: EncryptedEnvelope) -> bool: ...
    def append_observation(self, observation_id: str, record: ArtifactRecord) -> None: ...
    def read(self, artifact_identity: str) -> tuple[ArtifactRecord, EncryptedEnvelope]: ...
    def quarantine(self, artifact_identity: str, operation_id: str, reason_code: str, observed_at: str) -> None: ...
    def is_quarantined(self, artifact_identity: str) -> bool: ...


class DurableAuditSink(Protocol):
    def append(self, event: AuditEvent) -> None: ...

