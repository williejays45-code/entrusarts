"""CCS-001 fail-closed real-artifact verification.

This module is an executable verification gate, not a pytest module. Missing
configuration and source-access failures are mandatory-gate failures.
"""

import os
import sys

from era.app import build_app, bootstrap_collin_demo
from era.live_adapters.collin_bulk_data_adapter import CollinBulkDataAdapter
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record.property_models import PropertyIdentity


mdb_path = os.environ.get("ERA_COLLIN_MDB_PATH")
code_path = os.environ.get("ERA_COLLIN_CODE_LIST_PATH")
if not mdb_path or not code_path:
    print("COLLIN-BULK-ADAPTER-001: FAIL")
    print("configuration_present : FAIL")
    print("reason : set ERA_COLLIN_MDB_PATH and ERA_COLLIN_CODE_LIST_PATH")
    print("OVERALL: FAIL")
    raise SystemExit(1)

checks = {}
failure_reasons = {}


def check(name, operation):
    try:
        checks[name] = bool(operation())
        if not checks[name]:
            failure_reasons[name] = "check returned false"
    except Exception as exc:  # gate must report, not escape before its verdict
        checks[name] = False
        failure_reasons[name] = f"{type(exc).__name__}: {exc}"
    return checks[name]


adapter = CollinBulkDataAdapter(mdb_path, code_path)
check("mdb_source_opens", adapter.health_check)
check("ad_public_exact_row_count", lambda: adapter.source_row_count() == 503_711)

status, response = (None, {})
try:
    status, response = adapter.retrieve("37")
except Exception as exc:
    failure_reasons["real_prop_id_row_retrieved"] = f"{type(exc).__name__}: {exc}"
evidence = {item.field_name: item.raw_value for item in response.get("evidence", [])}
checks["real_prop_id_row_retrieved"] = status == "PASS" and evidence.get("source_record_id") == "37"
checks["geo_id_is_parcel_identifier"] = status == "PASS" and evidence.get("parcel_id") == "R-0002-00A-0030-1"
checks["situs_and_mailing_remain_distinct"] = (
    status == "PASS"
    and evidence.get("property_address") != evidence.get("owner_mailing_address")
    and evidence.get("city") == "PLANO"
    and evidence.get("owner_mailing_city") == "NASHVILLE"
)
checks["land_sqft_never_emitted"] = status == "PASS" and "land_sqft" not in evidence
checks["land_total_sqft_maps"] = status == "PASS" and evidence.get("land_area_sqft") == "49262.0"
checks["preliminary_current_values_map_conditionally"] = (
    status == "PASS"
    and evidence.get("property_status") == "Preliminary"
    and evidence.get("current_market_value") == "2600000"
    and "current_improvement_homesite_value" in evidence
    and "current_land_homesite_value" in evidence
    and "current_ten_percent_cap" in evidence
)
checks["certified_values_preserved"] = (
    status == "PASS"
    and evidence.get("certified_market_value") == "2200000"
    and "certified_improvement_homesite_value" in evidence
    and "certified_land_homesite_value" in evidence
    and "certified_ten_percent_cap" in evidence
)
checks["official_workbook_code_resolves"] = (
    status == "PASS"
    and evidence.get("state_code") == "F3"
    and evidence.get("state_description") == "Office Commercial - Real"
)

geo_status, geo_response = (None, {})
try:
    geo_status, geo_response = adapter.retrieve("R-0002-00A-0030-1")
except Exception as exc:
    failure_reasons["real_geo_id_lookup_works"] = f"{type(exc).__name__}: {exc}"
geo_evidence = {item.field_name: item.raw_value for item in geo_response.get("evidence", [])}
checks["real_geo_id_lookup_works"] = geo_status == "PASS" and geo_evidence.get("source_record_id") == "37"

def verify_pipeline():
    app = build_app(collin_mdb_path=mdb_path, collin_code_list_path=code_path, use_mock_auth=True)
    bootstrap_collin_demo(app)
    identity = PropertyIdentity(
        property_id="R-0002-00A-0030-1", address="1630 COIT RD", city="PLANO",
        state="TX", zip_code="75075", county="Collin", parcel_apn="R-0002-00A-0030-1",
        latitude=None, longitude=None, property_type=PropertyType.CONDO,
        strategy_type=StrategyType.LONG_TERM_RENTAL,
    )
    before = app.c.srr.get_connector("COLLIN_BULK_MDB").success_count
    result = app.run_property(identity.property_id, identity, "TX", "Collin", "COLLIN_BULK_MDB")
    after = app.c.srr.get_connector("COLLIN_BULK_MDB").success_count
    checks["existing_evidence_validation_passes"] = (
        result.stage("LPA") is not None and result.stage("LPA").ok
        and result.stage("ECM") is not None and result.stage("ECM").ok
        and not any(stage.name.startswith("ECM:") for stage in result.stages)
    )
    checks["pipeline_is_sole_srr_authority"] = after - before == 1


try:
    verify_pipeline()
except Exception as exc:
    reason = f"{type(exc).__name__}: {exc}"
    checks["existing_evidence_validation_passes"] = False
    checks["pipeline_is_sole_srr_authority"] = False
    failure_reasons["existing_evidence_validation_passes"] = reason
    failure_reasons["pipeline_is_sole_srr_authority"] = reason

passed = sum(bool(value) for value in checks.values())
for name, value in checks.items():
    print(name, ":", "PASS" if value else "FAIL")
    if not value and name in failure_reasons:
        print("  reason:", failure_reasons[name])
print(f"COLLIN-BULK-ADAPTER-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
