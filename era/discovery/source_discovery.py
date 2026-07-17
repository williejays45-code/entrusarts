"""SDR-001: deterministic, stateless discovery over eligible providers."""

from __future__ import annotations

from dataclasses import dataclass

from era.acquisition.provider_enumeration_authority import ProviderEnumerationRequest


RECORD_TYPE_UNAVAILABLE = "RECORD_TYPE_UNAVAILABLE"
METADATA_UNAVAILABLE = "METADATA_UNAVAILABLE"
DISCOVERY_EXCLUSION_REASONS = frozenset({RECORD_TYPE_UNAVAILABLE, METADATA_UNAVAILABLE})


@dataclass(frozen=True)
class DiscoveryRequest:
    state: str
    county: str
    record_types: tuple[str, ...] = ()
    requested_provider_ids: tuple[str, ...] = ()
    catalog_version: str = "SDR-001"


@dataclass(frozen=True)
class JurisdictionObservation:
    state: str
    county: str


@dataclass(frozen=True)
class SourceObservation:
    provider_id: str
    source_id: str
    source_kind: str
    record_type: str
    jurisdiction: JurisdictionObservation
    availability_observation: str
    provenance_metadata: tuple[tuple[str, str], ...]
    observed_at: str


@dataclass(frozen=True)
class DiscoveryExclusion:
    provider_id: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class DiscoveryResult:
    sources: tuple[SourceObservation, ...]
    provider_exclusions: tuple[object, ...]
    discovery_exclusions: tuple[DiscoveryExclusion, ...]
    evaluated_provider_ids: tuple[str, ...]
    catalog_version: str
    observed_at: str
    completeness_statement: str


class SourceDiscovery:
    """Project known source metadata without acquiring records or storing state."""

    def __init__(self, provider_enumeration_authority):
        self.provider_enumeration_authority = provider_enumeration_authority

    def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        enumeration = self.provider_enumeration_authority.enumerate(
            ProviderEnumerationRequest(
                state=request.state,
                county=request.county,
                requested_provider_ids=tuple(sorted(set(request.requested_provider_ids))),
            )
        )
        requested_types = tuple(sorted({item.upper() for item in request.record_types}))
        jurisdiction = JurisdictionObservation(request.state, request.county)
        sources = []
        exclusions = []

        for eligibility in enumeration.eligible:
            metadata_method = getattr(eligibility.provider, "metadata", None)
            metadata = metadata_method() if callable(metadata_method) else None
            if metadata is None:
                exclusions.append(DiscoveryExclusion(eligibility.provider_id, METADATA_UNAVAILABLE))
                continue

            declared = tuple(sorted({str(item).upper() for item in eligibility.connector.capabilities}))
            record_types = tuple(item for item in declared if not requested_types or item in requested_types)
            if not record_types:
                exclusions.append(DiscoveryExclusion(
                    eligibility.provider_id,
                    RECORD_TYPE_UNAVAILABLE,
                    ",".join(requested_types),
                ))
                continue

            provenance = tuple(sorted({
                "connector_version": str(metadata.connector_version),
                "legal_basis": str(metadata.legal_basis),
                "provider_name": str(metadata.provider_name),
                "source_name": str(metadata.source_name),
            }.items()))
            source_id = f"{eligibility.provider_id}:{metadata.source_name}"
            for record_type in record_types:
                sources.append(SourceObservation(
                    provider_id=eligibility.provider_id,
                    source_id=source_id,
                    source_kind=str(metadata.legal_basis),
                    record_type=record_type,
                    jurisdiction=jurisdiction,
                    availability_observation=eligibility.health.status,
                    provenance_metadata=provenance,
                    observed_at=enumeration.evaluated_at,
                ))

        sources = tuple(sorted(sources, key=lambda item: (
            item.provider_id, item.source_id, item.record_type
        )))
        exclusions = tuple(sorted(exclusions, key=lambda item: (item.provider_id, item.reason)))
        evaluated = tuple(item.provider_id for item in enumeration.eligible)
        statement = (
            "All eligible sources known to ERA for the requested jurisdiction, "
            "record types, and catalog version were evaluated."
        )
        return DiscoveryResult(
            sources=sources,
            provider_exclusions=enumeration.exclusions,
            discovery_exclusions=exclusions,
            evaluated_provider_ids=evaluated,
            catalog_version=request.catalog_version,
            observed_at=enumeration.evaluated_at,
            completeness_statement=statement,
        )

