"""EIA-WIRE-001 validated package-member and artifact-identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from era.discovery.acquisition_package import VALID, ValidatedAcquisitionPackage


SHA256 = "SHA-256"
_FACTORY_TOKEN = object()


@dataclass(frozen=True)
class ArtifactIdentity:
    algorithm: str
    digest: str
    byte_length: int
    media_type: str
    content_uri: str

    @classmethod
    def from_artifact(cls, artifact):
        digest = hashlib.sha256(artifact.raw_bytes).hexdigest()
        if digest != artifact.sha256 or not artifact.media_type:
            raise ValueError("INVALID_ARTIFACT_IDENTITY")
        return cls(SHA256, digest, len(artifact.raw_bytes), artifact.media_type,
                   f"era-artifact:sha256:{digest}")

    def is_valid(self):
        return (
            self.algorithm == SHA256 and len(self.digest) == 64
            and all(character in "0123456789abcdef" for character in self.digest)
            and self.byte_length >= 0 and bool(self.media_type)
            and self.content_uri == f"era-artifact:sha256:{self.digest}"
        )


@dataclass(frozen=True, init=False)
class ValidatedArtifactMember:
    package_id: str
    package_version: str
    execution_id: str
    plan_step_id: str
    step_sequence: int
    artifact_sha256: str
    provider_id: str
    canonical_source_id: str
    validation_status: str
    artifact: object
    artifact_identity: ArtifactIdentity

    def __init__(self, package_id, package_version, execution_id, plan_step_id,
                 step_sequence, artifact_sha256, provider_id,
                 canonical_source_id, validation_status, artifact,
                 artifact_identity, *, _token=None):
        if _token is not _FACTORY_TOKEN:
            raise TypeError("VALIDATED_MEMBER_FACTORY_REQUIRED")
        for name, value in locals().copy().items():
            if name not in {"self", "_token"}:
                object.__setattr__(self, name, value)

    @classmethod
    def from_package(cls, package, step):
        if not isinstance(package, ValidatedAcquisitionPackage):
            raise ValueError("VALIDATED_PACKAGE_REQUIRED")
        if not any(item is step for item in package.steps):
            raise ValueError("STEP_NOT_PACKAGE_MEMBER")
        if step.validation_status != VALID or step.artifact is None:
            raise ValueError("PACKAGE_MEMBER_NOT_VALID")
        artifact = step.artifact
        identity = ArtifactIdentity.from_artifact(artifact)
        if not all((package.package_id, package.package_identity_version,
                    package.execution_id, step.plan_step_id, step.provider_id,
                    step.canonical_source_id)):
            raise ValueError("INCOMPLETE_MEMBERSHIP_IDENTITY")
        if (artifact.sha256 != identity.digest
                or artifact.provider_id != step.provider_id
                or artifact.canonical_source_id != step.canonical_source_id):
            raise ValueError("MEMBERSHIP_IDENTITY_MISMATCH")
        return cls(
            package.package_id, package.package_identity_version,
            package.execution_id, step.plan_step_id, step.sequence,
            artifact.sha256, step.provider_id, step.canonical_source_id,
            step.validation_status, artifact, identity, _token=_FACTORY_TOKEN,
        )

    def is_valid(self):
        return (
            self.validation_status == VALID
            and self.artifact_identity.is_valid()
            and self.artifact_sha256 == self.artifact_identity.digest
            and hashlib.sha256(self.artifact.raw_bytes).hexdigest() == self.artifact_sha256
            and self.artifact_identity.byte_length == len(self.artifact.raw_bytes)
            and self.artifact_identity.media_type == self.artifact.media_type
            and self.artifact.provider_id == self.provider_id
            and self.artifact.canonical_source_id == self.canonical_source_id
            and all((self.package_id, self.package_version, self.execution_id,
                     self.plan_step_id, self.provider_id, self.canonical_source_id))
        )


def validated_members(package):
    """Return valid members in package-step order; invalid steps never become members."""
    return tuple(
        ValidatedArtifactMember.from_package(package, step)
        for step in sorted(package.steps, key=lambda item: item.sequence)
        if step.validation_status == VALID
    )
