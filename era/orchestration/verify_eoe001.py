import sys
from era.orchestration.era_orchestrator import ERAOrchestrationEngine
from era.orchestration.orchestration_models import OrchestrationRequest
from era.orchestration import orchestration_errors as errors
from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.provider_health_authority import HEALTHY
from era.acquisition.provider_enumeration_authority import (
    NOT_ACTIVE,
    PROVIDER_NOT_REGISTERED,
    ProviderEligibilityProjection,
    ProviderEnumerationDetail,
    ProviderEnumerationResult,
    ProviderExclusion,
)
class MockConnector:
    def __init__(self, status_value="ACTIVE"):
        self.status = status_value
class MockSourceRegistry:
    def __init__(self, disabled=False):
        self.disabled = disabled
    def get_connector(self, provider_id):
        if self.disabled:
            return MockConnector("DISABLED")
        return MockConnector("ACTIVE")
class MockProvider:
    def __init__(self, status=errors.PASS, evidence=None):
        self.status = status
        self.evidence = evidence if evidence is not None else [
            {"field": "address", "value": "5926 Sandhurst Ln Unit 224"},
            {"field": "county", "value": "Dallas"},
        ]
    def retrieve(self, property_id):
        return self.status, self.evidence
class MockCanonical:
    def __init__(self, status=errors.PASS):
        self.status = status
    def canonicalize(self, raw_evidence):
        if self.status != errors.PASS:
            return self.status, []
        return errors.PASS, [
            {"field_name": item["field"], "normalized_value": item["value"]}
            for item in raw_evidence
        ]
class MockUPR:
    def __init__(self, status=errors.PASS):
        self.status = status
    def update_property(self, property_id, canonical_records):
        return self.status
class MockERI:
    def __init__(self, status=errors.PASS):
        self.status = status
    def trigger(self, property_id):
        return self.status
def build_engine(**overrides):
    source_registry = overrides.get("source_registry", MockSourceRegistry())
    providers = overrides.get("providers", {
        "COUNTY_DALLAS_CAD": MockProvider(),
    })
    canonical = overrides.get("canonical", MockCanonical())
    upr = overrides.get("upr", MockUPR())
    eri = overrides.get("eri", MockERI())
    eligibility_evaluator = overrides.get("eligibility_evaluator")
    if eligibility_evaluator is None:
        def eligibility_evaluator(provider_ids):
            eligible = []
            exclusions = []
            seeded = tuple(sorted(providers))
            for provider_id in provider_ids:
                if provider_id not in providers:
                    exclusions.append(ProviderExclusion(provider_id, PROVIDER_NOT_REGISTERED))
                    continue
                connector = source_registry.get_connector(provider_id)
                if connector is not None and getattr(connector.status, "value", connector.status) != "ACTIVE":
                    exclusions.append(ProviderExclusion(provider_id, NOT_ACTIVE))
                    continue
                eligible.append(ProviderEligibilityProjection(
                    provider_id, connector, providers[provider_id], ProviderHealth(True, HEALTHY)
                ))
            ids = tuple(item.provider_id for item in eligible)
            return ProviderEnumerationResult(
                eligible=tuple(eligible), exclusions=tuple(exclusions),
                detail=ProviderEnumerationDetail(
                    seeded=seeded, geographic_mappings=seeded,
                    after_lifecycle=ids, after_capability=ids,
                    after_geography=ids, after_runtime=ids, after_health=ids,
                ),
            )
    return ERAOrchestrationEngine(
        source_registry=source_registry,
        providers=providers,
        canonical=canonical,
        upr=upr,
        eri=eri,
        eligibility_evaluator=eligibility_evaluator,
    )
