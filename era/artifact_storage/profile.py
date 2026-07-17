"""Frozen ART-GOV-001 production profile identity and admission checks."""

from __future__ import annotations

from .errors import ArtifactStorageError
from .models import GovernanceProfilePin


PRODUCTION_PROFILE = GovernanceProfilePin(
    "ERA-ARTIFACT-PRODUCTION-1",
    "1",
    "B3D3F445CAC5D43F998C349E00D2F5BE9B9ADD09CF1DB6DA270C494309663303",
)
DEVELOPMENT_PROFILE_ID = "ERA-ARTIFACT-DEVELOPMENT-1"
PRODUCTION_ENVIRONMENT = "PRODUCTION"


def verify_production_profile(pin: GovernanceProfilePin) -> None:
    if pin.profile_id == DEVELOPMENT_PROFILE_ID:
        raise ArtifactStorageError("DEVELOPMENT_AUTHORITY_PROHIBITED")
    if not all((pin.profile_id, pin.profile_version, pin.profile_sha256)):
        raise ArtifactStorageError("GOVERNANCE_PROFILE_REQUIRED")
    if (pin.profile_id, pin.profile_version) != (
        PRODUCTION_PROFILE.profile_id,
        PRODUCTION_PROFILE.profile_version,
    ):
        raise ArtifactStorageError("GOVERNANCE_PROFILE_UNTRUSTED")
    if pin.profile_sha256.upper() != PRODUCTION_PROFILE.profile_sha256:
        raise ArtifactStorageError("GOVERNANCE_PROFILE_DIGEST_MISMATCH")

