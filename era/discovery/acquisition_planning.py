"""SDR-003: deterministic acquisition planning without acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from era.discovery.source_identity import RESOLVED, SourceIdentityResolution


PLANNED = "PLANNED"
NO_ACQUIRABLE_SOURCES = "NO_ACQUIRABLE_SOURCES"

POLICY_PRIORITY = "POLICY_PRIORITY"
STABLE_CANONICAL_ORDER = "STABLE_CANONICAL_ORDER"

UNRESOLVED_SOURCE = "UNRESOLVED_SOURCE"
AMBIGUOUS_RESOLUTION_INPUT = "AMBIGUOUS_RESOLUTION_INPUT"
PROVIDER_NOT_ELIGIBLE = "PROVIDER_NOT_ELIGIBLE"
JURISDICTION_MISMATCH = "JURISDICTION_MISMATCH"
RECORD_TYPE_NOT_REQUESTED = "RECORD_TYPE_NOT_REQUESTED"

PLAN_STATUSES = frozenset({PLANNED, NO_ACQUIRABLE_SOURCES})
PLAN_RATIONALE_CODES = frozenset({POLICY_PRIORITY, STABLE_CANONICAL_ORDER})
PLAN_EXCLUSION_REASONS = frozenset({
    UNRESOLVED_SOURCE, AMBIGUOUS_RESOLUTION_INPUT, PROVIDER_NOT_ELIGIBLE,
    JURISDICTION_MISMATCH, RECORD_TYPE_NOT_REQUESTED,
})


@dataclass(frozen=True)
class AcquisitionPolicy:
    policy_id: str
    record_type_order: tuple[str, ...] = ()
    provider_order: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanningRequest:
    state: str
    county: str
    discovery_result: object
    source_resolutions: tuple[SourceIdentityResolution, ...]
    eligibility_projections: tuple[object, ...]
    requested_record_types: tuple[str, ...]
    policy: AcquisitionPolicy
    catalog_version: str


@dataclass(frozen=True)
class AcquisitionPlanStep:
    sequence: int
    canonical_source_id: str
    provider_id: str
    record_type: str
    provider_local_lookup_reference: str
    rationale_code: str


@dataclass(frozen=True)
class PlanningExclusion:
    source_reference: str
    provider_id: str
    reason_code: str


@dataclass(frozen=True)
class AcquisitionPlan:
    status: str
    steps: tuple[AcquisitionPlanStep, ...]
    exclusions: tuple[PlanningExclusion, ...]
    policy_id: str
    catalog_version: str
    replay_metadata: tuple[tuple[str, str], ...]
    planned_at: str


class AcquisitionPlanner:
    """Pure plan derivation over supplied immutable upstream projections."""

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def plan(self, request: PlanningRequest) -> AcquisitionPlan:
        resolutions = {}
        duplicate_references = set()
        for resolution in request.source_resolutions:
            key = resolution.input_reference
            if key in resolutions:
                duplicate_references.add(key)
            resolutions[key] = resolution

        eligible_ids = {item.provider_id for item in request.eligibility_projections}
        requested_types = {item.upper() for item in request.requested_record_types}
        candidates = []
        exclusions = []
        for source in request.discovery_result.sources:
            if source.source_id in duplicate_references:
                exclusions.append(self._exclude(source, AMBIGUOUS_RESOLUTION_INPUT))
                continue
            resolution = resolutions.get(source.source_id)
            if resolution is None or resolution.status != RESOLVED or not resolution.canonical_source_id:
                exclusions.append(self._exclude(source, UNRESOLVED_SOURCE))
                continue
            if source.provider_id not in eligible_ids:
                exclusions.append(self._exclude(source, PROVIDER_NOT_ELIGIBLE))
                continue
            if source.jurisdiction.state != request.state or source.jurisdiction.county != request.county:
                exclusions.append(self._exclude(source, JURISDICTION_MISMATCH))
                continue
            if requested_types and source.record_type.upper() not in requested_types:
                exclusions.append(self._exclude(source, RECORD_TYPE_NOT_REQUESTED))
                continue
            candidates.append((source, resolution.canonical_source_id))

        record_order = {value.upper(): index for index, value in enumerate(request.policy.record_type_order)}
        provider_order = {value: index for index, value in enumerate(request.policy.provider_order)}
        fallback = 1_000_000
        candidates.sort(key=lambda item: (
            record_order.get(item[0].record_type.upper(), fallback),
            provider_order.get(item[0].provider_id, fallback),
            item[1], item[0].provider_id, item[0].source_id,
        ))
        rationale = POLICY_PRIORITY if record_order or provider_order else STABLE_CANONICAL_ORDER
        steps = tuple(
            AcquisitionPlanStep(
                index, canonical_id, source.provider_id, source.record_type,
                source.source_id, rationale,
            )
            for index, (source, canonical_id) in enumerate(candidates, start=1)
        )
        exclusions = tuple(sorted(exclusions, key=lambda item: (
            item.provider_id, item.source_reference, item.reason_code
        )))
        replay_metadata = tuple(sorted({
            "catalog_version": request.catalog_version,
            "county": request.county,
            "discovery_observed_at": request.discovery_result.observed_at,
            "policy_id": request.policy.policy_id,
            "state": request.state,
        }.items()))
        return AcquisitionPlan(
            status=PLANNED if steps else NO_ACQUIRABLE_SOURCES,
            steps=steps,
            exclusions=exclusions,
            policy_id=request.policy.policy_id,
            catalog_version=request.catalog_version,
            replay_metadata=replay_metadata,
            planned_at=self.clock().astimezone(timezone.utc).isoformat(),
        )

    @staticmethod
    def _exclude(source, reason):
        return PlanningExclusion(source.source_id, source.provider_id, reason)
