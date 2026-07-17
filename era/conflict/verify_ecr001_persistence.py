import sys
import os
import tempfile
from era.shared.persistence import SqliteStore
from era.conflict.conflict_resolver import EvidenceConflictResolver
from era.conflict.conflict_models import ConflictEvidence
from era.conflict.conflict_enums import ConflictStatus, ConflictType
from era.conflict import conflict_errors as errors

print("ECR PERSISTENCE VERIFICATION (C4 rollout, step 4)")
print("=" * 70)

evidence_items = [
    ConflictEvidence(
        evidence_id="EV-001", property_id="ERA-PR-2026-000001", field_name="year_built",
        normalized_value="1998", provider_id="COUNTY_DALLAS_CAD", source_reference="DCAD",
    ),
    ConflictEvidence(
        evidence_id="EV-002", property_id="ERA-PR-2026-000001", field_name="year_built",
        normalized_value="2001", provider_id="COUNTY_TARRANT_ASSESSOR", source_reference="TARRANT",
    ),
]

checks = {}
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    store_a = SqliteStore(db_path)
    resolver_a = EvidenceConflictResolver(store=store_a)
    status, reports = resolver_a.resolve(evidence_items)
    checks["conflict_detected"] = status == errors.PASS and len(reports) == 1
    conflict_id = reports[0].conflict_id if reports else None
    checks["report_retained_in_memory"] = resolver_a.get_report(conflict_id) is not None
    del resolver_a  # simulate process exit

    store_b = SqliteStore(db_path)
    resolver_b = EvidenceConflictResolver(store=store_b)
    reloaded = resolver_b.get_report(conflict_id)
    checks["report_survived_restart"] = reloaded is not None
    checks["conflict_type_survived_restart"] = (
        reloaded.conflict_type == ConflictType.YEAR_BUILT_CONFLICT if reloaded else False
    )
    checks["status_survived_restart"] = reloaded.status == ConflictStatus.OPEN if reloaded else False
    checks["observed_values_survived_restart"] = (
        reloaded.observed_values == ["1998", "2001"] if reloaded else False
    )
    checks["providers_survived_restart"] = (
        set(reloaded.providers) == {"COUNTY_DALLAS_CAD", "COUNTY_TARRANT_ASSESSOR"} if reloaded else False
    )

    # Business logic unchanged: no-conflict input still returns NO_CONFLICT.
    single_source = [evidence_items[0]]
    no_conflict_status, no_conflict_reports = resolver_b.resolve(single_source)
    checks["no_conflict_logic_unchanged"] = (
        no_conflict_status == errors.NO_CONFLICT and no_conflict_reports == []
    )

    plain_resolver = EvidenceConflictResolver()
    plain_status, plain_reports = plain_resolver.resolve(evidence_items)
    checks["no_store_default_still_works"] = plain_status == errors.PASS and len(plain_reports) == 1
    checks["no_store_default_has_no_store_attr_set"] = plain_resolver.store is None

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
print("ECR PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
