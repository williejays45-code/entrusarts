"""ART-001 governed admission, exact recovery, quarantine, and boundary verification."""

from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import shutil
from contextlib import contextmanager

from era.acquisition_execution.executor import RawArtifact
from era.artifact_storage import (
    ARTIFACT_READ, ARTIFACT_WRITE, AdmissionRequest,
    Aes256GcmEnvelopeCipher, AppendOnlyFileAuditSink,
    AppendOnlyFilesystemBackend, ArtifactStorageAuthority,
    ArtifactStorageError, AuthorityProjection, PRODUCTION_PROFILE,
    QuotaProjection, RetentionProjection,
)


NOW = datetime(2026, 7, 13, 18, 0, tzinfo=timezone.utc)
PAYLOAD = b"exact historical acquisition bytes\x00\xff"
STORAGE_ID = "ART001-REFERENCE-PRIVATE-STORE"


class TrustedVerifier:
    def verify_authority(self, projection):
        return projection.projection_digest in {"trusted-write", "trusted-read"}

    def verify_retention(self, projection):
        return projection.projection_digest == "trusted-retention"

    def verify_quota(self, projection):
        return projection.projection_digest == "trusted-quota"


class TestKeyAuthority:
    key_authority_id = "TEST-EXTERNAL-KMS"
    key = b"K" * 32

    def generate_data_key(self):
        return self.key, b"wrapped-test-key"

    def unwrap_data_key(self, wrapped_data_key):
        if wrapped_data_key != b"wrapped-test-key":
            raise ValueError("bad wrapped key")
        return self.key


