import sys
from era.acquisition.providers.county.dallas_cad import DallasCADConnector
from era.acquisition.providers.county.county_framework_models import CountySearchRequest
from era.acquisition.providers.county import county_framework_errors as errors
def request(**overrides):
    data = {
        "property_id": "ERA-PR-2026-000001",
        "address": "5926 Sandhurst Ln Unit 224",
        "city": "Dallas",
        "county": "Dallas",
        "state": "TX",
        "parcel_apn": None,
    }
    data.update(overrides)
    return CountySearchRequest(**data)
tests = [
    ("EV-001", errors.COUNTY_INPUT_REQUIRED, lambda: DallasCADConnector().run(None)[0]),
    ("EV-002", errors.COUNTY_INPUT_REQUIRED, lambda: DallasCADConnector().run(request(property_id=""))[0]),
    ("EV-003", errors.COUNTY_NOT_SUPPORTED, lambda: DallasCADConnector().run(request(county="Tarrant"))[0]),
    ("EV-004", errors.READ_ONLY_COUNTY_CONNECTOR, lambda: DallasCADConnector().attempt_write()[1]),
    ("EV-005", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: DallasCADConnector().assign_confidence()[1]),
]
print("EAE-001.5 COUNTY CONNECTOR FRAMEWORK VERIFICATION")
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
connector = DallasCADConnector()
status1, evidence1 = connector.run(request())
status2, evidence2 = connector.run(request())
deterministic = (
    status1 == status2
    and len(evidence1) == len(evidence2)
    and [item.field_name for item in evidence1] == [item.field_name for item in evidence2]
    and [item.raw_value for item in evidence1] == [item.raw_value for item in evidence2]
)
print("EV-006")
print("  EXPECTED:", errors.DETERMINISTIC_COUNTY_RETRIEVAL)
print("  ACTUAL:  ", errors.DETERMINISTIC_COUNTY_RETRIEVAL if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
happy_ok = (
    status1 == errors.PASS
    and len(evidence1) >= 4
    and evidence1[0].property_id == "ERA-PR-2026-000001"
    and evidence1[0].connector_id == "COUNTY_DALLAS_CAD"
)
print("HAPPY PATH")
print("  STATUS:", status1)
print("  RAW COUNT:", len(evidence1))
print("  CONNECTOR:", evidence1[0].connector_id if evidence1 else None)
print("  FIRST FIELD:", evidence1[0].field_name if evidence1 else None)
print("  FIRST VALUE:", evidence1[0].raw_value if evidence1 else None)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(connector.audit.events))
for event in connector.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/6")
print("OVERALL:", "PASS" if passed == 6 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 6 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
