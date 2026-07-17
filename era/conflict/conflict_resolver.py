from dataclasses import asdict
from era.conflict.conflict_audit import ConflictAudit
from era.conflict.conflict_models import ConflictReport
from era.conflict.conflict_enums import ConflictType, ConflictStatus
from era.conflict import conflict_errors as errors
from era.shared.persistence import PersistenceError
class EvidenceConflictResolver:
    """
    C4 rollout, step 4: pass `store=` (era.shared.persistence.SqliteStore)
    to make detected conflict reports survive process exit. Pass nothing
    and behavior is unchanged -- reports are still returned from
    resolve() exactly as before; only their retention in self.reports
    (new) is affected by whether a store is present.

    Note: resolve() itself was previously stateless -- it computed and
    returned ConflictReport objects but never retained them. Retention
    (self.reports, get_report()) is new capability, not a change to how
    conflicts are detected or classified; that algorithm is untouched.
    """
    TABLE = "conflict_reports"
    FIELD_TYPES = {
        "owner": ConflictType.OWNER_CONFLICT,
        "owner_name": ConflictType.OWNER_CONFLICT,
        "address": ConflictType.ADDRESS_CONFLICT,
        "property_address": ConflictType.ADDRESS_CONFLICT,
        "parcel": ConflictType.PARCEL_CONFLICT,
        "parcel_apn": ConflictType.PARCEL_CONFLICT,
        "legal_description": ConflictType.LEGAL_DESCRIPTION_CONFLICT,
        "appraised_value": ConflictType.APPRAISAL_CONFLICT,
        "land_value": ConflictType.LAND_VALUE_CONFLICT,
        "improvement_value": ConflictType.IMPROVEMENT_VALUE_CONFLICT,
        "exemptions": ConflictType.EXEMPTION_CONFLICT,
        "year_built": ConflictType.YEAR_BUILT_CONFLICT,
        "living_area": ConflictType.BUILDING_SIZE_CONFLICT,
        "building_size": ConflictType.BUILDING_SIZE_CONFLICT,
    }
    def __init__(self, audit=None, store=None):
        self.audit = audit or ConflictAudit()
        self.store = store
        self.reports = {}
        if self.store:
            self._load_from_store()
    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            report = self._from_dict(data)
            self.reports[report.conflict_id] = report
    def _persist(self, report: ConflictReport, conn=None) -> bool:
        if not self.store:
            return True
        try:
            self.store.save_record(self.TABLE, report.conflict_id, self._to_dict(report), conn=conn)
            return True
        except PersistenceError:
            return False
    @staticmethod
    def _to_dict(report: ConflictReport) -> dict:
        data = asdict(report)
        data["conflict_type"] = report.conflict_type.value
        data["status"] = report.status.value
        return data
    @staticmethod
    def _from_dict(data: dict) -> ConflictReport:
        data = dict(data)
        data["conflict_type"] = ConflictType(data["conflict_type"])
        data["status"] = ConflictStatus(data["status"])
        return ConflictReport(**data)
    def classify(self, field_name):
        return self.FIELD_TYPES.get(str(field_name).lower(), ConflictType.UNKNOWN_CONFLICT)
    def resolve(self, evidence_items, conn=None):
        if not evidence_items:
            self.audit.publish("CONFLICT_BLOCKED", {"reason": errors.EVIDENCE_REQUIRED})
            return errors.EVIDENCE_REQUIRED, []
        evidence_ids = [item.evidence_id for item in evidence_items]
        if len(evidence_ids) != len(set(evidence_ids)):
            self.audit.publish("CONFLICT_BLOCKED", {"reason": errors.DUPLICATE_EVIDENCE})
            return errors.DUPLICATE_EVIDENCE, []
        for item in evidence_items:
            if not item.property_id:
                self.audit.publish("CONFLICT_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
                return errors.PROPERTY_REQUIRED, []
            if not item.field_name:
                self.audit.publish("CONFLICT_BLOCKED", {"reason": errors.FIELD_REQUIRED})
                return errors.FIELD_REQUIRED, []
            if not item.provider_id:
                self.audit.publish("CONFLICT_BLOCKED", {"reason": errors.PROVIDER_REQUIRED})
                return errors.PROVIDER_REQUIRED, []
        property_ids = sorted(set(item.property_id for item in evidence_items))
        if len(property_ids) != 1:
            self.audit.publish("CONFLICT_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return errors.PROPERTY_REQUIRED, []
        property_id = property_ids[0]
        grouped = {}
        for item in evidence_items:
            grouped.setdefault(item.field_name, []).append(item)
        reports = []
        for field_name in sorted(grouped.keys()):
            group = grouped[field_name]
            unique_values = sorted(set(item.normalized_value for item in group))
            if len(unique_values) <= 1:
                continue
            conflict_type = self.classify(field_name)
            report = ConflictReport(
                conflict_id=f"CONFLICT-{property_id}-{field_name}".replace(" ", "_").upper(),
                property_id=property_id,
                field_name=field_name,
                conflict_type=conflict_type,
                providers=sorted(set(item.provider_id for item in group)),
                evidence_ids=[item.evidence_id for item in group],
                observed_values=unique_values,
                source_references=sorted(set(item.source_reference for item in group)),
                status=ConflictStatus.OPEN,
            )
            self.reports[report.conflict_id] = report
            if not self._persist(report, conn=conn):
                del self.reports[report.conflict_id]
                self.audit.publish("CONFLICT_BLOCKED", {
                    "reason": errors.PERSISTENCE_WRITE_FAILED,
                    "conflict_id": report.conflict_id,
                })
                return errors.PERSISTENCE_WRITE_FAILED, []
            reports.append(report)
            self.audit.publish("CONFLICT_DETECTED", {
                "property_id": property_id,
                "field_name": field_name,
                "type": conflict_type.value,
            })
            self.audit.publish("CONFLICT_CLASSIFIED", {
                "conflict_id": report.conflict_id,
                "type": conflict_type.value,
            })
            self.audit.publish("CONFLICT_RECORDED", {
                "conflict_id": report.conflict_id,
                "evidence_count": len(report.evidence_ids),
            })
        self.audit.publish("CONFLICT_PACKAGE_CREATED", {
            "property_id": property_id,
            "conflict_count": len(reports),
        })
        if not reports:
            return errors.NO_CONFLICT, []
        return errors.PASS, reports
    def get_report(self, conflict_id):
        return self.reports.get(conflict_id)
    def attempt_write(self):
        self.audit.publish("CONFLICT_BLOCKED", {"reason": errors.READ_ONLY_CONFLICT})
        return False, errors.READ_ONLY_CONFLICT
    def assign_confidence(self):
        self.audit.publish("CONFLICT_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