tests = [
    ("EV-001", errors.PROPERTY_REQUIRED, lambda: build_engine().run(OrchestrationRequest(property_id="", providers=["COUNTY_DALLAS_CAD"]))[0]),
    ("EV-002", errors.PROVIDER_REQUIRED, lambda: build_engine().run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=[]))[0]),
    ("EV-003", errors.PROVIDER_NOT_APPROVED, lambda: build_engine().run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=["ZILLOW_SCRAPE"]))[0]),
    ("EV-004", errors.PROVIDER_DISABLED, lambda: build_engine(source_registry=MockSourceRegistry(disabled=True)).run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=["COUNTY_DALLAS_CAD"]))[0]),
    ("EV-005", errors.PROVIDER_FAILED, lambda: build_engine(providers={"COUNTY_DALLAS_CAD": MockProvider(status="SOURCE_FAILED")}).run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=["COUNTY_DALLAS_CAD"]))[0]),
    ("EV-006", errors.NO_EVIDENCE_RETURNED, lambda: build_engine(providers={"COUNTY_DALLAS_CAD": MockProvider(evidence=[])}).run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=["COUNTY_DALLAS_CAD"]))[0]),
    ("EV-007", errors.CANONICALIZATION_FAILED, lambda: build_engine(canonical=MockCanonical(status="CANONICAL_FAIL")).run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=["COUNTY_DALLAS_CAD"]))[0]),
    ("EV-008", errors.UPR_UPDATE_FAILED, lambda: build_engine(upr=MockUPR(status="UPR_FAIL")).run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=["COUNTY_DALLAS_CAD"]))[0]),
    ("EV-009", errors.ERI_TRIGGER_FAILED, lambda: build_engine(eri=MockERI(status="ERI_FAIL")).run(OrchestrationRequest(property_id="ERA-PR-2026-000001", providers=["COUNTY_DALLAS_CAD"]))[0]),
    ("EV-010", errors.READ_ONLY_ORCHESTRATOR, lambda: build_engine().attempt_write()[1]),
    ("EV-011", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: build_engine().assign_confidence()[1]),
]
print("EOE-001 ERA ORCHESTRATION ENGINE VERIFICATION")
print("=" * 70)
passed = 0
for ev_id, expected, fn in tests:
    actual = fn()
    ok = actual == expected
    if ok:
        passed += 1
    print(ev_id)
    print("  EXPECTED:", expected)
    print("  ACTUAL:  ", actual)
    print("  PASS:    ", ok)
    print()
engine1 = build_engine()
status1, result1 = engine1.run(
    OrchestrationRequest(
        property_id="ERA-PR-2026-000001",
        providers=["COUNTY_DALLAS_CAD"],
    )
)
engine2 = build_engine()
status2, result2 = engine2.run(
    OrchestrationRequest(
        property_id="ERA-PR-2026-000001",
        providers=["COUNTY_DALLAS_CAD"],
    )
)
deterministic = (
    status1 == status2
    and result1 is not None
    and result2 is not None
    and result1.property_id == result2.property_id
    and result1.providers_run == result2.providers_run
    and result1.evidence_count == result2.evidence_count
    and result1.canonical_count == result2.canonical_count
)
print("EV-012")
print("  EXPECTED:", errors.DETERMINISTIC_ORCHESTRATION)
print("  ACTUAL:  ", errors.DETERMINISTIC_ORCHESTRATION if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
happy_ok = (
    status1 == errors.PASS
    and result1 is not None
    and result1.evidence_count == 2
    and result1.canonical_count == 2
    and result1.providers_run == ["COUNTY_DALLAS_CAD"]
)
print("HAPPY PATH")
print("  STATUS:", status1)
print("  PROPERTY:", result1.property_id if result1 else None)
print("  PROVIDERS:", result1.providers_run if result1 else None)
print("  EVIDENCE COUNT:", result1.evidence_count if result1 else None)
print("  CANONICAL COUNT:", result1.canonical_count if result1 else None)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(engine1.audit.events))
for event in engine1.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/12")
print("OVERALL:", "PASS" if passed == 12 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 12 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
