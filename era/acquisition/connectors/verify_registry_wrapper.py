import sys
from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
from era.acquisition.connectors.metadata import ConnectorMetadata
from era.acquisition.connectors.registry import ConnectorRegistryWrapper
from era.acquisition.connectors import registry_errors as wrapper_errors
from era.acquisition import connector_errors as srr_errors
def metadata(**overrides):
    data = {
        "connector_id": "COUNTY_TARRANT_ASSESSOR",
        "provider_name": "Tarrant County Assessor",
        "version": "1.0",
        "category": ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        "legal_classification": LegalClassification.PUBLIC_RECORD,
        "status": ConnectorStatus.ACTIVE,
        "capabilities": [
            "OWNERSHIP",
            "PARCEL",
            "TAX_ASSESSMENT",
            "BUILDING_SIZE",
            "LOT_SIZE",
            "YEAR_BUILT",
        ],
        "refresh_schedule_hours": 24,
        "rate_limit_per_day": 500,
        "cache_duration_hours": 24,
        "monthly_budget_limit": 0.0,
        "max_requests": 500,
        "max_retries": 2,
        "retry_delay_seconds": 10,
    }
    data.update(overrides)
    return ConnectorMetadata(**data)
srr = SourceReliabilityRegistry()
wrapper = ConnectorRegistryWrapper(srr)
tests = [
    ("EV-001", wrapper_errors.CONNECTOR_METADATA_REQUIRED, lambda: wrapper.register_metadata(None)[0]),
    ("EV-002", srr_errors.CONNECTOR_REQUIRED, lambda: wrapper.register_metadata(metadata(connector_id=""))[0]),
    ("EV-003", srr_errors.LEGAL_CLASSIFICATION_REQUIRED, lambda: wrapper.register_metadata(metadata(connector_id="BAD-LEGAL", legal_classification="PUBLIC"))[0]),
    ("EV-004", srr_errors.RESOURCE_POLICY_REQUIRED, lambda: wrapper.register_metadata(metadata(connector_id="BAD-RATE", rate_limit_per_day=0))[0]),
    ("EV-005", srr_errors.REFRESH_POLICY_REQUIRED, lambda: wrapper.register_metadata(metadata(connector_id="BAD-REFRESH", refresh_schedule_hours=0))[0]),
    ("EV-006", srr_errors.UNKNOWN_CAPABILITY, lambda: wrapper.register_metadata(metadata(connector_id="BAD-CAP", capabilities=["ALIEN_SIGNAL"]))[0]),
    ("EV-007", wrapper_errors.PARALLEL_REGISTRY_FORBIDDEN, lambda: wrapper.forbidden_parallel_registry_write()[1]),
]
print("EAE-001.2 CONNECTOR REGISTRY WRAPPER VERIFICATION")
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
status, registered = wrapper.register_metadata(metadata())
dup_status, dup = wrapper.register_metadata(metadata())
print("EV-008")
print("  EXPECTED:", srr_errors.DUPLICATE_CONNECTOR)
print("  ACTUAL:  ", dup_status)
print("  PASS:    ", dup_status == srr_errors.DUPLICATE_CONNECTOR)
print()
if dup_status == srr_errors.DUPLICATE_CONNECTOR:
    passed += 1
disable_status = wrapper.disable_connector("COUNTY_TARRANT_ASSESSOR")
disabled = wrapper.get_connector("COUNTY_TARRANT_ASSESSOR").status == ConnectorStatus.DISABLED
print("EV-009")
print("  EXPECTED:", "DISABLED VIA SRR")
print("  ACTUAL:  ", "DISABLED VIA SRR" if disabled else "STATUS_NOT_CHANGED")
print("  PASS:    ", disable_status == srr_errors.PASS and disabled)
print()
if disable_status == srr_errors.PASS and disabled:
    passed += 1
enable_status = wrapper.enable_connector("COUNTY_TARRANT_ASSESSOR")
enabled = wrapper.get_connector("COUNTY_TARRANT_ASSESSOR").status == ConnectorStatus.ACTIVE
print("EV-010")
print("  EXPECTED:", "ACTIVE VIA SRR")
print("  ACTUAL:  ", "ACTIVE VIA SRR" if enabled else "STATUS_NOT_CHANGED")
print("  PASS:    ", enable_status == srr_errors.PASS and enabled)
print()
if enable_status == srr_errors.PASS and enabled:
    passed += 1
happy_ok = (
    status == wrapper_errors.PASS
    and registered is not None
    and wrapper.get_connector("COUNTY_TARRANT_ASSESSOR") is not None
    and wrapper.get_connector("COUNTY_TARRANT_ASSESSOR").connector_id == "COUNTY_TARRANT_ASSESSOR"
    and len(wrapper.source_registry.connectors) == 1
)
print("HAPPY PATH")
print("  STATUS:", status)
print("  CONNECTOR:", registered.connector_id if registered else None)
print("  SRR CONNECTOR COUNT:", len(wrapper.source_registry.connectors))
print("  WRAPPER HAS OWN STORE:", hasattr(wrapper, 'connectors'))
print("  PASS:", happy_ok and not hasattr(wrapper, 'connectors'))
print()
print("SRR AUDIT EVENTS:", len(srr.audit.events))
for event in srr.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/10")
print("OVERALL:", "PASS" if passed == 10 and happy_ok and not hasattr(wrapper, 'connectors') else "FAIL")
_ERA_OVERALL_OK = (passed == 10 and happy_ok and not hasattr(wrapper, 'connectors'))
if not _ERA_OVERALL_OK:
    sys.exit(1)
