"""Bounded append-only filesystem reference ports for ART-001 verification."""

from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
import json
import os
from pathlib import Path

from .errors import ArtifactStorageError
from .models import ArtifactRecord, AuditEvent, EncryptedEnvelope, GovernanceMetadata


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ArtifactStorageError("IMMUTABLE_OBJECT_EXISTS") from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


class AppendOnlyFilesystemBackend:
    """Local reference backend; deployment must supply a production object store."""

    def __init__(self, root: Path, storage_identifier: str):
        self.root = Path(root)
        self.storage_identifier = storage_identifier

    @staticmethod
    def _digest(identity: str) -> str:
        prefix = "era-artifact:sha256:"
        if not identity.startswith(prefix):
            raise ArtifactStorageError("IDENTITY_MISMATCH")
        digest = identity[len(prefix):]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ArtifactStorageError("IDENTITY_MISMATCH")
        return digest

    def _base(self, identity: str) -> Path:
        digest = self._digest(identity)
        return self.root / "objects" / digest[:2] / digest

    def total_plaintext_bytes(self) -> int:
        total = 0
        for path in (self.root / "objects").glob("*/*.metadata.json"):
            total += int(json.loads(path.read_text(encoding="utf-8"))["byte_length"])
        return total

    def write_once(self, record: ArtifactRecord, envelope: EncryptedEnvelope) -> bool:
        base = self._base(record.artifact_identity)
        metadata_path = base.with_suffix(".metadata.json")
        envelope_path = base.with_suffix(".envelope.json")
        if metadata_path.exists() or envelope_path.exists():
            existing, _ = self.read(record.artifact_identity)
            same_claim = (
                existing.artifact_identity == record.artifact_identity
                and existing.sha256 == record.sha256
                and existing.media_type == record.media_type
                and existing.byte_length == record.byte_length
                and existing.governance == record.governance
                and existing.admission_decision == record.admission_decision
                and existing.quarantine_status == record.quarantine_status
                and existing.integrity_status == record.integrity_status
            )
            if not same_claim:
                raise ArtifactStorageError("IDENTITY_MISMATCH")
            return False
        envelope_value = {
            "algorithm": envelope.algorithm,
            "nonce": base64.b64encode(envelope.nonce).decode("ascii"),
            "ciphertext": base64.b64encode(envelope.ciphertext).decode("ascii"),
            "wrapped_data_key": base64.b64encode(envelope.wrapped_data_key).decode("ascii"),
            "key_authority_id": envelope.key_authority_id,
        }
        _write_new(envelope_path, _json_bytes(envelope_value))
        try:
            _write_new(metadata_path, _json_bytes(asdict(record)))
        except Exception:
            try:
                envelope_path.unlink()
            except OSError:
                pass
            raise
        return True

    def append_observation(self, observation_id: str, record: ArtifactRecord) -> None:
        if not observation_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in observation_id):
            raise ArtifactStorageError("OBSERVATION_ID_INVALID")
        path = self.root / "observations" / f"{observation_id}.json"
        _write_new(path, _json_bytes({
            "observation_id": observation_id,
            "artifact_identity": record.artifact_identity,
            "admission_timestamp": record.admission_timestamp,
            "governance_profile_sha256": record.governance.profile_sha256,
        }))

    def read(self, artifact_identity: str) -> tuple[ArtifactRecord, EncryptedEnvelope]:
        base = self._base(artifact_identity)
        try:
            metadata = json.loads(base.with_suffix(".metadata.json").read_text(encoding="utf-8"))
            envelope = json.loads(base.with_suffix(".envelope.json").read_text(encoding="utf-8"))
            governance = GovernanceMetadata(**metadata.pop("governance"))
            record = ArtifactRecord(governance=governance, **metadata)
            sealed = EncryptedEnvelope(
                envelope["algorithm"],
                base64.b64decode(envelope["nonce"], validate=True),
                base64.b64decode(envelope["ciphertext"], validate=True),
                base64.b64decode(envelope["wrapped_data_key"], validate=True),
                envelope["key_authority_id"],
            )
            return record, sealed
        except FileNotFoundError as exc:
            raise ArtifactStorageError("NOT_FOUND") from exc
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise ArtifactStorageError("CORRUPT") from exc

    def quarantine(self, artifact_identity: str, operation_id: str, reason_code: str, observed_at: str) -> None:
        digest = self._digest(artifact_identity)
        path = self.root / "quarantine" / digest / f"{operation_id}.json"
        if not path.exists():
            _write_new(path, _json_bytes({
                "artifact_identity": artifact_identity,
                "operation_id": operation_id,
                "reason_code": reason_code,
                "observed_at": observed_at,
            }))

    def is_quarantined(self, artifact_identity: str) -> bool:
        digest = self._digest(artifact_identity)
        return any((self.root / "quarantine" / digest).glob("*.json"))


class AppendOnlyFileAuditSink:
    def __init__(self, root: Path):
        self.root = Path(root)

    def append(self, event: AuditEvent) -> None:
        ordinal = {"ACCESS_INTENT": "01", "ACCESS_RESULT": "02", "ADMISSION_RESULT": "03"}.get(event.event_type, "99")
        path = self.root / f"{event.operation_id}.{ordinal}.{event.event_type}.json"
        _write_new(path, _json_bytes(asdict(event)))

    def events_for(self, operation_id: str) -> tuple[AuditEvent, ...]:
        events = []
        for path in sorted(self.root.glob(f"{operation_id}.*.json")):
            events.append(AuditEvent(**json.loads(path.read_text(encoding="utf-8"))))
        return tuple(events)
