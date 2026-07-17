"""HA-001 finalized verification: authority, observations, and explainability."""

from dataclasses import dataclass

from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.connector_enums import ConnectorStatus
from era.acquisition.provider_health_authority import (
    DecisiveAuthority,
    HEALTHY,
    PROBE_FAILED,
    PROBE_UNAVAILABLE,
    PROVIDER_NOT_ACTIVE,
    PROVIDER_NOT_REGISTERED,
    READINESS_FAILED,
    READINESS_UNAVAILABLE,
    ProviderHealthAuthority,
    ReadinessObservation,
)
from era.container import TarrantConnectorProviderAdapter


@dataclass(frozen=True)
class Connector:
    status: ConnectorStatus
    success_rate: float | None = 0.75
    consecutive_failures: int = 2
    average_response_time_ms: int | None = 120
    last_success: str | None = "2026-01-01T00:00:00+00:00"
    last_failure: str | None = "2026-01-02T00:00:00+00:00"
    success_count: int = 3
    failure_count: int = 1


class Registry:
    def __init__(self, connector):
        self.connector = connector

    def get_connector(self, provider_id):
        return self.connector


class Provider:
    def __init__(self, probe=True):
        self.probe = probe
        self.probe_calls = 0

    def health_check(self):
        self.probe_calls += 1
        return self.probe


def authority(connector):
    return ProviderHealthAuthority(
        Registry(connector),
        clock=lambda: "2026-07-12T00:00:00+00:00",
    )


def run_checks():
    checks = {}
    active = Connector(ConnectorStatus.ACTIVE)

    checks["01_missing_registration"] = authority(None).evaluate(
        "P", Provider(), ReadinessObservation.READY
    ) == ProviderHealth(False, PROVIDER_NOT_REGISTERED)

    for number, status in ((2, ConnectorStatus.DISABLED), (3, ConnectorStatus.SUSPENDED), (4, ConnectorStatus.DRAFT)):
        checks[f"{number:02d}_{status.value.lower()}_not_active"] = authority(Connector(status)).evaluate(
            "P", Provider(), ReadinessObservation.READY
        ) == ProviderHealth(False, PROVIDER_NOT_ACTIVE)

    inactive_provider = Provider(True)
    authority(Connector(ConnectorStatus.DISABLED)).evaluate(
        "P", inactive_provider, ReadinessObservation.READY
    )
    checks["05_non_active_skips_probe"] = inactive_provider.probe_calls == 0

    checks["06_missing_readiness"] = authority(active).evaluate("P", Provider()) == ProviderHealth(
        False, READINESS_UNAVAILABLE
    )
    checks["07_failed_readiness"] = authority(active).evaluate(
        "P", Provider(), ReadinessObservation.NOT_READY
    ) == ProviderHealth(False, READINESS_FAILED)
    checks["08_missing_probe"] = authority(active).evaluate(
        "P", object(), ReadinessObservation.READY
    ) == ProviderHealth(False, PROBE_UNAVAILABLE)
    checks["09_failed_probe"] = authority(active).evaluate(
        "P", Provider(False), ReadinessObservation.READY
    ) == ProviderHealth(False, PROBE_FAILED)
    checks["10_healthy"] = authority(active).evaluate(
        "P", Provider(True), ReadinessObservation.READY
    ) == ProviderHealth(True, HEALTHY)

    tarrant = object.__new__(TarrantConnectorProviderAdapter)
    checks["11_tarrant_pass_explicit"] = authority(active).evaluate(
        "P", tarrant, ReadinessObservation.READY
    ) == ProviderHealth(True, HEALTHY)
    checks["12_unknown_truthy_string_rejected"] = authority(active).evaluate(
        "P", Provider("SOMETHING_TRUTHY"), ReadinessObservation.READY
    ) == ProviderHealth(False, PROBE_UNAVAILABLE)

    original = active
    registry = Registry(original)
    ProviderHealthAuthority(registry).evaluate("P", Provider(True), ReadinessObservation.READY)
    checks["13_srr_facts_not_mutated"] = registry.connector is original and registry.connector == original

    stable = authority(active)
    first = stable.evaluate("P", Provider(True), ReadinessObservation.READY)
    second = stable.evaluate("P", Provider(True), ReadinessObservation.READY)
    checks["14_repeated_evaluation_deterministic"] = first == second

    detail = authority(active).evaluate_with_detail(
        "P", Provider(False), ReadinessObservation.READY
    )
    checks["15_explainability_detail"] = (
        detail.provider_id == "P"
        and detail.observed_at == "2026-07-12T00:00:00+00:00"
        and detail.reason == PROBE_FAILED
        and detail.decisive_authority == DecisiveAuthority.OPERATIONAL_PROBE
        and detail.lifecycle_status == "ACTIVE"
        and detail.success_rate == active.success_rate
        and detail.consecutive_failures == active.consecutive_failures
    )

    checks["16_unknown_readiness_unavailable"] = authority(active).evaluate(
        "P", Provider(True), "MYSTERY"
    ) == ProviderHealth(False, READINESS_UNAVAILABLE)
    checks["17_closed_status_vocabulary"] = first.status == HEALTHY
    return checks


if __name__ == "__main__":
    results = run_checks()
    for name, passed in results.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(results.values())
    print(f"HA-001 FINAL CHECKS PASSED: {passed}/{len(results)}")
    raise SystemExit(0 if passed == len(results) else 1)
