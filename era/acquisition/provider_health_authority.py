"""HA-001: stateless provider-health derivation at the acquisition boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.connector_enums import ConnectorStatus


HEALTHY = "HEALTHY"
PROVIDER_NOT_REGISTERED = "PROVIDER_NOT_REGISTERED"
PROVIDER_NOT_ACTIVE = "PROVIDER_NOT_ACTIVE"
READINESS_UNAVAILABLE = "READINESS_UNAVAILABLE"
READINESS_FAILED = "READINESS_FAILED"
PROBE_UNAVAILABLE = "PROBE_UNAVAILABLE"
PROBE_FAILED = "PROBE_FAILED"

STATUS_REASONS = frozenset({
    HEALTHY,
    PROVIDER_NOT_REGISTERED,
    PROVIDER_NOT_ACTIVE,
    READINESS_UNAVAILABLE,
    READINESS_FAILED,
    PROBE_UNAVAILABLE,
    PROBE_FAILED,
})


class ReadinessObservation(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    UNKNOWN = "UNKNOWN"


class ProbeObservation(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class DecisiveAuthority(str, Enum):
    REGISTRATION = "REGISTRATION"
    LIFECYCLE = "LIFECYCLE"
    READINESS = "READINESS"
    OPERATIONAL_PROBE = "OPERATIONAL_PROBE"
    HEALTHY = "HEALTHY"


@dataclass(frozen=True)
class HealthEvaluationDetail:
    provider_id: str
    observed_at: str
    reason: str
    decisive_authority: DecisiveAuthority
    lifecycle_status: str | None
    success_rate: float | None
    consecutive_failures: int | None
    average_response_time_ms: int | None
    health: ProviderHealth


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderHealthAuthority:
    """Read SRR facts and provider observations; own and persist no health state."""

    def __init__(self, source_registry, clock: Callable[[], str] | None = None):
        self.source_registry = source_registry
        self._clock = clock or _utc_now

    @staticmethod
    def normalize_readiness(value: Any) -> ReadinessObservation:
        if isinstance(value, ReadinessObservation):
            return value
        if type(value) is bool:
            return ReadinessObservation.READY if value else ReadinessObservation.NOT_READY
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {"READY", "PASS"}:
                return ReadinessObservation.READY
            if normalized in {"NOT_READY", "FAILED", "FAIL"}:
                return ReadinessObservation.NOT_READY
        return ReadinessObservation.UNKNOWN

    @staticmethod
    def normalize_probe(value: Any) -> ProbeObservation:
        if isinstance(value, ProbeObservation):
            return value
        if isinstance(value, ProviderHealth):
            return ProbeObservation.AVAILABLE if value.available else ProbeObservation.UNAVAILABLE
        if type(value) is bool:
            return ProbeObservation.AVAILABLE if value else ProbeObservation.UNAVAILABLE
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {"AVAILABLE", "PASS", "HEALTHY"}:
                return ProbeObservation.AVAILABLE
            if normalized in {"UNAVAILABLE", "FAILED", "FAIL"}:
                return ProbeObservation.UNAVAILABLE
        return ProbeObservation.UNKNOWN

    def _detail(self, provider_id, connector, reason, authority, available):
        lifecycle = None
        if connector is not None:
            lifecycle = str(getattr(connector.status, "value", connector.status)).upper()
        return HealthEvaluationDetail(
            provider_id=provider_id,
            observed_at=self._clock(),
            reason=reason,
            decisive_authority=authority,
            lifecycle_status=lifecycle,
            success_rate=getattr(connector, "success_rate", None),
            consecutive_failures=getattr(connector, "consecutive_failures", None),
            average_response_time_ms=getattr(connector, "average_response_time_ms", None),
            health=ProviderHealth(available=available, status=reason),
        )

    @staticmethod
    def _observe(value_or_callable):
        return value_or_callable() if callable(value_or_callable) else value_or_callable

    def evaluate_with_detail(
        self,
        provider_id: str,
        provider,
        readiness_observation: Any = None,
        probe_observation: Any = None,
    ) -> HealthEvaluationDetail:
        connector = self.source_registry.get_connector(provider_id)
        if connector is None:
            return self._detail(
                provider_id, None, PROVIDER_NOT_REGISTERED,
                DecisiveAuthority.REGISTRATION, False,
            )

        lifecycle = str(getattr(connector.status, "value", connector.status)).upper()
        if lifecycle != ConnectorStatus.ACTIVE.value:
            return self._detail(
                provider_id, connector, PROVIDER_NOT_ACTIVE,
                DecisiveAuthority.LIFECYCLE, False,
            )

        if readiness_observation is None:
            readiness_observation = getattr(provider, "readiness_observation", None)
        if readiness_observation is None:
            return self._detail(
                provider_id, connector, READINESS_UNAVAILABLE,
                DecisiveAuthority.READINESS, False,
            )
        try:
            readiness = self.normalize_readiness(self._observe(readiness_observation))
        except Exception:
            readiness = ReadinessObservation.NOT_READY
        if readiness == ReadinessObservation.UNKNOWN:
            return self._detail(
                provider_id, connector, READINESS_UNAVAILABLE,
                DecisiveAuthority.READINESS, False,
            )
        if readiness == ReadinessObservation.NOT_READY:
            return self._detail(
                provider_id, connector, READINESS_FAILED,
                DecisiveAuthority.READINESS, False,
            )

        if probe_observation is None:
            # Prefer the raw observation seam. This deliberately bypasses
            # wrapper projections that may already contain truthiness defects.
            probe_observation = getattr(provider, "health_check", None)
            if not callable(probe_observation):
                probe_observation = getattr(provider, "health", None)
        if probe_observation is None:
            return self._detail(
                provider_id, connector, PROBE_UNAVAILABLE,
                DecisiveAuthority.OPERATIONAL_PROBE, False,
            )
        try:
            probe = self.normalize_probe(self._observe(probe_observation))
        except Exception:
            probe = ProbeObservation.UNAVAILABLE
        if probe == ProbeObservation.UNKNOWN:
            return self._detail(
                provider_id, connector, PROBE_UNAVAILABLE,
                DecisiveAuthority.OPERATIONAL_PROBE, False,
            )
        if probe == ProbeObservation.UNAVAILABLE:
            return self._detail(
                provider_id, connector, PROBE_FAILED,
                DecisiveAuthority.OPERATIONAL_PROBE, False,
            )

        return self._detail(
            provider_id, connector, HEALTHY,
            DecisiveAuthority.HEALTHY, True,
        )

    def evaluate(
        self,
        provider_id: str,
        provider,
        readiness_observation: Any = None,
        probe_observation: Any = None,
    ) -> ProviderHealth:
        return self.evaluate_with_detail(
            provider_id,
            provider,
            readiness_observation=readiness_observation,
            probe_observation=probe_observation,
        ).health

    # Compatibility with the provisional HA-001 name. It preserves the new
    # fail-closed readiness law rather than recreating the old semantics.
    derive = evaluate
