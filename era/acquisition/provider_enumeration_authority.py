"""PER-001: stateless provider eligibility derivation seeded only by SRR."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.connector_enums import ConnectorStatus


NOT_ACTIVE = "NOT_ACTIVE"
CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
JURISDICTION_UNSUPPORTED = "JURISDICTION_UNSUPPORTED"
RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
HEALTH_UNAVAILABLE = "HEALTH_UNAVAILABLE"
PROVIDER_NOT_REGISTERED = "PROVIDER_NOT_REGISTERED"

EXCLUSION_REASONS = frozenset({
    NOT_ACTIVE,
    CAPABILITY_MISMATCH,
    JURISDICTION_UNSUPPORTED,
    RUNTIME_UNAVAILABLE,
    HEALTH_UNAVAILABLE,
    PROVIDER_NOT_REGISTERED,
})


@dataclass(frozen=True)
class ProviderEnumerationRequest:
    state: str
    county: str
    required_capabilities: tuple[str, ...] = ()
    requested_provider_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderExclusion:
    provider_id: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class ProviderEligibilityProjection:
    provider_id: str
    connector: Any
    provider: Any
    health: ProviderHealth


@dataclass(frozen=True)
class ProviderEnumerationDetail:
    seeded: tuple[str, ...]
    geographic_mappings: tuple[str, ...]
    after_lifecycle: tuple[str, ...]
    after_capability: tuple[str, ...]
    after_geography: tuple[str, ...]
    after_runtime: tuple[str, ...]
    after_health: tuple[str, ...]


@dataclass(frozen=True)
class ProviderEnumerationResult:
    eligible: tuple[ProviderEligibilityProjection, ...]
    exclusions: tuple[ProviderExclusion, ...]
    detail: ProviderEnumerationDetail
    evaluated_at: str = ""

    def get(self, provider_id: str):
        return next((item for item in self.eligible if item.provider_id == provider_id), None)

    def exclusion_for(self, provider_id: str):
        return next((item for item in self.exclusions if item.provider_id == provider_id), None)


class ProviderEnumerationAuthority:
    """Combine existing facts without owning or persisting any of them."""

    def __init__(
        self,
        source_registry,
        jurisdiction_registry,
        runtime_resolver: Callable[[str], Any],
        health_evaluator: Callable[[str, Any], ProviderHealth],
        clock: Callable[[], datetime] | None = None,
    ):
        self.source_registry = source_registry
        self.jurisdiction_registry = jurisdiction_registry
        self.runtime_resolver = runtime_resolver
        self.health_evaluator = health_evaluator
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def enumerate(self, request: ProviderEnumerationRequest) -> ProviderEnumerationResult:
        connectors = {item.connector_id: item for item in self.source_registry.list_connectors()}
        requested = tuple(sorted(set(request.requested_provider_ids)))
        seeded = tuple(connectors)
        exclusions = []

        for provider_id in requested:
            if provider_id not in connectors:
                exclusions.append(ProviderExclusion(provider_id, PROVIDER_NOT_REGISTERED))

        candidate_ids = seeded
        if requested:
            requested_set = set(requested)
            candidate_ids = tuple(item for item in candidate_ids if item in requested_set)

        after_lifecycle = []
        for provider_id in candidate_ids:
            connector = connectors[provider_id]
            if connector.status != ConnectorStatus.ACTIVE:
                exclusions.append(ProviderExclusion(provider_id, NOT_ACTIVE, connector.status.value))
            else:
                after_lifecycle.append(provider_id)

        required = {item.upper() for item in request.required_capabilities}
        after_capability = []
        for provider_id in after_lifecycle:
            declared = {str(item).upper() for item in connectors[provider_id].capabilities}
            if not required.issubset(declared):
                exclusions.append(ProviderExclusion(provider_id, CAPABILITY_MISMATCH))
            else:
                after_capability.append(provider_id)

        geographic_ids = set(
            self.jurisdiction_registry.list_provider_ids(request.state, request.county)
        )
        after_geography = []
        for provider_id in after_capability:
            if provider_id not in geographic_ids:
                exclusions.append(ProviderExclusion(provider_id, JURISDICTION_UNSUPPORTED))
            else:
                after_geography.append(provider_id)

        resolved = {}
        after_runtime = []
        for provider_id in after_geography:
            provider = self.runtime_resolver(provider_id)
            if provider is None:
                exclusions.append(ProviderExclusion(provider_id, RUNTIME_UNAVAILABLE))
            else:
                resolved[provider_id] = provider
                after_runtime.append(provider_id)

        health_by_id = {}
        after_health = []
        for provider_id in after_runtime:
            health = self.health_evaluator(provider_id, resolved[provider_id])
            if not isinstance(health, ProviderHealth) or not health.available:
                detail = health.status if isinstance(health, ProviderHealth) else "INVALID_HEALTH_PROJECTION"
                exclusions.append(ProviderExclusion(provider_id, HEALTH_UNAVAILABLE, detail))
            else:
                health_by_id[provider_id] = health
                after_health.append(provider_id)

        eligible = tuple(
            ProviderEligibilityProjection(
                provider_id=provider_id,
                connector=connectors[provider_id],
                provider=resolved[provider_id],
                health=health_by_id[provider_id],
            )
            for provider_id in after_health
        )
        detail = ProviderEnumerationDetail(
            seeded=seeded,
            geographic_mappings=tuple(sorted(geographic_ids)),
            after_lifecycle=tuple(after_lifecycle),
            after_capability=tuple(after_capability),
            after_geography=tuple(after_geography),
            after_runtime=tuple(after_runtime),
            after_health=tuple(after_health),
        )
        return ProviderEnumerationResult(
            eligible=eligible,
            exclusions=tuple(sorted(exclusions, key=lambda item: (item.provider_id, item.reason))),
            detail=detail,
            evaluated_at=self.clock().astimezone(timezone.utc).isoformat(),
        )
