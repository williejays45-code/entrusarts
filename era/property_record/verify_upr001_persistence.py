import sys
import os
import tempfile
from era.shared.persistence import SqliteStore
from era.property_record.unified_property_record import UnifiedPropertyRecordEngine
from era.property_record.property_models import PropertyIdentity, EvidenceEntry
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record import property_errors as errors

print("UPR PERSISTENCE VERIFICATION (C4 rollout, step 2)")
print("=" * 70)

identity = PropertyIdentity(
    property_id="ERA-PR-2026-000001",
    address="5926 Sandhurst Ln Unit 224", city="Dallas", state="TX",
    zip_code="75252", county="Dallas", parcel_apn="00000000000",
    latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)
evidence = EvidenceEntry(
    evidence_id="EV-001", property_id=identity.property_id, category="IDENTITY",
    value="5926 Sandhurst Ln Unit 224", connector="COUNTY_DALLAS_CAD",
    original_source="DCAD-PUBLIC-SEARCH", retrieved_at="2026-07-09T00:00:00+00:00",
    normalization_version="ECM-001.0", audit_reference="sha256:deadbeef",
)

checks = {}
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    store_a = SqliteStore(db_path)
    engine_a = UnifiedPropertyRecordEngine(store=store_a)
    status, record = engine_a.create_property(identity)
    checks["create_ok"] = status == errors.PASS and record is not None
    ev_status, _ = engine_a.add_evidence(identity.property_id, evidence)
    checks["add_evidence_ok"] = ev_status == errors.PASS
    del engine_a  # simulate process exit

    store_b = SqliteStore(db_path)
    engine_b = UnifiedPropertyRecordEngine(store=store_b)
    reloaded = engine_b.records.get(identity.property_id)
    checks["record_survived_restart"] = reloaded is not None
    checks["identity_survived_restart"] = (
        reloaded.identity.address == identity.address
        and reloaded.identity.property_type == PropertyType.CONDO
        if reloaded else False
    )
    checks["evidence_survived_restart"] = (
        len(reloaded.evidence) == 1 and reloaded.evidence[0].evidence_id == "EV-001"
        if reloaded else False
    )
    # Prove it's a real reload, not a shared object: adding evidence
    # through engine_b must not retroactively appear anywhere else.
    dup_status, _ = engine_b.add_evidence(identity.property_id, evidence)
    checks["duplicate_evidence_still_blocked_after_reload"] = dup_status == errors.DUPLICATE_EVIDENCE

    # Default (no store) behavior unchanged.
    plain_engine = UnifiedPropertyRecordEngine()
    plain_status, _ = plain_engine.create_property(identity)
    checks["no_store_default_still_works"] = plain_status == errors.PASS
    checks["no_store_default_has_no_store_attr_set"] = plain_engine.store is None

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
print("UPR PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
