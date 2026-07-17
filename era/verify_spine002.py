import sys
import os
import tempfile
from era.container import Container
from era.pipeline import Pipeline
from era.app import build_app, bootstrap_demo
from era.auth.token_store import MockTokenStore
from era.shared.persistence import SqliteStore
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType
from era.acquisition.connector_enums import ConnectorStatus
from era.jurisdiction.jurisdiction_models import JurisdictionRequest
from era.jurisdiction import jurisdiction_errors

print("SPINE-002 COMPOSITION ROOT VERIFICATION")
print("=" * 70)

checks = {}

identity = PropertyIdentity(
    property_id="ERA-PR-2026-000001",
    address="5926 Sandhurst Ln Unit 224", city="Dallas", state="TX",
    zip_code="75252", county="Dallas", parcel_apn="00000000000",
    latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)

# ---- 1. Happy path: full 13-stage run through a fresh in-memory app ----
app = build_app(token_store=MockTokenStore())
bootstrap_demo(app)
result = app.run_property(
    property_id=identity.property_id, identity=identity,
    state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
)

checks["pipeline_ok"] = result.ok
checks["all_expected_stages_present"] = {
    "JRE", "SRR", "LPA", "ECM", "EPM", "MSF", "ECR",
    "UPR_CREATE", "UPR_EVIDENCE", "DEC", "POL", "EXP", "DASH",
}.issubset({s.name for s in result.stages})
checks["all_stages_ok"] = all(s.ok for s in result.stages)
checks["canonical_records_produced"] = len(result.canonical_records) > 0
checks["provenance_records_produced"] = len(result.provenance_records) == len(result.canonical_records)
checks["fusion_ran"] = result.fusion_package is not None
checks["property_record_created"] = result.property_record is not None
checks["property_record_has_evidence"] = len(result.property_record.evidence) == len(result.provenance_records)
checks["decision_recorded"] = result.decision_record is not None
checks["policy_evaluated"] = result.policy_result is not None
checks["policy_saw_same_decision_as_dec"] = (
    result.policy_result.decision == result.decision_record.decision.value
)
checks["export_created"] = result.export_package is not None
checks["export_saw_same_verdict_as_pol"] = (
    result.export_package.policy_verdict == result.policy_result.verdict.value
    if result.export_package else False
)
checks["dashboard_built"] = result.dashboard_view is not None
checks["dashboard_has_all_required_cards"] = (
    len(result.dashboard_view.cards) == 8 if result.dashboard_view else False
)

# ---- 2. API is not an island: it must read exactly what the pipeline
# wrote, through the one shared store the container owns. ----
api_status, api_property = app.c.api.get_property("founder-token", identity.property_id)
api_dec_status, api_decision = app.c.api.get_decision("founder-token", identity.property_id)
api_pol_status, api_policy = app.c.api.get_policy("founder-token", identity.property_id)
api_exp_status, api_export = app.c.api.get_export("founder-token", identity.property_id)
api_audit_status, api_audit = app.c.api.get_audit("founder-token", identity.property_id)
checks["api_property_matches_pipeline"] = (
    api_status == "PASS" and api_property.data["property_id"] == identity.property_id
)
checks["api_decision_matches_pipeline"] = (
    api_dec_status == "PASS"
    and api_decision.data["decision"] == result.decision_record.decision.value
)
checks["api_policy_matches_pipeline"] = (
    api_pol_status == "PASS" and api_policy.data["verdict"] == result.policy_result.verdict.value
)
checks["api_export_matches_pipeline"] = (
    api_exp_status == "PASS" and api_export.data["export_id"] == result.export_package.export_id
)
checks["api_audit_nonempty_and_multi_engine"] = (
    api_audit_status == "PASS"
    and len(api_audit.data["audit"]) > 0
    and len({e["namespace"] for e in api_audit.data["audit"]}) >= 5
)

# ---- 3. Negative path: unregistered jurisdiction/provider must fail
# cleanly through JRE, not silently proceed or crash. ----
bad_app = build_app()
bad_result = bad_app.run_property(
    property_id="ERA-PR-2026-999999",
    identity=identity, state="TX", county="Nowhere County",
    provider_id="COUNTY_DALLAS_CAD",
)
checks["unregistered_jurisdiction_fails_cleanly"] = (
    not bad_result.ok and bad_result.stage("JRE") is not None and not bad_result.stage("JRE").ok
)

# ---- 4. Container correctly threads persistence through to SRR (C4 +
# SPINE-002 integration: composition root must actually plumb the store
# it's given, not silently drop it). ----
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)
try:
    persisted_app = build_app(persistence_path=db_path)
    bootstrap_demo(persisted_app)
    connector = persisted_app.c.srr.get_connector("COUNTY_DALLAS_CAD")
    checks["persistent_container_registers_connector"] = (
        connector is not None and connector.status == ConnectorStatus.ACTIVE
    )
    del persisted_app  # simulate process exit

    reopened_app = build_app(persistence_path=db_path)
    reopened_connector = reopened_app.c.srr.get_connector("COUNTY_DALLAS_CAD")
    checks["persistent_container_state_survives_restart"] = (
        reopened_connector is not None and reopened_connector.connector_id == "COUNTY_DALLAS_CAD"
    )
finally:
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)

# ---- 5. Default (in-memory) app is unaffected by persistence support
# existing elsewhere -- no accidental shared state between instances. ----
isolated_app_a = build_app()
isolated_app_b = build_app()
bootstrap_demo(isolated_app_a)
checks["containers_do_not_leak_state_across_instances"] = (
    isolated_app_a.c.srr.get_connector("COUNTY_DALLAS_CAD") is not None
    and isolated_app_b.c.srr.get_connector("COUNTY_DALLAS_CAD") is None
)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print("STAGE TRACE (happy path):")
for s in result.stages:
    print(f"  [{'OK' if s.ok else 'FAIL'}] {s.name}: {s.status}")
print()
print(f"SPINE-002 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