class TestAead:
    """Instrumented AEAD stand-in; production adapter still requires cryptography AESGCM."""

    def __init__(self, key):
        self.key = key

    def _stream(self, nonce, length):
        stream = b""
        counter = 0
        while len(stream) < length:
            stream += hashlib.sha256(self.key + nonce + counter.to_bytes(4, "big")).digest()
            counter += 1
        return stream[:length]

    def encrypt(self, nonce, plaintext, aad):
        body = bytes(a ^ b for a, b in zip(plaintext, self._stream(nonce, len(plaintext))))
        tag = hmac.new(self.key, nonce + aad + body, hashlib.sha256).digest()
        return body + tag

    def decrypt(self, nonce, ciphertext, aad):
        body, tag = ciphertext[:-32], ciphertext[-32:]
        expected = hmac.new(self.key, nonce + aad + body, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("authentication failed")
        return bytes(a ^ b for a, b in zip(body, self._stream(nonce, len(body))))


class InstrumentedAes256GcmCipher(Aes256GcmEnvelopeCipher):
    @staticmethod
    def _aesgcm():
        return TestAead


def artifact():
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    return RawArtifact(
        PAYLOAD, "application/octet-stream", digest, "src:tx-dallas:a:artifact",
        "A", "LOCAL-1", NOW.isoformat(), (("transport", "https"),),
    )


def write_authority(digest="trusted-write"):
    return AuthorityProjection(
        "artifact-admission-service", "ERA_AUTH", (ARTIFACT_WRITE,), (),
        "PRODUCTION", digest,
    )


def read_authority():
    return AuthorityProjection(
        "authorized-requester", "ERA_AUTH", (ARTIFACT_READ,),
        ("HISTORICAL_RECOVERY",), "PRODUCTION", "trusted-read",
    )


def retention(digest="trusted-retention"):
    return RetentionProjection(
        "ERA-RETAIN-2026", "1", "ERA_RETENTION_AUTHORITY",
        "2036-07-13T00:00:00+00:00", "ERA_OPERATIONAL_RECORD",
        "PRODUCTION", digest,
    )


def quota(max_artifact=1024, digest="trusted-quota"):
    return QuotaProjection(
        "ERA-QUOTA-1", "ERA_QUOTA_AUTHORITY", max_artifact, 4096, 0,
        STORAGE_ID, "PRODUCTION", digest,
    )


def request(**changes):
    value = AdmissionRequest(
        artifact(), "OBS-001", PRODUCTION_PROFILE, write_authority(), retention(), quota(),
    )
    return replace(value, **changes)


def reason(callable_):
    try:
        callable_()
    except ArtifactStorageError as exc:
        return exc.reason_code
    return "NO_ERROR"


@contextmanager
def verification_directory():
    root = Path(__file__).parent / "verification_runtime"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_checks():
    checks = {}
    with verification_directory() as root:
        backend = AppendOnlyFilesystemBackend(root / "store", STORAGE_ID)
        audit = AppendOnlyFileAuditSink(root / "audit")
        service = ArtifactStorageAuthority(
            backend, InstrumentedAes256GcmCipher(TestKeyAuthority()), audit,
            TrustedVerifier(), "ERA_ARTIFACT_RESOLVER", clock=lambda: NOW,
        )

        result = service.admit(request(), "ADMIT-001")
        record = result.artifact
        checks["governance_profile_enforced"] = record.governance.profile_id == PRODUCTION_PROFILE.profile_id
        checks["profile_version_pinned"] = record.governance.profile_version == "1"
        checks["profile_digest_pinned"] = record.governance.profile_sha256 == PRODUCTION_PROFILE.profile_sha256
        checks["immutable_content_identity"] = record.artifact_identity == f"era-artifact:sha256:{artifact().sha256}"
        checks["identity_metadata_complete"] = (
            record.sha256 == artifact().sha256 and record.media_type == "application/octet-stream"
            and record.byte_length == len(PAYLOAD) and record.admission_decision == "ADMITTED"
            and record.quarantine_status == "NOT_QUARANTINED" and record.integrity_status == "VERIFIED"
        )
        checks["durable_files_written"] = len(tuple((root / "store" / "objects").glob("*/*"))) == 2
        checks["observation_independent"] = (root / "store" / "observations" / "OBS-001.json").exists()
        duplicate = service.admit(request(observation_id="OBS-002"), "ADMIT-002")
        checks["physical_deduplication_only"] = (
            not duplicate.physical_content_created
            and duplicate.artifact.artifact_identity == record.artifact_identity
            and (root / "store" / "observations" / "OBS-002.json").exists()
            and len(tuple((root / "store" / "observations").glob("*.json"))) == 2
        )

        recovered = service.recover(
            record.artifact_identity, read_authority(), "HISTORICAL_RECOVERY", "READ-001",
        )
        checks["exact_historical_bytes"] = recovered.original_bytes == PAYLOAD
        checks["recovery_contract_complete"] = (
            recovered.artifact_identity == record.artifact_identity
            and recovered.sha256 == record.sha256
            and recovered.byte_length == len(PAYLOAD)
            and recovered.media_type == record.media_type
            and recovered.governance_metadata.profile_sha256 == PRODUCTION_PROFILE.profile_sha256
            and recovered.integrity_verification.status == "VERIFIED"
        )
        recovered_again = service.recover(
            record.artifact_identity, read_authority(), "HISTORICAL_RECOVERY", "READ-002",
        )
        checks["deterministic_recovery"] = recovered_again == recovered
        checks["restart_survival"] = ArtifactStorageAuthority(
            AppendOnlyFilesystemBackend(root / "store", STORAGE_ID),
            InstrumentedAes256GcmCipher(TestKeyAuthority()),
            AppendOnlyFileAuditSink(root / "audit"), TrustedVerifier(),
            "ERA_ARTIFACT_RESOLVER", clock=lambda: NOW,
        ).recover(record.artifact_identity, read_authority(), "HISTORICAL_RECOVERY", "READ-003") == recovered
        checks["access_audit_order"] = tuple(
            event.event_type for event in audit.events_for("READ-001")
        ) == ("ACCESS_INTENT", "ACCESS_RESULT")

        rejected_profile = replace(PRODUCTION_PROFILE, profile_sha256="0" * 64)
        checks["wrong_profile_rejected"] = reason(
            lambda: service.admit(request(governance_profile=rejected_profile, observation_id="OBS-BAD-1"), "ADMIT-BAD-1")
        ) == "GOVERNANCE_PROFILE_DIGEST_MISMATCH"
        checks["untrusted_authority_rejected"] = reason(
            lambda: service.admit(request(admission_authority=write_authority("caller-created"), observation_id="OBS-BAD-2"), "ADMIT-BAD-2")
        ) == "ADMISSION_AUTHORITY_INVALID"
        checks["untrusted_retention_rejected"] = reason(
            lambda: service.admit(request(retention=retention("caller-created"), observation_id="OBS-BAD-3"), "ADMIT-BAD-3")
        ) == "RETENTION_PROJECTION_UNTRUSTED"
        checks["quota_rejected_before_write"] = reason(
            lambda: service.admit(request(quota=quota(1), observation_id="OBS-BAD-4"), "ADMIT-BAD-4")
        ) == "QUOTA_EXCEEDED"
        development = replace(PRODUCTION_PROFILE, profile_id="ERA-ARTIFACT-DEVELOPMENT-1")
        checks["development_profile_rejected"] = reason(
            lambda: service.admit(request(governance_profile=development, observation_id="OBS-BAD-5"), "ADMIT-BAD-5")
        ) == "DEVELOPMENT_AUTHORITY_PROHIBITED"
        checks["rejections_create_no_objects"] = len(tuple((root / "store" / "objects").glob("*/*"))) == 2

        envelope_path = next((root / "store" / "objects").glob("*/*.envelope.json"))
        sealed = json.loads(envelope_path.read_text(encoding="utf-8"))
        ciphertext = bytearray(base64.b64decode(sealed["ciphertext"]))
        ciphertext[0] ^= 1
        sealed["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
        envelope_path.write_text(json.dumps(sealed, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        checks["corruption_fails_closed"] = reason(
            lambda: service.recover(record.artifact_identity, read_authority(), "HISTORICAL_RECOVERY", "READ-CORRUPT")
        ) == "CORRUPT"
        checks["corruption_quarantined"] = backend.is_quarantined(record.artifact_identity)
        corrupt_events = audit.events_for("READ-CORRUPT")
        checks["failure_audit_durable"] = (
            tuple(event.event_type for event in corrupt_events) == ("ACCESS_INTENT", "ACCESS_RESULT")
            and corrupt_events[-1].outcome == "FAILED" and corrupt_events[-1].reason_code == "CORRUPT"
        )
        checks["quarantine_never_repairs"] = reason(
            lambda: service.recover(record.artifact_identity, read_authority(), "HISTORICAL_RECOVERY", "READ-QUARANTINED")
        ) == "QUARANTINED"

        try:
            record.sha256 = "changed"
            frozen = False
        except FrozenInstanceError:
            frozen = True
        checks["public_models_immutable"] = frozen

    source_root = Path(__file__).parent
    production_source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in source_root.glob("*.py") if not path.name.startswith("verify_")
    )
    checks["no_evidence_or_reasoning"] = all(
        term not in production_source
        for term in ("canonicalevidence", "evidencerecord", "reasoning_engine", "recommendationengine", "confidence")
    )
    checks["no_provider_or_ax_invocation"] = all(
        term not in production_source
        for term in ("provider_id", "network_client", ".acquire(", "acquisitionexecutor", "parse(")
    )
    checks["resolver_non_modification"] = all(
        term not in production_source for term in ("repair", "reacquire", "regenerate", "normalize")
    )
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"ART-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
