import sys
from era.jurisdiction.jurisdiction_registry import JurisdictionRegistry
from era.jurisdiction.jurisdiction_models import JurisdictionRecord, JurisdictionProvider, JurisdictionRequest
from era.jurisdiction.jurisdiction_enums import ProviderOperationalStatus, ProviderRole
from era.jurisdiction import jurisdiction_errors as errors
def provider(provider_id, provider_name, role, status=ProviderOperationalStatus.NOT_OPERATIONAL):
    return JurisdictionProvider(
        provider_id=provider_id,
        provider_name=provider_name,
        role=role,
        status=status,
    )
def record(state="TX", county="Dallas", providers=None):
    return JurisdictionRecord(
        state=state,
        county=county,
        providers=providers if providers is not None else [
            provider("COUNTY_DALLAS_CAD", "Dallas CAD", ProviderRole.CAD, ProviderOperationalStatus.OPERATIONAL),
            provider("DALLAS_TAX_OFFICE", "Dallas Tax Office", ProviderRole.TAX),
            provider("DALLAS_COUNTY_CLERK", "Dallas County Clerk", ProviderRole.CLERK),
        ],
    )
def load_provider_pack_001(registry):
    counties = {
        "Dallas": [
            provider("COUNTY_DALLAS_CAD", "Dallas CAD", ProviderRole.CAD, ProviderOperationalStatus.OPERATIONAL),
            provider("DALLAS_TAX_OFFICE", "Dallas Tax Office", ProviderRole.TAX),
            provider("DALLAS_COUNTY_CLERK", "Dallas County Clerk", ProviderRole.CLERK),
        ],
        "Tarrant": [
            provider("COUNTY_TARRANT_CAD", "Tarrant CAD", ProviderRole.CAD),
            provider("TARRANT_TAX_OFFICE", "Tarrant Tax Office", ProviderRole.TAX),
            provider("TARRANT_COUNTY_CLERK", "Tarrant County Clerk", ProviderRole.CLERK),
        ],
        "Collin": [
            provider("COUNTY_COLLIN_CAD", "Collin CAD", ProviderRole.CAD),
            provider("COLLIN_TAX_OFFICE", "Collin Tax Office", ProviderRole.TAX),
            provider("COLLIN_COUNTY_CLERK", "Collin County Clerk", ProviderRole.CLERK),
        ],
        "Denton": [
            provider("COUNTY_DENTON_CAD", "Denton CAD", ProviderRole.CAD),
            provider("DENTON_TAX_OFFICE", "Denton Tax Office", ProviderRole.TAX),
            provider("DENTON_COUNTY_CLERK", "Denton County Clerk", ProviderRole.CLERK),
        ],
        "Rockwall": [
            provider("COUNTY_ROCKWALL_CAD", "Rockwall CAD", ProviderRole.CAD),
        ],
        "Parker": [
            provider("COUNTY_PARKER_CAD", "Parker CAD", ProviderRole.CAD),
        ],
        "Ellis": [
            provider("COUNTY_ELLIS_CAD", "Ellis CAD", ProviderRole.CAD),
        ],
        "Kaufman": [
            provider("COUNTY_KAUFMAN_CAD", "Kaufman CAD", ProviderRole.CAD),
        ],
        "Johnson": [
            provider("COUNTY_JOHNSON_CAD", "Johnson CAD", ProviderRole.CAD),
        ],
        "Harris": [
            provider("COUNTY_HARRIS_CAD", "Harris CAD", ProviderRole.CAD),
        ],
    }
    for county, providers in counties.items():
        status = registry.register_jurisdiction(
            JurisdictionRecord(
                state="TX",
                county=county,
                providers=providers,
            )
        )
        if status != errors.PASS:
            return status
    return errors.PASS
registry = JurisdictionRegistry()
tests = [
    ("EV-001", errors.JURISDICTION_REQUIRED, lambda: registry.register_jurisdiction(None)),
    ("EV-002", errors.STATE_REQUIRED, lambda: registry.register_jurisdiction(record(state=""))),
    ("EV-003", errors.COUNTY_REQUIRED, lambda: registry.register_jurisdiction(record(county=""))),
    ("EV-004", errors.PROVIDER_REQUIRED, lambda: registry.register_jurisdiction(record(county="NoProviders", providers=[]))),
    ("EV-005", errors.DUPLICATE_PROVIDER, lambda: registry.register_jurisdiction(record(county="DupProvider", providers=[
        provider("COUNTY_DUP_CAD", "Dup CAD", ProviderRole.CAD),
        provider("COUNTY_DUP_CAD", "Dup CAD Again", ProviderRole.CAD),
    ]))),
    ("EV-006", errors.READ_ONLY_JURISDICTION, lambda: registry.attempt_write()[1]),
    ("EV-007", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: registry.assign_confidence()[1]),
]
print("JRE-001 JURISDICTION REGISTRY VERIFICATION")
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
load_status = load_provider_pack_001(registry)
print("EV-008")
print("  EXPECTED:", errors.PASS)
print("  ACTUAL:  ", load_status)
print("  PASS:    ", load_status == errors.PASS)
print()
if load_status == errors.PASS:
    passed += 1
dup_jurisdiction = registry.register_jurisdiction(record(county="Dallas"))
print("EV-009")
print("  EXPECTED:", errors.DUPLICATE_JURISDICTION)
print("  ACTUAL:  ", dup_jurisdiction)
print("  PASS:    ", dup_jurisdiction == errors.DUPLICATE_JURISDICTION)
print()
if dup_jurisdiction == errors.DUPLICATE_JURISDICTION:
    passed += 1
missing_status, missing_providers = registry.resolve(
    JurisdictionRequest(state="TX", county="Unknown")
)
print("EV-010")
print("  EXPECTED:", errors.JURISDICTION_NOT_FOUND)
print("  ACTUAL:  ", missing_status)
print("  PASS:    ", missing_status == errors.JURISDICTION_NOT_FOUND)
print()
if missing_status == errors.JURISDICTION_NOT_FOUND:
    passed += 1
resolver_a_status, providers_a = registry.resolve(
    JurisdictionRequest(state="TX", county="Dallas")
)
resolver_b_status, providers_b = registry.resolve(
    JurisdictionRequest(state="tx", county="dallas")
)
deterministic = (
    resolver_a_status == resolver_b_status
    and [p.provider_id for p in providers_a] == [p.provider_id for p in providers_b]
)
print("EV-011")
print("  EXPECTED:", errors.DETERMINISTIC_RESOLUTION)
print("  ACTUAL:  ", errors.DETERMINISTIC_RESOLUTION if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
operational_status, operational = registry.resolve(
    JurisdictionRequest(state="TX", county="Dallas"),
    operational_only=True,
)
happy_ok = (
    resolver_a_status == errors.PASS
    and len(providers_a) == 3
    and providers_a[0].provider_id == "COUNTY_DALLAS_CAD"
    and operational_status == errors.PASS
    and len(operational) == 1
    and operational[0].provider_id == "COUNTY_DALLAS_CAD"
)
print("HAPPY PATH")
print("  STATUS:", resolver_a_status)
print("  PROVIDERS:", [p.provider_id for p in providers_a])
print("  OPERATIONAL ONLY:", [p.provider_id for p in operational])
print("  TOTAL JURISDICTIONS:", len(registry.records))
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(registry.audit.events))
for event in registry.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/11")
print("OVERALL:", "PASS" if passed == 11 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 11 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
