import sys
from era.provider_network.provider_manifest import ProviderManifest
from era.provider_network.provider_manifest_models import ProviderManifestEntry, ProviderHealth
from era.provider_network.provider_manifest_enums import ProviderNetworkStatus, ProviderNetworkRole
from era.provider_network import provider_manifest_errors as errors
def provider(provider_id, name, county, role=ProviderNetworkRole.CAD, status=ProviderNetworkStatus.REGISTERED):
    return ProviderManifestEntry(
        provider_id=provider_id,
        provider_name=name,
        state="TX",
        county=county,
        role=role,
        status=status,
        public=True,
        read_only=True,
        legal_basis="PUBLIC_RECORD",
        version="1.0",
        health=ProviderHealth(
            success_rate=0.0 if status != ProviderNetworkStatus.OPERATIONAL else 1.0,
            latency_ms=0,
            failures=0,
            last_success=None,
        ),
    )
def load_provider_pack(manifest):
    providers = [
        provider("COUNTY_DALLAS_CAD", "Dallas CAD", "Dallas", status=ProviderNetworkStatus.OPERATIONAL),
        provider("DALLAS_TAX_OFFICE", "Dallas Tax Office", "Dallas", ProviderNetworkRole.TAX),
        provider("DALLAS_COUNTY_CLERK", "Dallas County Clerk", "Dallas", ProviderNetworkRole.CLERK),
        provider("COUNTY_TARRANT_CAD", "Tarrant CAD", "Tarrant"),
        provider("TARRANT_TAX_OFFICE", "Tarrant Tax Office", "Tarrant", ProviderNetworkRole.TAX),
        provider("TARRANT_COUNTY_CLERK", "Tarrant County Clerk", "Tarrant", ProviderNetworkRole.CLERK),
        provider("COUNTY_COLLIN_CAD", "Collin CAD", "Collin"),
        provider("COLLIN_TAX_OFFICE", "Collin Tax Office", "Collin", ProviderNetworkRole.TAX),
        provider("COLLIN_COUNTY_CLERK", "Collin County Clerk", "Collin", ProviderNetworkRole.CLERK),
        provider("COUNTY_DENTON_CAD", "Denton CAD", "Denton"),
        provider("COUNTY_ROCKWALL_CAD", "Rockwall CAD", "Rockwall"),
        provider("COUNTY_PARKER_CAD", "Parker CAD", "Parker"),
        provider("COUNTY_ELLIS_CAD", "Ellis CAD", "Ellis"),
        provider("COUNTY_KAUFMAN_CAD", "Kaufman CAD", "Kaufman"),
        provider("COUNTY_JOHNSON_CAD", "Johnson CAD", "Johnson"),
        provider("COUNTY_HARRIS_CAD", "Harris CAD", "Harris"),
    ]
    for item in providers:
        status = manifest.register_provider(item)
        if status != errors.PASS:
            return status
    return errors.PASS
manifest = ProviderManifest()
tests = [
    ("EV-001", errors.PROVIDER_REQUIRED, lambda: manifest.register_provider(None)),
    ("EV-002", errors.PROVIDER_ID_REQUIRED, lambda: manifest.register_provider(provider("", "Bad Provider", "Dallas"))),
    ("EV-003", errors.INVALID_STATUS, lambda: manifest.register_provider(provider("BAD_STATUS", "Bad Status", "Dallas", status="ACTIVE"))),
    ("EV-004", errors.INVALID_ROLE, lambda: manifest.register_provider(provider("BAD_ROLE", "Bad Role", "Dallas", role="APPRAISAL"))),
    ("EV-005", errors.READ_ONLY_MANIFEST, lambda: manifest.attempt_write()[1]),
    ("EV-006", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: manifest.assign_confidence()[1]),
]
print("EPP-002 PROVIDER MANIFEST VERIFICATION")
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
load_status = load_provider_pack(manifest)
print("EV-007")
print("  EXPECTED:", errors.PASS)
print("  ACTUAL:  ", load_status)
print("  PASS:    ", load_status == errors.PASS)
print()
if load_status == errors.PASS:
    passed += 1
dup_status = manifest.register_provider(provider("COUNTY_DALLAS_CAD", "Dallas CAD Duplicate", "Dallas"))
print("EV-008")
print("  EXPECTED:", errors.DUPLICATE_PROVIDER)
print("  ACTUAL:  ", dup_status)
print("  PASS:    ", dup_status == errors.DUPLICATE_PROVIDER)
print()
if dup_status == errors.DUPLICATE_PROVIDER:
    passed += 1
unknown_status = manifest.update_status("UNKNOWN_PROVIDER", ProviderNetworkStatus.OPERATIONAL)
print("EV-009")
print("  EXPECTED:", errors.UNKNOWN_PROVIDER)
print("  ACTUAL:  ", unknown_status)
print("  PASS:    ", unknown_status == errors.UNKNOWN_PROVIDER)
print()
if unknown_status == errors.UNKNOWN_PROVIDER:
    passed += 1
update_status = manifest.update_status("COUNTY_TARRANT_CAD", ProviderNetworkStatus.VERIFIED)
updated = manifest.get_provider("COUNTY_TARRANT_CAD").status == ProviderNetworkStatus.VERIFIED
print("EV-010")
print("  EXPECTED:", errors.PASS)
print("  ACTUAL:  ", update_status)
print("  STATUS UPDATED:", updated)
print("  PASS:    ", update_status == errors.PASS and updated)
print()
if update_status == errors.PASS and updated:
    passed += 1
manifest_a = ProviderManifest()
manifest_b = ProviderManifest()
load_provider_pack(manifest_a)
load_provider_pack(manifest_b)
deterministic = (
    sorted(manifest_a.providers.keys()) == sorted(manifest_b.providers.keys())
    and [p.provider_id for p in manifest_a.list_by_state("TX")] == [p.provider_id for p in manifest_b.list_by_state("tx")]
)
print("EV-011")
print("  EXPECTED:", errors.DETERMINISTIC_MANIFEST)
print("  ACTUAL:  ", errors.DETERMINISTIC_MANIFEST if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
operational = manifest.list_operational()
texas = manifest.list_by_state("TX")
happy_ok = (
    len(manifest.providers) == 16
    and len(texas) == 16
    and len(operational) == 1
    and operational[0].provider_id == "COUNTY_DALLAS_CAD"
)
print("HAPPY PATH")
print("  TOTAL PROVIDERS:", len(manifest.providers))
print("  TEXAS PROVIDERS:", len(texas))
print("  OPERATIONAL:", [p.provider_id for p in operational])
print("  TARRANT STATUS:", manifest.get_provider("COUNTY_TARRANT_CAD").status.value)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(manifest.audit.events))
for event in manifest.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/11")
print("OVERALL:", "PASS" if passed == 11 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 11 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
