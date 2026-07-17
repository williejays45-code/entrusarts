import sys
import os
import tempfile
from era.shared.persistence import SqliteStore
from era.policy.policy_engine import PolicyEngine
from era.policy.policy_models import PolicyRuleSet, PolicyDecisionInput
from era.policy.policy_enums import PolicyVerdict, PolicyReason
from era.policy import policy_errors as errors

print("POL PERSISTENCE VERIFICATION (C4 rollout, step 6)")
print("=" * 70)

policy = PolicyRuleSet(
    policy_id="POL-ERA-001", policy_version="1.0",
    allowed_decisions=["ACCEPT", "READY_FOR_EXPORT"],
    export_allowed=True, require_manual_review_on_conflict=True,
)
decision_input = PolicyDecisionInput(
    property_id="ERA-PR-2026-000001", decision="ACCEPT",
    has_conflicts=False, export_requested=True, policy_violation=False,
    supporting_evidence_ids=["EV-001", "EV-002"],
)

checks = {}
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    store_a = SqliteStore(db_path)
    engine_a = PolicyEngine(store=store_a)
    status, result = engine_a.evaluate(policy, decision_input)
    checks["evaluate_ok"] = status == errors.PASS and result is not None
    checks["expected_verdict"] = result.verdict == PolicyVerdict.EXPORT_APPROVED if result else False
    del engine_a  # simulate process exit

    store_b = SqliteStore(db_path)
    engine_b = PolicyEngine(store=store_b)
    reloaded = engine_b.get_result("ERA-PR-2026-000001")
    checks["result_survived_restart"] = reloaded is not None
    checks["verdict_enum_survived_restart"] = (
        reloaded.verdict == PolicyVerdict.EXPORT_APPROVED if reloaded else False
    )
    checks["reason_enum_survived_restart"] = (
        reloaded.reason == PolicyReason.EXPORT_REQUIREMENTS_MET if reloaded else False
    )
    checks["policy_id_survived_restart"] = reloaded.policy_id == "POL-ERA-001" if reloaded else False

    # Business logic unchanged: a policy-violating decision still denies.
    violating_input = PolicyDecisionInput(
        property_id="ERA-PR-2026-000002", decision="ACCEPT",
        has_conflicts=False, export_requested=True, policy_violation=True,
        supporting_evidence_ids=["EV-003"],
    )
    _, violation_result = engine_b.evaluate(policy, violating_input)
    checks["policy_rule_logic_unchanged"] = (
        violation_result.verdict == PolicyVerdict.POLICY_VIOLATION
        and violation_result.reason == PolicyReason.POLICY_RULE_VIOLATED
    )

    plain_engine = PolicyEngine()
    plain_status, _ = plain_engine.evaluate(policy, decision_input)
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
print("POL PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
