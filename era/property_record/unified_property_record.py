from dataclasses import asdict
from era.property_record.property_models import UnifiedPropertyRecord, PropertyIdentity, EvidenceEntry
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record.property_audit import PropertyAuditPublisher
from era.property_record import property_errors as errors
from era.shared.persistence import PersistenceError
class UnifiedPropertyRecordEngine:
    """
    C4 rollout, step 2: pass `store=` (era.shared.persistence.SqliteStore)
    to make property records and their evidence survive process exit.
    Pass nothing and behavior is unchanged from before -- in-memory only,
    same as every other engine that hasn't had persistence wired in yet.

    Persistence error handling: create_property() and add_evidence()
    roll their in-memory mutation back and return
    errors.PERSISTENCE_WRITE_FAILED if the durable write fails, so
    self.records never disagrees with disk.
    """
    TABLE = "property_records"
    def __init__(self, audit=None, store=None):
        self.records = {}
        self.audit = audit or PropertyAuditPublisher()
        self.store = store
        if self.store:
            self._load_from_store()
    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            record = self._from_dict(data)
            self.records[record.identity.property_id] = record
    def _persist(self, record: UnifiedPropertyRecord, conn=None) -> bool:
        if not self.store:
            return True
        try:
            self.store.save_record(self.TABLE, record.identity.property_id, self._to_dict(record), conn=conn)
            return True
        except PersistenceError:
            return False
    @staticmethod
    def _to_dict(record: UnifiedPropertyRecord) -> dict:
        identity = asdict(record.identity)
        identity["property_type"] = record.identity.property_type.value
        identity["strategy_type"] = record.identity.strategy_type.value
        return {
            "identity": identity,
            "evidence": [asdict(e) for e in record.evidence],
            "evaluations": list(record.evaluations),
            "audit_events": list(record.audit_events),
            "created_at": record.created_at,
        }
    @staticmethod
    def _from_dict(data: dict) -> UnifiedPropertyRecord:
        identity_data = dict(data["identity"])
        identity_data["property_type"] = PropertyType(identity_data["property_type"])
        identity_data["strategy_type"] = StrategyType(identity_data["strategy_type"])
        identity = PropertyIdentity(**identity_data)
        record = UnifiedPropertyRecord(
            identity=identity,
            evidence=[EvidenceEntry(**e) for e in data["evidence"]],
            evaluations=list(data["evaluations"]),
            audit_events=list(data["audit_events"]),
            created_at=data["created_at"],
        )
        return record
    def create_property(self, identity, conn=None):
        if not identity.property_id:
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return errors.PROPERTY_REQUIRED, None
        if identity.property_id in self.records:
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.DUPLICATE_PROPERTY})
            return errors.DUPLICATE_PROPERTY, None
        if not isinstance(identity.property_type, PropertyType):
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.INVALID_PROPERTY_TYPE})
            return errors.INVALID_PROPERTY_TYPE, None
        if not isinstance(identity.strategy_type, StrategyType):
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.INVALID_STRATEGY_TYPE})
            return errors.INVALID_STRATEGY_TYPE, None
        record = UnifiedPropertyRecord(identity=identity)
        self.records[identity.property_id] = record
        if not self._persist(record, conn=conn):
            del self.records[identity.property_id]
            self.audit.publish("PROPERTY_BLOCKED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "property_id": identity.property_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED, None
        self.audit.publish("PROPERTY_CREATED", {
            "property_id": identity.property_id,
            "parcel_apn": identity.parcel_apn,
            "county": identity.county,
        })
        return errors.PASS, record
    def add_evidence(self, property_id: str, evidence, conn=None):
        if property_id not in self.records:
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return errors.PROPERTY_REQUIRED, None
        if not evidence.evidence_id:
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.EVIDENCE_REQUIRED})
            return errors.EVIDENCE_REQUIRED, None
        record = self.records[property_id]
        if any(item.evidence_id == evidence.evidence_id for item in record.evidence):
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.DUPLICATE_EVIDENCE})
            return errors.DUPLICATE_EVIDENCE, None
        if evidence.supersedes_evidence_id and not evidence.correction_reason:
            self.audit.publish("PROPERTY_BLOCKED", {"reason": errors.SUPERSEDES_REQUIRED})
            return errors.SUPERSEDES_REQUIRED, None
        record.evidence.append(evidence)
        if not self._persist(record, conn=conn):
            record.evidence.pop()
            self.audit.publish("PROPERTY_BLOCKED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "property_id": property_id,
                "evidence_id": evidence.evidence_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED, None
        event = "EVIDENCE_SUPERSEDED" if evidence.supersedes_evidence_id else "EVIDENCE_ADDED"
        self.audit.publish(event, {
            "property_id": property_id,
            "evidence_id": evidence.evidence_id,
            "supersedes": evidence.supersedes_evidence_id,
        })
        return errors.PASS, evidence
    def attempt_reasoning_write(self, target: str):
        if target in {"evidence", "documents", "photos", "ownership", "taxes", "permits"}:
            self.audit.publish("PROPERTY_BLOCKED", {
                "reason": errors.READ_ONLY_PROPERTY,
                "target": target,
            })
            return False, errors.READ_ONLY_PROPERTY
        return True, errors.PASS
    def find_existing_property(self, parcel_apn: str, county: str, address: str):
        for record in self.records.values():
            identity = record.identity
            if parcel_apn and county and identity.parcel_apn == parcel_apn and identity.county == county:
                return record
            if address and county and identity.address.lower() == address.lower() and identity.county == county:
                return record
        return None
