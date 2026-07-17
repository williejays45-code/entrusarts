from dataclasses import asdict
from era.policy.policy_audit import PolicyAudit
from era.policy.policy_models import PolicyResult
from era.policy.policy_enums import PolicyVerdict, PolicyReason
from era.policy import policy_errors as errors
from era.shared.persistence import PersistenceError
class PolicyEngine:
    """
    C4 rollout, step 6: pass `store=` (era.shared.persistence.SqliteStore)
    to make policy results survive process exit. Pass nothing and
    behavior is unchanged.

    Note: evaluate() was previously stateless -- it computed and returned
    a PolicyResult but never retained it. Retention (self.results,
    get_result()) is new capability; _apply_policy(), the actual policy
    logic, is untouched.
    """
    TABLE = "policy_results"
    def __init__(self, audit=None, store=None):
        self.audit = audit or PolicyAudit()
        self.store = store
        self.results = {}
        if self.store:
            self._load_from_store()
    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            result = self._from_dict(data)
            self.results[result.property_id] = result
    def _persist(self, result: PolicyResult, conn=None) -> bool:
        if not self.store:
            return True
        try:
            self.store.save_record(self.TABLE, result.property_id, self._to_dict(result), conn=conn)
            return True
        except PersistenceError:
            return False
    @staticmethod
    def _to_dict(result: PolicyResult) -> dict:
        data = asdict(result)
        data["verdict"] = result.verdict.value
        data["reason"] = result.reason.value
        return data
    @staticmethod
    def _from_dict(data: dict) -> PolicyResult:
        data = dict(data)
        data["verdict"] = PolicyVerdict(data["verdict"])
        data["reason"] = PolicyReason(data["reason"])
        return PolicyResult(**data)
    def evaluate(self, policy, decision, conn=None):
        if policy is None or not policy.policy_id:
            self.audit.publish("POLICY_BLOCKED", {"reason": errors.POLICY_REQUIRED})
            return errors.POLICY_REQUIRED, None
        if not policy.policy_version:
            self.audit.publish("POLICY_BLOCKED", {"reason": errors.POLICY_VERSION_REQUIRED})
            return errors.POLICY_VERSION_REQUIRED, None
        if decision is None or not decision.property_id or not decision.decision:
            self.audit.publish("POLICY_BLOCKED", {"reason": errors.DECISION_REQUIRED})
            return errors.DECISION_REQUIRED, None
        verdict, reason = self._apply_policy(policy, decision)
        result = PolicyResult(
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            property_id=decision.property_id,
            decision=decision.decision,
            verdict=verdict,
            reason=reason,
            supporting_evidence_ids=list(decision.supporting_evidence_ids),
        )
        previous = self.results.get(result.property_id)
        self.results[result.property_id] = result
        if not self._persist(result, conn=conn):
            if previous is not None:
                self.results[result.property_id] = previous
            else:
                del self.results[result.property_id]
            self.audit.publish("POLICY_BLOCKED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "property_id": result.property_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED, None
        self.audit.publish("POLICY_RULE_EVALUATED", {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "property_id": decision.property_id,
            "decision": decision.decision,
            "verdict": verdict.value,
            "reason": reason.value,
        })
        self.audit.publish("POLICY_RESULT_RECORDED", {
            "policy_id": policy.policy_id,
            "property_id": decision.property_id,
            "supporting_evidence_count": len(decision.supporting_evidence_ids),
        })
        return errors.PASS, result
    def get_result(self, property_id):
        return self.results.get(property_id)
    def _apply_policy(self, policy, decision):
        if decision.policy_violation:
            return PolicyVerdict.POLICY_VIOLATION, PolicyReason.POLICY_RULE_VIOLATED
        if decision.has_conflicts and policy.require_manual_review_on_conflict:
            return PolicyVerdict.REQUIRES_REVIEW, PolicyReason.MANUAL_REVIEW_NEEDED
        if decision.decision not in policy.allowed_decisions:
            return PolicyVerdict.DENIED, PolicyReason.DECISION_NOT_ALLOWED
        if decision.export_requested:
            if policy.export_allowed:
                return PolicyVerdict.EXPORT_APPROVED, PolicyReason.EXPORT_REQUIREMENTS_MET
            return PolicyVerdict.EXPORT_DENIED, PolicyReason.EXPORT_REQUIREMENTS_NOT_MET
        return PolicyVerdict.AUTHORIZED, PolicyReason.DECISION_ALLOWED
    def attempt_write(self):
        self.audit.publish("POLICY_BLOCKED", {"reason": errors.READ_ONLY_POLICY})
        return False, errors.READ_ONLY_POLICY
    def assign_confidence(self):
        self.audit.publish("POLICY_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
