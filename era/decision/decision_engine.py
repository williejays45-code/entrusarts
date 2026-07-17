from dataclasses import asdict
from era.decision.decision_audit import DecisionAudit
from era.decision.decision_models import DecisionRecord
from era.decision.decision_enums import DecisionState, DecisionReason
from era.decision import decision_errors as errors
from era.shared.persistence import PersistenceError
class DecisionEngine:
    """
    C4 rollout, step 5: pass `store=` (era.shared.persistence.SqliteStore)
    to make decision records survive process exit. Pass nothing and
    behavior is unchanged.

    Note: decide() was previously stateless -- it computed and returned a
    DecisionRecord but never retained it. Retention (self.records,
    get_decision()) is new capability; _apply_rules(), the actual
    decision logic, is untouched.
    """
    TABLE = "decision_records"
    def __init__(self, audit=None, store=None):
        self.audit = audit or DecisionAudit()
        self.store = store
        self.records = {}
        if self.store:
            self._load_from_store()
    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            record = self._from_dict(data)
            self.records[record.property_id] = record
    def _persist(self, record: DecisionRecord, conn=None) -> bool:
        if not self.store:
            return True
        try:
            self.store.save_record(self.TABLE, record.property_id, self._to_dict(record), conn=conn)
            return True
        except PersistenceError:
            return False
    @staticmethod
    def _to_dict(record: DecisionRecord) -> dict:
        data = asdict(record)
        data["decision"] = record.decision.value
        data["reason"] = record.reason.value
        return data
    @staticmethod
    def _from_dict(data: dict) -> DecisionRecord:
        data = dict(data)
        data["decision"] = DecisionState(data["decision"])
        data["reason"] = DecisionReason(data["reason"])
        return DecisionRecord(**data)
    def decide(self, item, conn=None):
        if item is None or not item.property_id:
            self.audit.publish("DECISION_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return errors.PROPERTY_REQUIRED, None
        if item.evidence_count <= 0 or not item.supporting_evidence_ids:
            self.audit.publish("DECISION_BLOCKED", {"reason": errors.EVIDENCE_REQUIRED})
            return errors.EVIDENCE_REQUIRED, None
        decision, reason, review = self._apply_rules(item)
        record = DecisionRecord(
            decision_id=f"DEC-{item.property_id}",
            property_id=item.property_id,
            decision=decision,
            reason=reason,
            requires_manual_review=review,
            supporting_evidence_ids=list(item.supporting_evidence_ids),
        )
        previous = self.records.get(record.property_id)
        self.records[record.property_id] = record
        if not self._persist(record, conn=conn):
            if previous is not None:
                self.records[record.property_id] = previous
            else:
                del self.records[record.property_id]
            self.audit.publish("DECISION_BLOCKED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "property_id": record.property_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED, None
        self.audit.publish("DECISION_RULE_EVALUATED", {
            "property_id": item.property_id,
            "decision": decision.value,
            "reason": reason.value,
        })
        self.audit.publish("DECISION_RECORDED", {
            "decision_id": record.decision_id,
            "property_id": record.property_id,
            "supporting_evidence_count": len(record.supporting_evidence_ids),
        })
        return errors.PASS, record
    def get_decision(self, property_id):
        return self.records.get(property_id)
    def _apply_rules(self, item):
        if item.has_policy_violation:
            return DecisionState.REJECT, DecisionReason.POLICY_VIOLATION, False
        if item.has_conflicts:
            return DecisionState.CONFLICT_RESOLUTION_REQUIRED, DecisionReason.ACTIVE_CONFLICTS_PRESENT, True
        if item.manual_review_flag:
            return DecisionState.MANUAL_REVIEW, DecisionReason.MANUAL_REVIEW_REQUIRED, True
        if not item.required_fields_present:
            return DecisionState.INSUFFICIENT_EVIDENCE, DecisionReason.MISSING_REQUIRED_EVIDENCE, False
        if item.single_source_only:
            return DecisionState.PENDING_MORE_EVIDENCE, DecisionReason.SINGLE_SOURCE_ONLY, False
        if item.export_ready:
            return DecisionState.READY_FOR_EXPORT, DecisionReason.EXPORT_REQUIREMENTS_MET, False
        return DecisionState.ACCEPT, DecisionReason.NO_CONFLICTS_SUFFICIENT_EVIDENCE, False
    def attempt_write(self):
        self.audit.publish("DECISION_BLOCKED", {"reason": errors.READ_ONLY_DECISION})
        return False, errors.READ_ONLY_DECISION
    def assign_confidence(self):
        self.audit.publish("DECISION_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
