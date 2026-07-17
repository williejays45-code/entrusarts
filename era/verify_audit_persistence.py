import sys
import os
import tempfile
from era.app import build_app, bootstrap_demo
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType

print("AUDIT PERSISTENCE VERIFICATION")
print("=" * 70)

identity = PropertyIdentity(
    property_id="ERA-PR-2026-000001",
    address="5926 Sandhurst Ln Unit 224", city="Dallas", state="TX",
    zip_code="75252", county="Dallas", parcel_apn="00000000000",
    latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)

checks = {}
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

EXPECTED_NAMESPACES = {
    "era.acquisition.source_reliability_registry",
    "era.jurisdiction.jurisdiction_registry",
    "era.providers.live_provider_adapter",
    "era.canonical.canonical_engine",
    "era.provenance.provenance_manager",
    "era.fusion.fusion_engine",
    "era.conflict.conflict_resolver",
    "era.property_record.unified_property_record",
    "era.decision.decision_engine",
    "era.policy.policy_engine",
    "era.export.export_engine",
    "era.dashboard.dashboard_engine",
}
# provider_manifest and api are wired for persistence (they get a real
# sink from the container) but run_property() itself never calls
# provider_manifest.register_provider() or api.get_*() -- those are
# exercised separately in verify_spine002.py. Their absence here reflects
# what actually ran, not a wiring gap.

try:
    # --- "process 1": run a full property through a persistence-backed
    # app, then let the instance go away entirely.
    app_a = build_app(persistence_path=db_path)
    bootstrap_demo(app_a)
    result = app_a.run_property(
        property_id=identity.property_id, identity=identity,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    checks["pipeline_ran_ok"] = result.ok
    store_a = app_a.c.persistence_store
    events_before = store_a.query_events(limit=1000)
    checks["events_written_during_run"] = len(events_before) > 0
    namespaces_before = {e["namespace"] for e in events_before}
    checks["multiple_engine_namespaces_present"] = len(namespaces_before) >= 10
    checks["all_expected_namespaces_present"] = EXPECTED_NAMESPACES.issubset(namespaces_before)
    del app_a  # simulate process exit -- nothing in memory survives this

    # --- "process 2": fresh container, same db file. Query the audit
    # trail with no in-memory engine instances involved at all -- this
    # is the actual "cross-engine, durable, queryable" audit trail the
    # original review found completely absent.
    from era.shared.persistence import SqliteStore
    store_b = SqliteStore(db_path)
    events_after = store_b.query_events(limit=1000)
    checks["events_queryable_after_restart"] = len(events_after) >= len(events_before)
    checks["event_counts_stable_across_restart"] = len(events_after) == len(events_before)

    # Spot-check a few specific event types landed under the right
    # namespace -- not just "some events exist somewhere."
    srr_events = store_b.query_events(namespace="era.acquisition.source_reliability_registry")
    dec_events = store_b.query_events(namespace="era.decision.decision_engine")
    exp_events = store_b.query_events(namespace="era.export.export_engine")
    checks["srr_events_persisted"] = any(e["event_type"] == "CONNECTOR_REGISTERED" for e in srr_events)
    checks["decision_events_persisted"] = any(e["event_type"] == "DECISION_RECORDED" for e in dec_events)
    checks["export_events_persisted"] = any(e["event_type"] == "EXPORT_COMPLETED" for e in exp_events)

    # provider_manifest and api are wired for persistence too, even
    # though run_property() doesn't happen to call them -- prove that
    # directly rather than just asserting their absence is fine.
    store_c = SqliteStore(db_path)
    app_c = build_app(persistence_path=db_path)
    app_c.c.api.health()
    from era.provider_network.provider_manifest_models import ProviderManifestEntry, ProviderHealth
    from era.provider_network.provider_manifest_enums import ProviderNetworkStatus, ProviderNetworkRole
    app_c.c.provider_manifest.register_provider(ProviderManifestEntry(
        provider_id="COUNTY_DALLAS_CAD", provider_name="Dallas CAD",
        state="TX", county="Dallas", role=ProviderNetworkRole.CAD,
        status=ProviderNetworkStatus.OPERATIONAL, public=True, read_only=True,
        legal_basis="PUBLIC_RECORD", version="1.0",
        health=ProviderHealth(success_rate=1.0, latency_ms=100, failures=0),
    ))
    api_events = store_c.query_events(namespace="era.api.api_engine")
    manifest_events = store_c.query_events(namespace="era.provider_network.provider_manifest")
    checks["api_namespace_persists_when_exercised"] = any(
        e["event_type"] == "API_REQUEST_RECORDED" for e in api_events
    )
    checks["provider_manifest_namespace_persists_when_exercised"] = any(
        e["event_type"] == "PROVIDER_REGISTERED" for e in manifest_events
    )

    # --- default (no store) behavior must be completely unaffected: an
    # app built without persistence_path still works exactly as before,
    # and touches no disk at all.
    plain_app = build_app()
    bootstrap_demo(plain_app)
    plain_result = plain_app.run_property(
        property_id=identity.property_id, identity=identity,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    checks["no_store_default_still_works"] = plain_result.ok
    checks["no_store_default_has_no_persistence_store"] = plain_app.c.persistence_store is None

finally:
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print("AUDIT PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
