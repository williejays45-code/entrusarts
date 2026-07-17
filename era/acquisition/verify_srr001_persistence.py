import sys
import os
import tempfile
from era.shared.persistence import SqliteStore
from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
from era.acquisition import connector_errors as errors


def connector(**overrides):
    data = {
        "connector_id": "COUNTY_TARRANT_ASSESSOR",
        "provider_name": "Tarrant County Assessor",
        "version": "1.0",
        "category": ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        "legal_classification": LegalClassification.PUBLIC_RECORD,
        "status": ConnectorStatus.ACTIVE,
        "capabilities": ["OWNERSHIP", "PARCEL", "TAX_ASSESSMENT"],
        "resource_policy": ResourcePolicy(
            refresh_schedule_hours=24, rate_limit_per_day=500,
            cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=500,
        ),
        "retry_policy": RetryPolicy(max_retries=2, retry_delay_seconds=10),
    }
    data.update(overrides)
    return ConnectorRecord(**data)


print("SRR-001 PERSISTENCE VERIFICATION (C4)")
print("=" * 70)

db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)  # start clean; SqliteStore creates schema on connect

checks = {}
try:
    # --- "process 1": register a connector, record activity, then the
    # process/instance goes away. Nothing is kept in this script's memory
    # past this block on purpose -- store is the only thing that persists.
    store_a = SqliteStore(db_path)
    registry_a = SourceReliabilityRegistry(store=store_a)
    status, registered = registry_a.register_connector(connector())
    checks["register_ok"] = status == errors.PASS and registered is not None
    registry_a.record_success("COUNTY_TARRANT_ASSESSOR", 120)
    registry_a.disable_connector("COUNTY_TARRANT_ASSESSOR")
    events_before_restart = len(store_a.query_events(namespace="era.acquisition.source_reliability_registry"))
    checks["events_written_before_restart"] = events_before_restart >= 3
    del registry_a  # simulate process exit -- no reference to in-memory state survives

    # --- "process 2": brand-new SourceReliabilityRegistry instance,
    # same db_path. If this reflects prior state, persistence is real,
    # not just an in-memory dict that happens to still be reachable.
    store_b = SqliteStore(db_path)
    registry_b = SourceReliabilityRegistry(store=store_b)
    reloaded = registry_b.get_connector("COUNTY_TARRANT_ASSESSOR")
    checks["state_survived_restart"] = reloaded is not None
    checks["status_survived_restart"] = reloaded.status == ConnectorStatus.DISABLED if reloaded else False
    checks["success_count_survived_restart"] = reloaded.success_count == 1 if reloaded else False
    checks["average_response_time_survived_restart"] = reloaded.average_response_time_ms == 120 if reloaded else False

    events_after_restart = store_b.query_events(namespace="era.acquisition.source_reliability_registry")
    checks["audit_events_queryable_after_restart"] = len(events_after_restart) >= events_before_restart
    checks["audit_event_types_present"] = {"CONNECTOR_REGISTERED", "CONNECTOR_COMPLETED", "CONNECTOR_DISABLED"}.issubset(
        {e["event_type"] for e in events_after_restart}
    )

    # --- default behavior (no store) is unchanged: pure in-memory, does
    # not touch disk at all.
    registry_c = SourceReliabilityRegistry()
    status_c, _ = registry_c.register_connector(connector())
    checks["no_store_default_still_works"] = status_c == errors.PASS
    checks["no_store_default_has_no_store_attr_set"] = registry_c.store is None

finally:
    if os.path.exists(db_path):
        os.remove(db_path)
    for ext in ("-wal", "-shm"):
        if os.path.exists(db_path + ext):
            os.remove(db_path + ext)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print("PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
