import sys
from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
from era.acquisition.providers.county.tarrant_assessor import TarrantCountyAssessorConnector
from era.acquisition.providers.county.county_models import CountyConnectorRequest
from era.acquisition.providers.county import county_errors as errors
def register_tarrant(status=ConnectorStatus.ACTIVE, legal=LegalClassification.PUBLIC_RECORD):
    srr = SourceReliabilityRegistry()
    connector = ConnectorRecord(
        connector_id="COUNTY_TARRANT_ASSESSOR",
        provider_name="Tarrant County Assessor",
        version="1.0",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        legal_classification=legal,
        status=status,
        capabilities=[
            "OWNERSHIP",
            "PARCEL",
            "TAX_ASSESSMENT",
            "BUILDING_SIZE",
            "LOT_SIZE",
            "YEAR_BUILT",
        ],
        resource_policy=ResourcePolicy(
            refresh_schedule_hours=24,
            rate_limit_per_day=500,
            cache_duration_hours=24,
            monthly_budget_limit=0.0,
            max_requests=500,
        ),
        retry_policy=RetryPolicy(
            max_retries=2,
            retry_delay_seconds=10,
        ),
    )
    srr.register_connector(connector)
    return srr
def request(**overrides):
    data = {
        "property_id": "ERA-PR-2026-000001",
        "address": "5926 Sandhurst Ln Unit 224",
        "county": "Tarrant",
        "state": "TX",
        "parcel_apn": None,
    }
    data.update(overrides)
    return CountyConnectorRequest(**data)
tests = [
    ("EV-001", errors.CONNECTOR_INPUT_REQUIRED, lambda: TarrantCountyAssessorConnector(register_tarrant()).retrieve(None)[0]),
    ("EV-002", errors.CONNECTOR_INPUT_REQUIRED, lambda: TarrantCountyAssessorConnector(SourceReliabilityRegistry()).retrieve(request())[0]),
    ("EV-003", errors.CONNECTOR_NOT_ACTIVE, lambda: TarrantCountyAssessorConnector(register_tarrant(status=ConnectorStatus.DISABLED)).retrieve(request())[0]),
    ("EV-004", errors.LEGAL_SOURCE_REQUIRED, lambda: TarrantCountyAssessorConnector(register_tarrant(legal=LegalClassification.LICENSED)).retrieve(request())[0]),
    ("EV-005", errors.READ_ONLY_CONNECTOR, lambda: TarrantCountyAssessorConnector(register_tarrant()).attempt_write()[1]),
    ("EV-006", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: TarrantCountyAssessorConnector(register_tarrant()).assign_confidence()[1]),
]
print("EAE-001.3 TARRANT COUNTY CONNECTOR VERIFICATION")
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
srr = register_tarrant()
connector = TarrantCountyAssessorConnector(srr)
status1, raw1 = connector.retrieve(request())
status2, raw2 = connector.retrieve(request())
deterministic = (
    status1 == status2
    and len(raw1) == len(raw2)
    and [x.field_name for x in raw1] == [x.field_name for x in raw2]
    and [x.raw_value for x in raw1] == [x.raw_value for x in raw2]
)
print("EV-007")
print("  EXPECTED:", errors.DETERMINISTIC_RETRIEVAL)
print("  ACTUAL:  ", errors.DETERMINISTIC_RETRIEVAL if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
happy_ok = (
    status1 == errors.PASS
    and len(raw1) == 3
    and raw1[0].property_id == "ERA-PR-2026-000001"
    and raw1[0].connector_id == "COUNTY_TARRANT_ASSESSOR"
)
print("HAPPY PATH")
print("  STATUS:", status1)
print("  RAW COUNT:", len(raw1))
print("  CONNECTOR:", raw1[0].connector_id if raw1 else None)
print("  FIRST FIELD:", raw1[0].field_name if raw1 else None)
print("  FIRST VALUE:", raw1[0].raw_value if raw1 else None)
print("  SRR SUCCESS RATE:", srr.get_connector("COUNTY_TARRANT_ASSESSOR").success_rate)
print("  PASS:", happy_ok)
print()
print("CONNECTOR AUDIT EVENTS:", len(connector.audit.events))
for event in connector.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/7")
print("OVERALL:", "PASS" if passed == 7 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 7 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
