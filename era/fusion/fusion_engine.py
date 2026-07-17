from era.fusion.fusion_audit import FusionAudit
from era.fusion.fusion_models import FieldFusionResult, EvidenceFusionPackage
from era.fusion.fusion_enums import FusionStatus
from era.fusion import fusion_errors as errors
class MultiSourceFusionEngine:
    def __init__(self, audit=None):
        self.audit = audit or FusionAudit()
    def fuse(self, evidence_items):
        if not evidence_items:
            self.audit.publish("FUSION_BLOCKED", {"reason": errors.EVIDENCE_REQUIRED})
            return errors.EVIDENCE_REQUIRED, None
        evidence_ids = [item.evidence_id for item in evidence_items]
        if len(evidence_ids) != len(set(evidence_ids)):
            self.audit.publish("FUSION_BLOCKED", {"reason": errors.DUPLICATE_EVIDENCE})
            return errors.DUPLICATE_EVIDENCE, None
        for item in evidence_items:
            if not item.property_id:
                self.audit.publish("FUSION_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
                return errors.PROPERTY_REQUIRED, None
            if not item.field_name:
                self.audit.publish("FUSION_BLOCKED", {"reason": errors.FIELD_REQUIRED})
                return errors.FIELD_REQUIRED, None
            if not item.provider_id:
                self.audit.publish("FUSION_BLOCKED", {"reason": errors.PROVIDER_REQUIRED})
                return errors.PROVIDER_REQUIRED, None
        property_ids = sorted(set(item.property_id for item in evidence_items))
        if len(property_ids) != 1:
            self.audit.publish("FUSION_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return errors.PROPERTY_REQUIRED, None
        property_id = property_ids[0]
        grouped = {}
        for item in evidence_items:
            grouped.setdefault(item.field_name, []).append(item)
        results = []
        for field_name in sorted(grouped.keys()):
            group = grouped[field_name]
            unique_values = sorted(set(item.normalized_value for item in group))
            evidence_group_ids = [item.evidence_id for item in group]
            if len(group) == 1:
                status = FusionStatus.SINGLE_SOURCE
            elif len(unique_values) == 1:
                status = FusionStatus.CONSENSUS
            else:
                status = FusionStatus.CONFLICT
            result = FieldFusionResult(
                property_id=property_id,
                field_name=field_name,
                status=status,
                source_count=len(group),
                unique_values=unique_values,
                evidence_ids=evidence_group_ids,
            )
            results.append(result)
            self.audit.publish("FIELD_FUSED", {
                "property_id": property_id,
                "field_name": field_name,
                "status": status.value,
                "source_count": len(group),
            })
        package = EvidenceFusionPackage(
            property_id=property_id,
            fields=results,
            evidence_count=len(evidence_items),
        )
        self.audit.publish("FUSION_COMPLETED", {
            "property_id": property_id,
            "field_count": len(results),
            "evidence_count": len(evidence_items),
        })
        return errors.PASS, package
    def attempt_write(self):
        self.audit.publish("FUSION_BLOCKED", {"reason": errors.READ_ONLY_FUSION})
        return False, errors.READ_ONLY_FUSION
    def assign_confidence(self):
        self.audit.publish("FUSION_BLOCKED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
