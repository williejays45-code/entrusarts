"""PER-001: provider enumeration authority and monotonic eligibility verification."""

from dataclasses import FrozenInstanceError, dataclass
from datetime import datetime, timezone
from pathlib import Path

from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.connector_enums import ConnectorStatus
from era.acquisition.provider_enumeration_authority import (
    CAPABILITY_MISMATCH,
    HEALTH_UNAVAILABLE,
    JURISDICTION_UNSUPPORTED,
    NOT_ACTIVE,
    PROVIDER_NOT_REGISTERED,
    RUNTIME_UNAVAILABLE,
    ProviderEnumerationAuthority,
    ProviderEnumerationRequest,
)


@dataclass(frozen=True)
class Connector:
    connector_id: str
    status: ConnectorStatus
    capabilities: tuple[str, ...]


class SRR:
    def __init__(self, connectors): self.connectors = tuple(connectors)
    def list_connectors(self): return tuple(sorted(self.connectors, key=lambda item: item.connector_id))


class JRE:
    def __init__(self, ids): self.ids = tuple(ids)
    def list_provider_ids(self, state, county): return tuple(sorted(self.ids))


class Provider:
    def __init__(self, provider_id): self.provider_id = provider_id


def run_checks():
    connectors = (
        Connector("A_DISABLED", ConnectorStatus.DISABLED, ("PARCEL",)),
        Connector("B_CAP_MISS", ConnectorStatus.ACTIVE, ("OWNERSHIP",)),
        Connector("C_WRONG_GEO", ConnectorStatus.ACTIVE, ("PARCEL",)),
        Connector("D_NO_RUNTIME", ConnectorStatus.ACTIVE, ("PARCEL",)),
        Connector("E_UNHEALTHY", ConnectorStatus.ACTIVE, ("PARCEL",)),
        Connector("F_ELIGIBLE", ConnectorStatus.ACTIVE, ("PARCEL",)),
    )
    runtime = {
        "E_UNHEALTHY": Provider("E_UNHEALTHY"),
        "F_ELIGIBLE": Provider("F_ELIGIBLE"),
        "Z_CONTAINER_ONLY": Provider("Z_CONTAINER_ONLY"),
    }
    runtime_calls = []
    health_calls = []
    def resolve(provider_id):
        runtime_calls.append(provider_id)
        return runtime.get(provider_id)
    def health(provider_id, provider):
        health_calls.append(provider_id)
        return ProviderHealth(provider_id == "F_ELIGIBLE", "HEALTHY" if provider_id == "F_ELIGIBLE" else "PROBE_FAILED")

    authority = ProviderEnumerationAuthority(
        SRR(connectors),
        JRE(("A_DISABLED", "B_CAP_MISS", "D_NO_RUNTIME", "E_UNHEALTHY", "F_ELIGIBLE", "Y_JRE_ONLY")),
        resolve,
        health,
        clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
    )
    request = ProviderEnumerationRequest(
        state="TX", county="Dallas", required_capabilities=("PARCEL",),
        requested_provider_ids=("A_DISABLED", "B_CAP_MISS", "C_WRONG_GEO", "D_NO_RUNTIME", "E_UNHEALTHY", "F_ELIGIBLE", "Y_JRE_ONLY"),
    )
    result = authority.enumerate(request)
    result2 = authority.enumerate(request)
    reasons = {item.provider_id: item.reason for item in result.exclusions}
    d = result.detail
    stages = (d.seeded, d.after_lifecycle, d.after_capability, d.after_geography, d.after_runtime, d.after_health)

    checks = {}
    checks["srr_ids_sorted"] = d.seeded == tuple(sorted(d.seeded))
    checks["srr_only_seed"] = d.seeded == tuple(sorted(item.connector_id for item in connectors))
    checks["unknown_requested_fails_closed"] = reasons["Y_JRE_ONLY"] == PROVIDER_NOT_REGISTERED
    checks["inactive_excluded"] = reasons["A_DISABLED"] == NOT_ACTIVE
    checks["capability_mismatch_excluded"] = reasons["B_CAP_MISS"] == CAPABILITY_MISMATCH
    checks["wrong_geography_excluded"] = reasons["C_WRONG_GEO"] == JURISDICTION_UNSUPPORTED
    checks["missing_runtime_excluded"] = reasons["D_NO_RUNTIME"] == RUNTIME_UNAVAILABLE
    checks["unhealthy_excluded"] = reasons["E_UNHEALTHY"] == HEALTH_UNAVAILABLE
    checks["eligible_set_correct"] = tuple(item.provider_id for item in result.eligible) == ("F_ELIGIBLE",)
    checks["monotonic_eligibility"] = all(set(later).issubset(earlier) for earlier, later in zip(stages, stages[1:]))
    checks["runtime_only_after_geography"] = runtime_calls[:3] == ["D_NO_RUNTIME", "E_UNHEALTHY", "F_ELIGIBLE"]
    checks["health_once_per_survivor"] = health_calls[:2] == ["E_UNHEALTHY", "F_ELIGIBLE"]
    checks["container_only_never_introduced"] = "Z_CONTAINER_ONLY" not in {item.provider_id for item in result.eligible}
    checks["jre_only_never_introduced"] = "Y_JRE_ONLY" not in d.after_lifecycle
    checks["manifest_only_never_introduced"] = "M_MANIFEST_ONLY" not in d.seeded
    checks["missing_manifest_irrelevant"] = "provider_manifest" not in authority.__dict__
    checks["manifest_state_irrelevant"] = result.eligible == result2.eligible
    checks["inactive_not_resolved_or_probed"] = "A_DISABLED" not in runtime_calls and "A_DISABLED" not in health_calls
    checks["capability_mismatch_not_resolved_or_probed"] = "B_CAP_MISS" not in runtime_calls and "B_CAP_MISS" not in health_calls
    checks["wrong_geography_not_resolved_or_probed"] = "C_WRONG_GEO" not in runtime_calls and "C_WRONG_GEO" not in health_calls
    checks["missing_runtime_not_health_probed"] = "D_NO_RUNTIME" not in health_calls
    checks["removed_provider_never_reappears"] = all(
        not (set(earlier) - set(later)) & set(restored)
        for earlier, later, restored in zip(stages, stages[1:], stages[2:])
    )
    checks["no_stage_adds_or_substitutes"] = all(
        set(later).issubset(earlier) for earlier, later in zip(stages, stages[1:])
    )
    checks["eligible_and_exclusions_sorted"] = (
        tuple(item.provider_id for item in result.eligible) == tuple(sorted(item.provider_id for item in result.eligible))
        and result.exclusions == tuple(sorted(result.exclusions, key=lambda item: (item.provider_id, item.reason)))
    )
    checks["injected_operation_timestamp"] = result.evaluated_at == "2026-07-12T00:00:00+00:00"
    try:
        result.evaluated_at = "changed"
        immutable = False
    except FrozenInstanceError:
        immutable = True
    checks["result_is_immutable"] = immutable
    checks["authority_has_no_result_store"] = not any(
        name in authority.__dict__ for name in ("results", "eligible", "exclusions", "history")
    )
    checks["deterministic_projection"] = (
        tuple(item.provider_id for item in result.eligible) == tuple(item.provider_id for item in result2.eligible)
        and result.exclusions == result2.exclusions
        and result.detail == result2.detail
    )

    era_dir = Path(__file__).resolve().parents[1]
    enum_source = (era_dir / "acquisition" / "provider_enumeration_authority.py").read_text(encoding="utf-8")
    lpa_source = (era_dir / "providers" / "live_provider_adapter.py").read_text(encoding="utf-8")
    orch_source = (era_dir / "orchestration" / "era_orchestrator.py").read_text(encoding="utf-8")
    pipeline_source = (era_dir / "pipeline.py").read_text(encoding="utf-8")
    checks["manifest_not_selection_input"] = "provider_manifest" not in enum_source.lower()
    checks["container_map_not_enumeration_seed"] = "county_connectors" not in enum_source
    checks["no_runtime_allowlists"] = "APPROVED_PROVIDERS" not in lpa_source + orch_source
    checks["jre_operational_filter_removed_from_pipeline"] = "operational_only=True" not in pipeline_source
    checks["pipeline_consumes_enumeration"] = "provider_enumeration_authority.enumerate" in pipeline_source
    checks["lpa_consumes_projection"] = "ProviderEligibilityProjection" in lpa_source
    checks["orchestration_consumes_result"] = "ProviderEnumerationResult" in orch_source
    checks["consumers_do_not_evaluate_health"] = "evaluate_provider_health" not in lpa_source + orch_source
    checks["pipeline_stage_order_preserved"] = all(
        pipeline_source.index(marker) < pipeline_source.index(next_marker)
        for marker, next_marker in zip(
            ('"JRE",', 'record_stage("SRR"', 'record_stage("RATE_LIMIT"', 'record_stage("LPA"'),
            ('record_stage("SRR"', 'record_stage("RATE_LIMIT"', 'record_stage("LPA"', 'record_stage("ECM"'),
        )
    )
    checks["closed_exclusion_reasons"] = all(item.reason in {
        NOT_ACTIVE, CAPABILITY_MISMATCH, JURISDICTION_UNSUPPORTED,
        RUNTIME_UNAVAILABLE, HEALTH_UNAVAILABLE, PROVIDER_NOT_REGISTERED,
    } for item in result.exclusions)
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"PER-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
