"""SDR-003 deterministic planning and boundary verification."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.provider_enumeration_authority import ProviderEligibilityProjection
from era.discovery.acquisition_planning import (
    AMBIGUOUS_RESOLUTION_INPUT, JURISDICTION_MISMATCH, NO_ACQUIRABLE_SOURCES,
    PLANNED, POLICY_PRIORITY, PROVIDER_NOT_ELIGIBLE, RECORD_TYPE_NOT_REQUESTED,
    STABLE_CANONICAL_ORDER, UNRESOLVED_SOURCE, AcquisitionPlanner,
    AcquisitionPolicy, PlanningRequest,
)
from era.discovery.source_discovery import (
    DiscoveryResult, JurisdictionObservation, SourceObservation,
)
from era.discovery.source_identity import (
    DECLARED_ALIAS_MATCH, RESOLVED, UNRESOLVED, UNKNOWN_ALIAS,
    SourceIdentityResolution,
)


NOW = datetime(2026, 7, 12, 22, 0, tzinfo=timezone.utc)


class ForbiddenProvider:
    def __getattribute__(self, name):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        raise AssertionError("planner inspected runtime provider")


def source(provider_id, source_id, record_type="PARCEL", county="Dallas"):
    return SourceObservation(
        provider_id, source_id, "PUBLIC_RECORD", record_type,
        JurisdictionObservation("TX", county), "AVAILABLE", (),
        "2026-07-12T21:00:00+00:00",
    )


def resolution(reference, canonical_id, status=RESOLVED):
    return SourceIdentityResolution(
        reference, reference.lower(), canonical_id if status == RESOLVED else None,
        status, DECLARED_ALIAS_MATCH if status == RESOLVED else UNKNOWN_ALIAS,
        reference if status == RESOLVED else None, "1", "CATALOG-4",
        "2026-07-12T21:00:00+00:00",
    )


def eligibility(provider_id):
    connector = type("Connector", (), {"connector_id": provider_id})()
    return ProviderEligibilityProjection(
        provider_id, connector, ForbiddenProvider(), ProviderHealth(True, "AVAILABLE")
    )


def discovery(sources):
    return DiscoveryResult(
        tuple(sources), (), (), tuple(item.provider_id for item in sources),
        "CATALOG-4", "2026-07-12T21:00:00+00:00",
        "All eligible sources known to ERA were evaluated.",
    )


def run_checks():
    a = source("A", "A:PARCEL", "PARCEL")
    b = source("B", "B:TAX", "TAX")
    c = source("C", "C:PARCEL", "PARCEL")
    resolutions = (
        resolution(a.source_id, "src:tx-dallas:a:public_record:parcel"),
        resolution(b.source_id, "src:tx-dallas:b:public_record:tax"),
        resolution(c.source_id, "src:tx-dallas:c:public_record:parcel"),
    )
    policy = AcquisitionPolicy("POLICY-1", ("TAX", "PARCEL"), ("B", "A", "C"))
    request = PlanningRequest(
        "TX", "Dallas", discovery((c, b, a)), tuple(reversed(resolutions)),
        (eligibility("C"), eligibility("A"), eligibility("B")),
        ("PARCEL", "TAX"), policy, "CATALOG-4",
    )
    planner = AcquisitionPlanner(clock=lambda: NOW)
    plan = planner.plan(request)
    replay = planner.plan(request)
    reordered = planner.plan(PlanningRequest(
        "TX", "Dallas", discovery((a, c, b)), resolutions,
        (eligibility("B"), eligibility("C"), eligibility("A")),
        ("TAX", "PARCEL"), policy, "CATALOG-4",
    ))

    checks = {
        "plan_created": plan.status == PLANNED and len(plan.steps) == 3,
        "policy_order_applied": tuple(item.provider_id for item in plan.steps) == ("B", "A", "C"),
        "sequence_contiguous": tuple(item.sequence for item in plan.steps) == (1, 2, 3),
        "canonical_ids_only": all(item.canonical_source_id.startswith("src:") for item in plan.steps),
        "closed_rationale": all(item.rationale_code == POLICY_PRIORITY for item in plan.steps),
        "input_order_irrelevant": plan.steps == reordered.steps,
        "semantic_replayability": plan == replay,
        "timestamp_injected": plan.planned_at == "2026-07-12T22:00:00+00:00",
        "replay_metadata_stable": plan.replay_metadata == replay.replay_metadata,
        "catalog_and_policy_projected": plan.catalog_version == "CATALOG-4" and plan.policy_id == "POLICY-1",
        "provider_not_inspected": True,
        "planner_has_no_result_state": set(planner.__dict__) == {"clock"},
    }
    try:
        plan.status = NO_ACQUIRABLE_SOURCES
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["plan_immutable"] = frozen

    default_plan = planner.plan(PlanningRequest(
        "TX", "Dallas", discovery((c, a)), (resolutions[2], resolutions[0]),
        (eligibility("A"), eligibility("C")), ("PARCEL",),
        AcquisitionPolicy("LEXICAL"), "CATALOG-4",
    ))
    checks["canonical_fallback_order"] = (
        tuple(item.provider_id for item in default_plan.steps) == ("A", "C")
        and all(item.rationale_code == STABLE_CANONICAL_ORDER for item in default_plan.steps)
    )

    unresolved_source = source("A", "A:UNKNOWN")
    wrong_jurisdiction = source("A", "A:OTHER_COUNTY", county="Tarrant")
    unrequested = source("A", "A:OWNERSHIP", "OWNERSHIP")
    not_eligible = source("Z", "Z:PARCEL")
    excluded = planner.plan(PlanningRequest(
        "TX", "Dallas", discovery((unresolved_source, wrong_jurisdiction, unrequested, not_eligible)),
        (
            resolution(unresolved_source.source_id, "", UNRESOLVED),
            resolution(wrong_jurisdiction.source_id, "src:tx-tarrant:a:public_record:parcel"),
            resolution(unrequested.source_id, "src:tx-dallas:a:public_record:ownership"),
            resolution(not_eligible.source_id, "src:tx-dallas:z:public_record:parcel"),
        ),
        (eligibility("A"),), ("PARCEL",), policy, "CATALOG-4",
    ))
    reasons = {item.source_reference: item.reason_code for item in excluded.exclusions}
    checks["unresolved_excluded"] = reasons[unresolved_source.source_id] == UNRESOLVED_SOURCE
    checks["jurisdiction_mismatch_excluded"] = reasons[wrong_jurisdiction.source_id] == JURISDICTION_MISMATCH
    checks["record_type_excluded"] = reasons[unrequested.source_id] == RECORD_TYPE_NOT_REQUESTED
    checks["ineligible_provider_excluded"] = reasons[not_eligible.source_id] == PROVIDER_NOT_ELIGIBLE
    checks["empty_plan_closed"] = excluded.status == NO_ACQUIRABLE_SOURCES and excluded.steps == ()

    duplicate = planner.plan(PlanningRequest(
        "TX", "Dallas", discovery((a,)), (resolutions[0], resolutions[0]),
        (eligibility("A"),), ("PARCEL",), policy, "CATALOG-4",
    ))
    checks["duplicate_resolution_fails_closed"] = duplicate.exclusions[0].reason_code == AMBIGUOUS_RESOLUTION_INPUT

    source_text = (Path(__file__).parent / "acquisition_planning.py").read_text(encoding="utf-8").lower()
    checks["no_srr_jre_health_queries"] = all(term not in source_text for term in ("source_reliability", "jurisdiction_registry", "health_evaluator", "evaluate_provider_health"))
    checks["no_acquisition_execution"] = all(term not in source_text for term in (".retrieve(", ".run(", "acquisitionresult"))
    checks["no_evidence_reasoning"] = all(term not in source_text for term in ("canonicalevidence", "decisionengine", "confidence", "recommendation"))
    checks["no_persistence"] = all(term not in source_text for term in ("sqlite", "database", "persist("))
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"SDR-003 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)

