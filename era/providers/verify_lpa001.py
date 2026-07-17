import sys
from era.providers.live_provider_adapter import LiveProviderAdapter
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors as errors
from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.provider_health_authority import HEALTHY
from era.acquisition.provider_enumeration_authority import (
    HEALTH_UNAVAILABLE,
    ProviderEligibilityProjection,
    ProviderExclusion,
)
class MockProvider:
    def __init__(self, provider_id="COUNTY_DALLAS_CAD", health=True, evidence=True, provenance=True, source_reference=True):
        self._provider_id = provider_id
        self._health = health
        self._evidence = evidence
        self._provenance = provenance
        self._source_reference = source_reference
    def provider_id(self):
        return self._provider_id
    def provider_name(self):
        return "Dallas Central Appraisal District"
    def connector_version(self):
        return "1.0"
    def health_check(self):
        return self._health
    def retrieve(self, property_id):
        return errors.PASS, {
            "source_reference": "DCAD-PUBLIC-SEARCH" if self._source_reference else "",
            "provenance": {"legal_basis": "PUBLIC_RECORD"} if self._provenance else None,
            "evidence": [
                ProviderEvidence("address", "5926 Sandhurst Ln Unit 224"),
                ProviderEvidence("county", "Dallas"),
            ] if self._evidence else [],
        }
def adapter(provider):
    if provider.health_check():
        eligibility = ProviderEligibilityProjection(
            provider.provider_id(), object(), provider, ProviderHealth(True, HEALTHY)
        )
        return LiveProviderAdapter(provider, eligibility=eligibility)
    return LiveProviderAdapter(
        provider,
        exclusion=ProviderExclusion(provider.provider_id(), HEALTH_UNAVAILABLE),
    )
tests = [
    ("EV-001", errors.PROVIDER_REQUIRED, lambda: LiveProviderAdapter(None).run("ERA-PR-2026-000001")[0]),
    ("EV-002", errors.PROVIDER_UNAUTHORIZED, lambda: LiveProviderAdapter(
        MockProvider(provider_id="ZILLOW_SCRAPE"),
        eligibility=ProviderEligibilityProjection("COUNTY_DALLAS_CAD", object(), object(), ProviderHealth(True, HEALTHY)),
    ).run("ERA-PR-2026-000001")[0]),
    ("EV-003", errors.PROVIDER_UNAVAILABLE, lambda: adapter(MockProvider(health=False)).run("ERA-PR-2026-000001")[0]),
    ("EV-004", errors.EMPTY_EVIDENCE, lambda: adapter(MockProvider(evidence=False)).run("ERA-PR-2026-000001")[0]),
    ("EV-005", errors.PROVENANCE_MISSING, lambda: adapter(MockProvider(provenance=False)).run("ERA-PR-2026-000001")[0]),
    ("EV-006", errors.SOURCE_REFERENCE_MISSING, lambda: adapter(MockProvider(source_reference=False)).run("ERA-PR-2026-000001")[0]),
    ("EV-007", errors.READ_ONLY_PROVIDER, lambda: LiveProviderAdapter(MockProvider()).attempt_write()[1]),
    ("EV-008", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: LiveProviderAdapter(MockProvider()).assign_confidence()[1]),
]
print("LPA-001 LIVE PROVIDER ADAPTER VERIFICATION")
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
engine1 = adapter(MockProvider())
status1, pkg1 = engine1.run("ERA-PR-2026-000001")
engine2 = adapter(MockProvider())
status2, pkg2 = engine2.run("ERA-PR-2026-000001")
deterministic = (
    status1 == status2
    and pkg1.provider_id == pkg2.provider_id
    and pkg1.property_id == pkg2.property_id
    and len(pkg1.evidence) == len(pkg2.evidence)
    and [x.field_name for x in pkg1.evidence] == [x.field_name for x in pkg2.evidence]
    and [x.raw_value for x in pkg1.evidence] == [x.raw_value for x in pkg2.evidence]
)
print("EV-009")
print("  EXPECTED:", errors.DETERMINISTIC_PACKAGE)
print("  ACTUAL:  ", errors.DETERMINISTIC_PACKAGE if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
happy_ok = (
    status1 == errors.PASS
    and pkg1 is not None
    and pkg1.provider_id == "COUNTY_DALLAS_CAD"
    and len(pkg1.evidence) == 2
)
print("HAPPY PATH")
print("  STATUS:", status1)
print("  PROVIDER:", pkg1.provider_id if pkg1 else None)
print("  PROPERTY:", pkg1.property_id if pkg1 else None)
print("  EVIDENCE COUNT:", len(pkg1.evidence) if pkg1 else None)
print("  SOURCE REF:", pkg1.source_reference if pkg1 else None)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(engine1.audit.events))
for event in engine1.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/9")
print("OVERALL:", "PASS" if passed == 9 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 9 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
