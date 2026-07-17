"""ART-001 governed admission and exact historical recovery authority."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Callable

from .errors import ArtifactStorageError
from .models import (
    AdmissionRequest, AdmissionResult, ArtifactRecord, AuditEvent,
    AuthorityProjection, GovernanceMetadata, IntegrityVerification,
    RecoveredArtifact,
)
from .ports import ArtifactBackend, DurableAuditSink, EnvelopeCipher, GovernanceProjectionVerifier
from .profile import DEVELOPMENT_PROFILE_ID, PRODUCTION_ENVIRONMENT, verify_production_profile


ARTIFACT_WRITE = "ARTIFACT_WRITE"
ARTIFACT_READ = "ARTIFACT_READ"
ADMITTED = "ADMITTED"
NOT_QUARANTINED = "NOT_QUARANTINED"
QUARANTINED = "QUARANTINED"
VERIFIED = "VERIFIED"
AES_256_GCM = "AES-256-GCM"


class ArtifactStorageAuthority:
    """Owns bytes and recovery only; it performs no acquisition or interpretation."""

    def __init__(
        self,
        backend: ArtifactBackend,
        cipher: EnvelopeCipher,
        audit: DurableAuditSink,
        verifier: GovernanceProjectionVerifier,
        service_id: str,
        clock: Callable[[], datetime] | None = None,
    ):
        if cipher.algorithm != AES_256_GCM:
            raise ArtifactStorageError("ENCRYPTION_UNAVAILABLE")
        if cipher.key_authority_id in ("", "SEPARATE_DEVELOPMENT_KEY"):
            raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")
        if backend.storage_identifier == "LOCAL_CONTENT_ADDRESSED_DIRECTORY":
            raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")
        self.backend = backend
        self.cipher = cipher
        self.audit = audit
        self.verifier = verifier
        self.service_id = service_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def admit(self, request: AdmissionRequest, operation_id: str) -> AdmissionResult:
        identity = ""
        try:
            self._verify_admission(request)
            raw = bytes(request.artifact.raw_bytes)
            if not request.artifact.media_type:
                raise ArtifactStorageError("MEDIA_TYPE_MISMATCH")
            digest = hashlib.sha256(raw).hexdigest()
            if request.artifact.sha256.lower() != digest:
                raise ArtifactStorageError("IDENTITY_MISMATCH")
            if len(raw) > request.quota.maximum_artifact_bytes:
                raise ArtifactStorageError("QUOTA_EXCEEDED")
            if self.backend.total_plaintext_bytes() + len(raw) > request.quota.maximum_total_bytes:
                raise ArtifactStorageError("QUOTA_EXCEEDED")
            identity = f"era-artifact:sha256:{digest}"
            governance = GovernanceMetadata(
                request.governance_profile.profile_id,
                request.governance_profile.profile_version,
                request.governance_profile.profile_sha256.upper(),
                request.retention.retention_class_id,
                request.retention.retention_policy_version,
                request.retention.authority_reference,
                request.retention.retain_until,
                request.retention.legal_basis,
                request.retention.projection_digest,
                request.quota.quota_id,
                request.quota.projection_digest,
            )
            record = ArtifactRecord(
                identity, digest, request.artifact.media_type, len(raw), governance,
                self._now(), ADMITTED, NOT_QUARANTINED, VERIFIED,
            )
            envelope = self.cipher.encrypt(raw, self._authenticated_metadata(record))
            created = self.backend.write_once(record, envelope)
            persisted_record, persisted_envelope = self.backend.read(identity)
            persisted_raw = self.cipher.decrypt(
                persisted_envelope, self._authenticated_metadata(persisted_record),
            )
            same_stored_claim = (
                persisted_record.artifact_identity == record.artifact_identity
                and persisted_record.sha256 == record.sha256
                and persisted_record.media_type == record.media_type
                and persisted_record.byte_length == record.byte_length
                and persisted_record.governance == record.governance
                and persisted_record.admission_decision == record.admission_decision
                and persisted_record.quarantine_status == record.quarantine_status
                and persisted_record.integrity_status == record.integrity_status
            )
            if not same_stored_claim or persisted_raw != raw:
                raise ArtifactStorageError("CORRUPT")
            self.backend.append_observation(request.observation_id, record)
            self._audit(
                "ADMISSION_RESULT", operation_id, request.admission_authority.subject_id,
                "ARTIFACT_ADMISSION", identity, "SUCCEEDED", "",
            )
            return AdmissionResult(persisted_record, request.observation_id, created)
        except ArtifactStorageError as exc:
            if identity and exc.reason_code in {
                "CORRUPT", "IDENTITY_MISMATCH", "LENGTH_MISMATCH", "MEDIA_TYPE_MISMATCH",
            }:
                self.backend.quarantine(identity, operation_id, exc.reason_code, self._now())
            self._audit(
                "ADMISSION_RESULT", operation_id,
                request.admission_authority.subject_id if request.admission_authority else "",
                "ARTIFACT_ADMISSION", "", "FAILED", exc.reason_code,
            )
            raise

    def recover(
        self,
        artifact_identity: str,
        authority: AuthorityProjection,
        purpose_code: str,
        operation_id: str,
    ) -> RecoveredArtifact:
        self._audit("ACCESS_INTENT", operation_id, authority.subject_id, purpose_code, artifact_identity, "OPEN", "")
        try:
            self._verify_read(authority, purpose_code)
            if self.backend.is_quarantined(artifact_identity):
                raise ArtifactStorageError("QUARANTINED")
            record, envelope = self.backend.read(artifact_identity)
            raw = self.cipher.decrypt(envelope, self._authenticated_metadata(record))
            observed_digest = hashlib.sha256(raw).hexdigest()
            observed_media_type = record.media_type
            reason = ""
            if record.artifact_identity != artifact_identity or record.sha256 != observed_digest:
                reason = "IDENTITY_MISMATCH"
            elif record.byte_length != len(raw):
                reason = "LENGTH_MISMATCH"
            elif not record.media_type:
                reason = "MEDIA_TYPE_MISMATCH"
            if reason:
                raise ArtifactStorageError(reason)
            verification = IntegrityVerification(
                VERIFIED, record.sha256, observed_digest, record.byte_length, len(raw),
                record.media_type, observed_media_type,
            )
            self._audit("ACCESS_RESULT", operation_id, authority.subject_id, purpose_code, artifact_identity, "SUCCEEDED", "")
            return RecoveredArtifact(
                record.artifact_identity, raw, record.sha256, record.media_type,
                record.byte_length, record.governance, verification,
            )
        except ArtifactStorageError as exc:
            if exc.reason_code in {"CORRUPT", "IDENTITY_MISMATCH", "LENGTH_MISMATCH", "MEDIA_TYPE_MISMATCH"}:
                self.backend.quarantine(artifact_identity, operation_id, exc.reason_code, self._now())
            self._audit("ACCESS_RESULT", operation_id, authority.subject_id, purpose_code, artifact_identity, "FAILED", exc.reason_code)
            raise

    def _verify_admission(self, request: AdmissionRequest) -> None:
        verify_production_profile(request.governance_profile)
        if not self.verifier.verify_authority(request.admission_authority):
            raise ArtifactStorageError("ADMISSION_AUTHORITY_INVALID")
        if set(request.admission_authority.permissions) != {ARTIFACT_WRITE}:
            raise ArtifactStorageError("ADMISSION_AUTHORITY_INVALID")
        if request.admission_authority.environment != PRODUCTION_ENVIRONMENT:
            raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")
        if not self.verifier.verify_retention(request.retention):
            raise ArtifactStorageError("RETENTION_PROJECTION_UNTRUSTED")
        if not all((request.retention.retention_class_id, request.retention.retain_until, request.retention.legal_basis)):
            raise ArtifactStorageError("RETENTION_PROJECTION_REQUIRED")
        try:
            retain_until = datetime.fromisoformat(request.retention.retain_until)
        except ValueError as exc:
            raise ArtifactStorageError("RETENTION_PROJECTION_UNTRUSTED") from exc
        if retain_until.tzinfo is None or retain_until <= self.clock().astimezone(timezone.utc):
            raise ArtifactStorageError("RETENTION_PROJECTION_UNTRUSTED")
        if request.retention.environment != PRODUCTION_ENVIRONMENT or request.retention.retention_class_id == "DEVELOPMENT":
            raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")
        if not self.verifier.verify_quota(request.quota):
            raise ArtifactStorageError("QUOTA_PROJECTION_REQUIRED")
        if request.quota.environment != PRODUCTION_ENVIRONMENT:
            raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")
        if request.quota.storage_identifier != self.backend.storage_identifier:
            raise ArtifactStorageError("QUOTA_PROJECTION_REQUIRED")
        if request.quota.maximum_artifact_bytes <= 0 or request.quota.maximum_total_bytes <= 0:
            raise ArtifactStorageError("QUOTA_PROJECTION_REQUIRED")
        if self.cipher.key_authority_id == "SEPARATE_DEVELOPMENT_KEY" or request.governance_profile.profile_id == DEVELOPMENT_PROFILE_ID:
            raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")

    def _verify_read(self, authority: AuthorityProjection, purpose_code: str) -> None:
        if not self.verifier.verify_authority(authority) or set(authority.permissions) != {ARTIFACT_READ}:
            raise ArtifactStorageError("ACCESS_DENIED")
        if authority.environment != PRODUCTION_ENVIRONMENT:
            raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")
        if purpose_code not in authority.purpose_codes:
            raise ArtifactStorageError("PURPOSE_NOT_AUTHORIZED")

    @staticmethod
    def _authenticated_metadata(record: ArtifactRecord) -> bytes:
        value = {
            "artifact_identity": record.artifact_identity,
            "sha256": record.sha256,
            "byte_length": record.byte_length,
            "media_type": record.media_type,
            "governance_profile_id": record.governance.profile_id,
            "governance_profile_version": record.governance.profile_version,
            "governance_profile_sha256": record.governance.profile_sha256,
        }
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _audit(self, event_type, operation_id, requester_id, purpose_code, identity, outcome, reason):
        try:
            self.audit.append(AuditEvent(
                event_type, operation_id, requester_id, self.service_id, purpose_code,
                identity, outcome, reason, self._now(),
            ))
        except Exception as exc:
            raise ArtifactStorageError("AUDIT_UNAVAILABLE") from exc

    def _now(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat()
