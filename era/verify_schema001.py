import sys
import os
import sqlite3
import tempfile
from era.shared.persistence import (
    SqliteStore, SchemaVersionError, RECORDS_SCHEMA_VERSION, AUDIT_SCHEMA_VERSION,
)

print("SCHEMA-001 VERIFICATION")
print("=" * 70)

checks = {}


def fresh_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    return path


def cleanup(path):
    for suffix in ("", "-wal", "-shm", ".audit.db", ".audit.db-wal", ".audit.db-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


# --- 1. Fresh DB: no schema_meta row exists yet. Opening should apply
# every migration from scratch and land on the current version. ---
path_fresh = fresh_path()
try:
    store = SqliteStore(path_fresh)
    checks["fresh_db_records_at_current_version"] = store.get_schema_version() == RECORDS_SCHEMA_VERSION
    checks["fresh_db_audit_at_current_version"] = (
        store.get_schema_version(audit=True) == AUDIT_SCHEMA_VERSION
    )
    checks["fresh_db_records_table_usable"] = True
    try:
        store.save_record("test_table", "id-1", {"x": 1})
        checks["fresh_db_records_table_usable"] = store.load_record("test_table", "id-1") == {"x": 1}
    except Exception:
        checks["fresh_db_records_table_usable"] = False
finally:
    cleanup(path_fresh)

# --- 2. Existing DB: a database already at an OLDER real version (1,
# not 2) must migrate forward to the current version on next open, not
# silently stay behind and not re-run migration 1. ---
path_existing = fresh_path()
try:
    # Simulate "a database written by an older build of this code" by
    # applying only migration 1 by hand, via a raw connection -- not
    # going through SqliteStore, since SqliteStore always brings a file
    # fully up to date on construction.
    raw = sqlite3.connect(path_existing)
    raw.execute(
        "CREATE TABLE schema_meta (id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)"
    )
    raw.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    raw.execute(
        "CREATE TABLE records (table_name TEXT NOT NULL, record_id TEXT NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (table_name, record_id))"
    )
    raw.execute("INSERT INTO schema_meta (id, version) VALUES (1, 1)")
    raw.execute(
        "INSERT INTO schema_migrations (version, description, applied_at) VALUES (1, 'create records table', '2026-01-01T00:00:00+00:00')"
    )
    # Seed a real business record under the old schema, to prove
    # migration doesn't touch or lose existing data.
    raw.execute(
        "INSERT INTO records (table_name, record_id, data, updated_at) VALUES ('legacy_table', 'legacy-1', '{\"pre_migration\": true}', '2026-01-01T00:00:00+00:00')"
    )
    raw.commit()
    raw.close()

    store = SqliteStore(path_existing)
    checks["existing_db_migrated_to_current_version"] = store.get_schema_version() == RECORDS_SCHEMA_VERSION
    history = store.get_migration_history()
    checks["existing_db_did_not_rerun_migration_1"] = (
        sum(1 for h in history if h["version"] == 1) == 1
    )
    checks["existing_db_applied_migration_2_in_order"] = (
        any(h["version"] == 2 for h in history)
        and history[-1]["version"] == 2
        and history[0]["version"] == 1
    )
    checks["existing_db_preserved_prior_data"] = (
        store.load_record("legacy_table", "legacy-1") == {"pre_migration": True}
    )
    # And the new index from migration 2 genuinely exists now.
    conn = sqlite3.connect(path_existing)
    idx_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    checks["existing_db_migration_2_index_created"] = "idx_records_updated_at" in idx_names
finally:
    cleanup(path_existing)

# --- 3. Future version rejection: a DB claiming a version newer than
# this code supports must be refused outright, not silently accepted
# or worked around. ---
path_future = fresh_path()
try:
    raw = sqlite3.connect(path_future)
    raw.execute("CREATE TABLE schema_meta (id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)")
    raw.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    raw.execute("INSERT INTO schema_meta (id, version) VALUES (1, 999)")
    raw.commit()
    raw.close()

    rejected = False
    error_mentions_versions = False
    try:
        SqliteStore(path_future)
    except SchemaVersionError as exc:
        rejected = True
        error_mentions_versions = exc.found_version == 999 and exc.max_supported_version == RECORDS_SCHEMA_VERSION
    checks["future_version_refused_to_open"] = rejected
    checks["future_version_error_has_correct_context"] = error_mentions_versions
finally:
    cleanup(path_future)

# --- 4. Migration history: every applied migration is recorded, in
# order, with a description and a timestamp -- for both files. ---
path_history = fresh_path()
try:
    store = SqliteStore(path_history)
    records_history = store.get_migration_history()
    audit_history = store.get_migration_history(audit=True)
    checks["records_history_has_both_migrations"] = [h["version"] for h in records_history] == [1, 2]
    checks["records_history_has_descriptions"] = all(h["description"] for h in records_history)
    checks["records_history_has_timestamps"] = all(h["applied_at"] for h in records_history)
    checks["audit_history_has_both_migrations"] = [h["version"] for h in audit_history] == [1, 2]
    checks["audit_history_has_descriptions"] = all(h["description"] for h in audit_history)
finally:
    cleanup(path_history)

# --- 5. Restart survival: schema version and migration history (not
# just business data) must themselves survive a real restart. ---
path_restart = fresh_path()
try:
    store_a = SqliteStore(path_restart)
    store_a.save_record("test_table", "id-1", {"restart": "proof"})
    version_before = store_a.get_schema_version()
    history_before = store_a.get_migration_history()
    del store_a  # simulate process exit

    store_b = SqliteStore(path_restart)
    checks["restart_schema_version_survived"] = store_b.get_schema_version() == version_before
    checks["restart_migration_history_survived"] = store_b.get_migration_history() == history_before
    checks["restart_business_data_survived"] = (
        store_b.load_record("test_table", "id-1") == {"restart": "proof"}
    )
    # And reopening again must NOT re-apply migrations or duplicate history.
    checks["restart_did_not_reapply_migrations"] = len(store_b.get_migration_history()) == len(history_before)
finally:
    cleanup(path_restart)

# --- 6. No business logic touched: engines that use SqliteStore under
# the hood still behave exactly as before -- spot check via SRR. ---
path_srr = fresh_path()
try:
    from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
    from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
    from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
    from era.acquisition import connector_errors as srr_errors

    store = SqliteStore(path_srr)
    srr = SourceReliabilityRegistry(store=store)
    connector = ConnectorRecord(
        connector_id="COUNTY_TEST", provider_name="Test County", version="1.0",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS, legal_classification=LegalClassification.PUBLIC_RECORD,
        status=ConnectorStatus.ACTIVE, capabilities=["OWNERSHIP"],
        resource_policy=ResourcePolicy(refresh_schedule_hours=24, rate_limit_per_day=500,
                                        cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=500),
        retry_policy=RetryPolicy(max_retries=2, retry_delay_seconds=10),
    )
    status, registered = srr.register_connector(connector)
    checks["srr_business_logic_unaffected_by_schema_versioning"] = (
        status == srr_errors.PASS and registered is not None
    )
finally:
    cleanup(path_srr)

# --- 7. Full pipeline still runs under a schema-versioned store. -----
path_pipeline = fresh_path()
try:
    from era.app import build_app, bootstrap_demo
    from era.property_record.property_models import PropertyIdentity
    from era.property_record.property_enums import PropertyType, StrategyType

    app = build_app(persistence_path=path_pipeline)
    bootstrap_demo(app)
    identity = PropertyIdentity(
        property_id="ERA-PR-SCHEMA-001", address="5926 Sandhurst Ln Unit 224", city="Dallas",
        state="TX", zip_code="75252", county="Dallas", parcel_apn="00000000000",
        latitude=None, longitude=None,
        property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
    )
    result = app.run_property(
        property_id=identity.property_id, identity=identity,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    checks["full_pipeline_runs_under_schema_versioned_store"] = result.ok
finally:
    cleanup(path_pipeline)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"SCHEMA-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
