import sys
import os
import tempfile
from era.shared.persistence import SqliteStore
from era.decision.decision_engine import DecisionEngine
from era.decision.decision_models import DecisionInput
from era.decision.decision_enums import DecisionState, DecisionReason
from era.decision import decision_errors as errors

print("DEC PERSISTENCE VERIFICATION (C4 rollout, step 5)")
print("=" * 70)

decision_input = DecisionInput(
    property_id="ERA-PR-2026-000001", evidence_count=2,
    required_fields_present=True, has_conflicts=False, has_policy_violation=False,
    manual_review_flag=False, single_source_only=False, export_ready=True,
    supporting_evidence_ids=["EV-001", "EV-002"],
)

checks = {}
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    store_a = SqliteStore(db_path)
    engine_a = DecisionEngine(store=store_a)
    status, record = engine_a.decide(decision_input)
    checks["decide_ok"] = status == errors.PASS and record is not None
    checks["expected_decision_state"] = (
        record.decision == DecisionState.READY_FOR_EXPORT if record else False
    )
    del engine_a  # simulate process exit

    store_b = SqliteStore(db_path)
    engine_b = DecisionEngine(store=store_b)
    reloaded = engine_b.get_decision("ERA-PR-2026-000001")
    checks["record_survived_restart"] = reloaded is not None
    checks["decision_enum_survived_restart"] = (
        reloaded.decision == DecisionState.READY_FOR_EXPORT if reloaded else False
    )
    checks["reason_enum_survived_restart"] = (
        reloaded.reason == DecisionReason.EXPORT_REQUIREMENTS_MET if reloaded else False
    )
    checks["supporting_evidence_survived_restart"] = (
        reloaded.supporting_evidence_ids == ["EV-001", "EV-002"] if reloaded else False
    )

    # Business logic unchanged: a conflicting item still routes to
    # CONFLICT_RESOLUTION_REQUIRED, not silently altered by persistence.
    conflicting_input = DecisionInput(
        property_id="ERA-PR-2026-000002", evidence_count=2,
        required_fields_present=True, has_conflicts=True, has_policy_violation=False,
        manual_review_flag=False, single_source_only=False, export_ready=False,
        supporting_evidence_ids=["EV-003"],
    )
    _, conflict_record = engine_b.decide(conflicting_input)
    checks["decision_rule_logic_unchanged"] = (
        conflict_record.decision == DecisionState.CONFLICT_RESOLUTION_REQUIRED
        and conflict_record.requires_manual_review is True
    )

    plain_engine = DecisionEngine()
    plain_status, _ = plain_engine.decide(decision_input)
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
print("DEC PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
