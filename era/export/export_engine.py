from dataclasses import asdict
from era.export.export_audit import ExportAudit
from era.export.export_models import ExportPackage
from era.export.export_enums import ExportStatus, ExportFormat
from era.export import export_errors as errors
from era.shared.persistence import PersistenceError
class ExportEngine:
    """
    C4 rollout, step 7 (final): pass `store=`
    (era.shared.persistence.SqliteStore) to make export packages survive
    process exit. Pass nothing and behavior is unchanged.

    Note: export() was previously stateless -- it computed and returned
    an ExportPackage but never retained it. Retention (self.records,
    get_export()) is new capability; the authorization/blocking logic in
    export() itself is untouched.

    Persisted fields: export_id, property_id, decision, policy_verdict,
    export_format, status, payload, created_at. ExportPackage has no
    audit_reference field in this codebase, so none is persisted --
    not inventing one.
    """
    AUTHORIZED_VERDICTS = {"AUTHORIZED", "EXPORT_APPROVED"}
    TABLE = "export_packages"
    def __init__(self, audit=None, store=None):
        self.audit = audit or ExportAudit()
        self.store = store
        self.records = {}
        if self.store:
            self._load_from_store()
    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            record = self._from_dict(data)
            self.records[record.property_id] = record
    def _persist(self, record: ExportPackage, conn=None) -> bool:
        if not self.store:
            return True
        try:
            self.store.save_record(self.TABLE, record.property_id, self._to_dict(record), conn=conn)
            return True
        except PersistenceError:
            return False
    @staticmethod
    def _to_dict(record: ExportPackage) -> dict:
        data = asdict(record)
        data["export_format"] = record.export_format.value
        data["status"] = record.status.value
        return data
    @staticmethod
    def _from_dict(data: dict) -> ExportPackage:
        data = dict(data)
        data["export_format"] = ExportFormat(data["export_format"])
        data["status"] = ExportStatus(data["status"])
        return ExportPackage(**data)
    def export(self, request, conn=None):
        if request is None or not request.property_id:
            self.audit.publish("EXPORT_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return errors.PROPERTY_REQUIRED, None
        if not request.decision:
            self.audit.publish("EXPORT_BLOCKED", {"reason": errors.DECISION_REQUIRED})
            return errors.DECISION_REQUIRED, None
        if not request.policy_verdict:
            self.audit.publish("EXPORT_BLOCKED", {"reason": errors.POLICY_REQUIRED})
            return errors.POLICY_REQUIRED, None
        if not request.provenance_complete:
            self.audit.publish("EXPORT_BLOCKED", {"reason": errors.PROVENANCE_REQUIRED})
            return errors.PROVENANCE_REQUIRED, None
        if request.policy_verdict not in self.AUTHORIZED_VERDICTS:
            self.audit.publish("EXPORT_BLOCKED", {
                "reason": errors.EXPORT_BLOCKED,
                "policy_verdict": request.policy_verdict,
            })
            return errors.EXPORT_BLOCKED, None
        if not isinstance(request.export_format, ExportFormat):
            self.audit.publish("EXPORT_BLOCKED", {"reason": errors.UNSUPPORTED_FORMAT})
            return errors.UNSUPPORTED_FORMAT, None
        package = ExportPackage(
            export_id=f"EXP-{request.property_id}-{request.export_format.value}",
            property_id=request.property_id,
            decision=request.decision,
            policy_verdict=request.policy_verdict,
            export_format=request.export_format,
            status=ExportStatus.EXPORTED,
            payload=dict(request.payload),
        )
        previous = self.records.get(package.property_id)
        self.records[package.property_id] = package
        if not self._persist(package, conn=conn):
            if previous is not None:
                self.records[package.property_id] = previous
            else:
                del self.records[package.property_id]
            self.audit.publish("EXPORT_BLOCKED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "property_id": package.property_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED, None
        self.audit.publish("EXPORT_PACKAGE_CREATED", {
            "export_id": package.export_id,
            "property_id": package.property_id,
            "format": package.export_format.value,
        })
        self.audit.publish("EXPORT_COMPLETED", {
            "export_id": package.export_id,
            "status": package.status.value,
        })
        return errors.PASS, package
    def get_export(self, property_id):
        return self.records.get(property_id)
    def attempt_write(self):
        self.audit.publish("EXPORT_BLOCKED", {"reason": errors.READ_ONLY_EXPORT})
        return False, errors.READ_ONLY_EXPORT
    def assign_confidence(self):
        self.audit.publish("EXPORT_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
