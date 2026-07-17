"""SDR-002: deterministic canonical source identity and declared-alias resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Callable


RESOLVED = "RESOLVED"
UNRESOLVED = "UNRESOLVED"
AMBIGUOUS = "AMBIGUOUS"
INVALID_INPUT = "INVALID_INPUT"

EXACT_CANONICAL_MATCH = "EXACT_CANONICAL_MATCH"
DECLARED_ALIAS_MATCH = "DECLARED_ALIAS_MATCH"
UNKNOWN_ALIAS = "UNKNOWN_ALIAS"
AMBIGUOUS_ALIAS = "AMBIGUOUS_ALIAS"
INVALID_REFERENCE = "INVALID_REFERENCE"
JURISDICTION_MISMATCH = "JURISDICTION_MISMATCH"
PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
RECORD_TYPE_MISMATCH = "RECORD_TYPE_MISMATCH"
SOURCE_KIND_MISMATCH = "SOURCE_KIND_MISMATCH"

RESOLUTION_STATUSES = frozenset({RESOLVED, UNRESOLVED, AMBIGUOUS, INVALID_INPUT})
REASON_CODES = frozenset({
    EXACT_CANONICAL_MATCH, DECLARED_ALIAS_MATCH, UNKNOWN_ALIAS, AMBIGUOUS_ALIAS,
    INVALID_REFERENCE, JURISDICTION_MISMATCH, PROVIDER_MISMATCH,
    RECORD_TYPE_MISMATCH, SOURCE_KIND_MISMATCH,
})
CANONICAL_ID_VERSION = "1"


def _semantic_token(value: str) -> str:
    value = str(value or "").strip().lower()
    if not value or not value.isascii():
        return ""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value)).strip("_")


def _jurisdiction_token(value: str) -> str:
    value = str(value or "").strip().lower()
    if not value or not value.isascii():
        return ""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-")


def normalize_alias(value: str) -> str:
    """Exact normalization only: case and punctuation, never similarity."""
    return _semantic_token(value)


@dataclass(frozen=True)
class CanonicalSourceDescriptor:
    jurisdiction: str
    provider_id: str
    source_kind: str
    record_type: str
    declared_capabilities: tuple[str, ...] = ()

    def canonical_source_id(self) -> str:
        jurisdiction = _jurisdiction_token(self.jurisdiction)
        provider = _semantic_token(self.provider_id)
        source_kind = _semantic_token(self.source_kind)
        record_type = _semantic_token(self.record_type)
        if not all((jurisdiction, provider, source_kind, record_type)):
            return ""
        return f"src:{jurisdiction}:{provider}:{source_kind}:{record_type}"


@dataclass(frozen=True)
class DeclaredSourceAlias:
    alias: str
    target: CanonicalSourceDescriptor


@dataclass(frozen=True)
class SourceIdentityRequest:
    input_reference: str
    descriptor: CanonicalSourceDescriptor
    catalog_version: str
    provider_local_record_key: str = ""


@dataclass(frozen=True)
class SourceIdentityResolution:
    input_reference: str
    normalized_reference: str
    canonical_source_id: str | None
    status: str
    reason_code: str
    matched_alias: str | None
    canonical_id_version: str
    catalog_version: str
    evaluated_at: str


class SourceIdentityResolver:
    """Resolve only exact canonical IDs and explicitly declared aliases."""

    def __init__(
        self,
        aliases: tuple[DeclaredSourceAlias, ...] = (),
        clock: Callable[[], datetime] | None = None,
    ):
        self.aliases = tuple(sorted(aliases, key=lambda item: (
            normalize_alias(item.alias), item.target.canonical_source_id()
        )))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(self, request: SourceIdentityRequest) -> SourceIdentityResolution:
        evaluated_at = self.clock().astimezone(timezone.utc).isoformat()
        reference = str(request.input_reference or "").strip()
        normalized = normalize_alias(reference)
        canonical_id = request.descriptor.canonical_source_id()
        if not reference or not normalized or not canonical_id or not request.catalog_version:
            return self._result(request, normalized, None, INVALID_INPUT, INVALID_REFERENCE, None, evaluated_at)

        if reference.lower() == canonical_id:
            return self._result(
                request, normalized, canonical_id, RESOLVED,
                EXACT_CANONICAL_MATCH, None, evaluated_at,
            )

        matches = tuple(item for item in self.aliases if normalize_alias(item.alias) == normalized)
        if not matches:
            return self._result(request, normalized, None, UNRESOLVED, UNKNOWN_ALIAS, None, evaluated_at)

        expected_id = canonical_id
        matching_targets = tuple(item for item in matches if item.target.canonical_source_id() == expected_id)
        target_ids = {item.target.canonical_source_id() for item in matches}
        if len(target_ids) > 1:
            return self._result(request, normalized, None, AMBIGUOUS, AMBIGUOUS_ALIAS, None, evaluated_at)
        if matching_targets:
            return self._result(
                request, normalized, expected_id, RESOLVED, DECLARED_ALIAS_MATCH,
                matching_targets[0].alias, evaluated_at,
            )

        target = matches[0].target
        reason = self._mismatch_reason(request.descriptor, target)
        return self._result(request, normalized, None, UNRESOLVED, reason, None, evaluated_at)

    @staticmethod
    def _mismatch_reason(expected, actual):
        if _jurisdiction_token(expected.jurisdiction) != _jurisdiction_token(actual.jurisdiction):
            return JURISDICTION_MISMATCH
        if _semantic_token(expected.provider_id) != _semantic_token(actual.provider_id):
            return PROVIDER_MISMATCH
        if _semantic_token(expected.record_type) != _semantic_token(actual.record_type):
            return RECORD_TYPE_MISMATCH
        return SOURCE_KIND_MISMATCH

    @staticmethod
    def _result(request, normalized, canonical_id, status, reason, alias, evaluated_at):
        return SourceIdentityResolution(
            input_reference=request.input_reference,
            normalized_reference=normalized,
            canonical_source_id=canonical_id,
            status=status,
            reason_code=reason,
            matched_alias=alias,
            canonical_id_version=CANONICAL_ID_VERSION,
            catalog_version=request.catalog_version,
            evaluated_at=evaluated_at,
        )

