"""SDR-001 focused contract verification."""

from dataclasses import FrozenInstanceError, dataclass

from era.acquisition.acquisition_provider import ProviderHealth, ProviderMetadata
from era.acquisition.connector_enums import ConnectorStatus
from era.acquisition.provider_enumeration_authority import (
    ProviderEligibilityProjection,
    ProviderEnumerationDetail,
    ProviderEnumerationResult,
    ProviderExclusion,
    PROVIDER_NOT_REGISTERED,
)
from era.discovery.source_discovery import (
    DISCOVERY_EXCLUSION_REASONS,
    METADATA_UNAVAILABLE,
    RECORD_TYPE_UNAVAILABLE,
    DiscoveryRequest,
    SourceDiscovery,
)


@dataclass(frozen=True)
class Connector:
    connector_id: str
    status: ConnectorStatus
    capabilities: tuple[str, ...]


class Provider:
    def __init__(self, provider_id, metadata=True):
        self.provider_id_value = provider_id
        self.has_metadata = metadata
        self.retrieve_calls = 0

    def metadata(self):
        if not self.has_metadata:
            return None
        return ProviderMetadata(
            provider_id=self.provider_id_value,
            provider_name=f"Provider {self.provider_id_value}",
            connector_version="1.0",
            legal_basis="PUBLIC_RECORD",
            source_name=f"SOURCE_{self.provider_id_value}",
        )

    def retrieve(self, request):
        self.retrieve_calls += 1
        raise AssertionError("SDR-001 must not acquire records")


class EnumerationAuthority:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def enumerate(self, request):
        self.calls.append(request)
        return self.result


def projection(provider_id, capabilities=("PARCEL", "OWNERSHIP"), metadata=True):
    provider = Provider(provider_id, metadata)
    connector = Connector(provider_id, ConnectorStatus.ACTIVE, capabilities)
    return ProviderEligibilityProjection(
        provider_id=provider_id,
        connector=connector,
        provider=provider,
        health=ProviderHealth(True, "AVAILABLE"),
    )


def run_checks():
    a = projection("A_PROVIDER")
    b = projection("B_PROVIDER", ("TAX",))
    c = projection("C_PROVIDER", metadata=False)
    detail = ProviderEnumerationDetail(
        seeded=("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
        geographic_mappings=("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
        after_lifecycle=("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
        after_capability=("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
        after_geography=("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
        after_runtime=("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
        after_health=("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
    )
    enumeration = ProviderEnumerationResult(
        eligible=(a, b, c),
        exclusions=(ProviderExclusion("Z_UNKNOWN", PROVIDER_NOT_REGISTERED),),
        detail=detail,
        evaluated_at="2026-07-12T20:00:00+00:00",
    )
    authority = EnumerationAuthority(enumeration)
    discovery = SourceDiscovery(authority)
    request = DiscoveryRequest(
        state="TX", county="Dallas", record_types=("PARCEL", "TAX"),
        requested_provider_ids=("B_PROVIDER", "A_PROVIDER", "A_PROVIDER"),
        catalog_version="CATALOG-4",
    )
    result = discovery.discover(request)
    result2 = discovery.discover(request)
    source_keys = tuple((item.provider_id, item.source_id, item.record_type) for item in result.sources)
    discovery_reasons = {item.provider_id: item.reason for item in result.discovery_exclusions}

    checks = {
        "enumeration_called_once_per_discovery": len(authority.calls) == 2,
        "requested_provider_ids_normalized": authority.calls[0].requested_provider_ids == ("A_PROVIDER", "B_PROVIDER"),
        "provider_capability_filter_not_recreated": authority.calls[0].required_capabilities == (),
        "eligible_providers_only": result.evaluated_provider_ids == ("A_PROVIDER", "B_PROVIDER", "C_PROVIDER"),
        "sources_sorted_deterministically": source_keys == tuple(sorted(source_keys)),
        "requested_record_types_only": {item.record_type for item in result.sources} == {"PARCEL", "TAX"},
        "stable_source_ids": all(item.source_id.startswith(item.provider_id + ":") for item in result.sources),
        "jurisdiction_projected": all(item.jurisdiction.state == "TX" and item.jurisdiction.county == "Dallas" for item in result.sources),
        "availability_from_eligibility": all(item.availability_observation == "AVAILABLE" for item in result.sources),
        "provenance_is_immutable_pairs": all(isinstance(item.provenance_metadata, tuple) for item in result.sources),
        "observation_timestamp_reused": result.observed_at == enumeration.evaluated_at and all(item.observed_at == enumeration.evaluated_at for item in result.sources),
        "catalog_version_projected": result.catalog_version == "CATALOG-4",
        "provider_exclusions_carried_forward": result.provider_exclusions == enumeration.exclusions,
        "metadata_failure_is_structured": discovery_reasons["C_PROVIDER"] == METADATA_UNAVAILABLE,
        "closed_discovery_reasons": all(item.reason in DISCOVERY_EXCLUSION_REASONS for item in result.discovery_exclusions),
        "no_record_acquisition": all(item.provider.retrieve_calls == 0 for item in (a, b, c)),
        "deterministic_result": result == result2,
        "bounded_completeness_statement": result.completeness_statement.startswith("All eligible sources known to ERA"),
        "no_absolute_completeness_claim": "all possible" not in result.completeness_statement.lower(),
        "no_persistence_state": set(discovery.__dict__) == {"provider_enumeration_authority"},
    }
    try:
        result.catalog_version = "changed"
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["result_immutable"] = frozen

    unmatched = SourceDiscovery(EnumerationAuthority(ProviderEnumerationResult(
        eligible=(b,), exclusions=(), detail=detail,
        evaluated_at=enumeration.evaluated_at,
    ))).discover(DiscoveryRequest("TX", "Dallas", record_types=("PARCEL",)))
    checks["record_type_unavailable_structured"] = (
        unmatched.discovery_exclusions[0].reason == RECORD_TYPE_UNAVAILABLE
        and unmatched.sources == ()
    )
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"SDR-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)

