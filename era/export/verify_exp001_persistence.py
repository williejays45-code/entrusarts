import sys
import os
import tempfile
from era.shared.persistence import SqliteStore
from era.export.export_engine import ExportEngine
from era.export.export_models import ExportRequest
from era.export.export_enums import ExportFormat, ExportStatus
from era.export import export_errors as errors

print("EXP PERSISTENCE VERIFICATION (C4 rollout, step 7 -- final)")
print("=" * 70)

request = ExportRequest(
    property_id="ERA-PR-2026-000001", decision="ACCEPT", policy_verdict="AUTHORIZED",
    provenance_complete=True, export_format=ExportFormat.JSON,
    payload={"decision_id": "DEC-ERA-PR-2026-000001", "policy_id": "POL-ERA-001", "evidence_count": 2},
)

checks = {}
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    # 1. Create export.
    store_a = SqliteStore(db_path)
    engine_a = ExportEngine(store=store_a)
    status, package = engine_a.export(request)
    checks["export_created"] = status == errors.PASS and package is not None
    checks["export_id_correct"] = package.export_id == "EXP-ERA-PR-2026-000001-JSON" if package else False

    # 2. Close engine/container -- simulate process exit, nothing in
    # memory survives past this point.
    del engine_a

    # 3. Reopen from same SQLite store.
    store_b = SqliteStore(db_path)
    engine_b = ExportEngine(store=store_b)

    # 4. Confirm export record still exists and matches.
    reloaded = engine_b.get_export("ERA-PR-2026-000001")
    checks["export_survived_restart"] = reloaded is not None
    checks["export_id_matches"] = reloaded.export_id == "EXP-ERA-PR-2026-000001-JSON" if reloaded else False
    checks["property_id_matches"] = reloaded.property_id == "ERA-PR-2026-000001" if reloaded else False
    checks["decision_matches"] = reloaded.decision == "ACCEPT" if reloaded else False
    checks["policy_verdict_matches"] = reloaded.policy_verdict == "AUTHORIZED" if reloaded else False
    checks["export_format_enum_matches"] = (
        reloaded.export_format == ExportFormat.JSON if reloaded else False
    )
    checks["status_enum_matches"] = reloaded.status == ExportStatus.EXPORTED if reloaded else False
    checks["payload_matches"] = (
        reloaded.payload == {
            "decision_id": "DEC-ERA-PR-2026-000001", "policy_id": "POL-ERA-001", "evidence_count": 2,
        } if reloaded else False
    )
    checks["created_at_present"] = bool(reloaded.created_at) if reloaded else False

    # Business logic unchanged: a denied verdict still blocks export
    # after reload, not silently allowed by persistence wiring.
    denied_request = ExportRequest(
        property_id="ERA-PR-2026-000002", decision="ACCEPT", policy_verdict="DENIED",
        provenance_complete=True, export_format=ExportFormat.JSON, payload={},
    )
    denied_status, denied_package = engine_b.export(denied_request)
    checks["export_blocking_logic_unchanged"] = (
        denied_status == errors.EXPORT_BLOCKED and denied_package is None
    )

    plain_engine = ExportEngine()
    plain_status, _ = plain_engine.export(request)
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
print("EXP PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
