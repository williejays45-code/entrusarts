from era.orchestration.orchestration_audit import OrchestrationAudit
from era.orchestration.orchestration_models import OrchestrationResult
from era.orchestration import orchestration_errors as errors
from era.acquisition.provider_enumeration_authority import (
    NOT_ACTIVE,
    PROVIDER_NOT_REGISTERED,
    ProviderEnumerationResult,
)
class ERAOrchestrationEngine:
    def __init__(self, source_registry, providers, canonical, upr, eri, audit=None, eligibility_evaluator=None):
        self.source_registry = source_registry
        self.providers = providers
        self.canonical = canonical
        self.upr = upr
        self.eri = eri
        self.audit = audit or OrchestrationAudit()
        self.eligibility_evaluator = eligibility_evaluator
    def run(self, request):
        if request is None or not request.property_id:
            self.audit.publish("ORCHESTRATION_BLOCKED", {
                "reason": errors.PROPERTY_REQUIRED,
            })
            return errors.PROPERTY_REQUIRED, None
        if not request.providers:
            self.audit.publish("ORCHESTRATION_BLOCKED", {
                "reason": errors.PROVIDER_REQUIRED,
            })
            return errors.PROVIDER_REQUIRED, None
        self.audit.publish("ORCHESTRATION_STARTED", {
            "property_id": request.property_id,
            "providers": request.providers,
        })
        raw_evidence = []
        providers_run = []
        enumeration = (
            self.eligibility_evaluator(tuple(request.providers))
            if callable(self.eligibility_evaluator)
            else None
        )
        if not isinstance(enumeration, ProviderEnumerationResult):
            self.audit.publish("ORCHESTRATION_BLOCKED", {
                "reason": errors.PROVIDER_FAILED,
                "eligibility_reason": "ENUMERATION_AUTHORITY_REQUIRED",
            })
            return errors.PROVIDER_FAILED, None
        for provider_id in request.providers:
            eligibility = enumeration.get(provider_id)
            if eligibility is None:
                exclusion = enumeration.exclusion_for(provider_id)
                eligibility_reason = getattr(exclusion, "reason", "PROVIDER_NOT_ELIGIBLE")
                public_reason = (
                    errors.PROVIDER_NOT_APPROVED
                    if eligibility_reason == PROVIDER_NOT_REGISTERED
                    else errors.PROVIDER_DISABLED
                    if eligibility_reason == NOT_ACTIVE
                    else errors.PROVIDER_FAILED
                )
                self.audit.publish("ORCHESTRATION_BLOCKED", {
                    "reason": public_reason,
                    "provider": provider_id,
                    "eligibility_reason": eligibility_reason,
                })
                return public_reason, None
            provider = eligibility.provider
            self.audit.publish("PROVIDER_SELECTED", {
                "provider": provider_id,
            })
            status, evidence = provider.retrieve(request.property_id)
            if status != errors.PASS:
                self.audit.publish("PROVIDER_FAILED", {
                    "reason": errors.PROVIDER_FAILED,
                    "provider": provider_id,
                })
                return errors.PROVIDER_FAILED, None
            if not evidence:
                self.audit.publish("PROVIDER_FAILED", {
                    "reason": errors.NO_EVIDENCE_RETURNED,
                    "provider": provider_id,
                })
                return errors.NO_EVIDENCE_RETURNED, None
            raw_evidence.extend(evidence)
            providers_run.append(provider_id)
            self.audit.publish("EVIDENCE_COLLECTED", {
                "provider": provider_id,
                "count": len(evidence),
            })
        canonical_status, canonical_records = self.canonical.canonicalize(raw_evidence)
        if canonical_status != errors.PASS:
            self.audit.publish("ORCHESTRATION_BLOCKED", {
                "reason": errors.CANONICALIZATION_FAILED,
            })
            return errors.CANONICALIZATION_FAILED, None
        self.audit.publish("CANONICALIZATION_COMPLETED", {
            "count": len(canonical_records),
        })
        upr_status = self.upr.update_property(request.property_id, canonical_records)
        if upr_status != errors.PASS:
            self.audit.publish("ORCHESTRATION_BLOCKED", {
                "reason": errors.UPR_UPDATE_FAILED,
            })
            return errors.UPR_UPDATE_FAILED, None
        self.audit.publish("UPR_UPDATED", {
            "property_id": request.property_id,
            "count": len(canonical_records),
        })
        eri_status = self.eri.trigger(request.property_id)
        if eri_status != errors.PASS:
            self.audit.publish("ORCHESTRATION_BLOCKED", {
                "reason": errors.ERI_TRIGGER_FAILED,
            })
            return errors.ERI_TRIGGER_FAILED, None
        self.audit.publish("ERI_TRIGGERED", {
            "property_id": request.property_id,
        })
        result = OrchestrationResult(
            property_id=request.property_id,
            providers_run=providers_run,
            evidence_count=len(raw_evidence),
            canonical_count=len(canonical_records),
            status=errors.PASS,
        )
        self.audit.publish("ORCHESTRATION_COMPLETED", {
            "property_id": request.property_id,
            "providers_run": providers_run,
            "evidence_count": len(raw_evidence),
            "canonical_count": len(canonical_records),
        })
        return errors.PASS, result
    def attempt_write(self):
        self.audit.publish("ORCHESTRATION_BLOCKED", {
            "reason": errors.READ_ONLY_ORCHESTRATOR,
        })
        return False, errors.READ_ONLY_ORCHESTRATOR
    def assign_confidence(self):
        self.audit.publish("ORCHESTRATION_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
