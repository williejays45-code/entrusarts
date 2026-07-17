from era.providers.provider_audit import ProviderAudit
from era.providers.provider_models import ProviderPackage
from era.providers import provider_errors as errors
from era.acquisition.provider_enumeration_authority import ProviderEligibilityProjection
class LiveProviderAdapter:
    """
    LPA-001 standard adapter.
    Packages authorized provider evidence only.
    It does not normalize, store, reason, or assign confidence.
    """
    def __init__(self, provider, audit=None, eligibility=None, exclusion=None):
        self.provider = provider
        self.audit = audit or ProviderAudit()
        self.eligibility = eligibility
        self.exclusion = exclusion
    def run(self, property_id: str):
        if not isinstance(self.eligibility, ProviderEligibilityProjection):
            if self.provider is None and self.exclusion is None:
                self.audit.publish("PROVIDER_FAILED", {"reason": errors.PROVIDER_REQUIRED})
                return errors.PROVIDER_REQUIRED, None
            eligibility_reason = getattr(self.exclusion, "reason", "PROVIDER_NOT_ELIGIBLE")
            self.audit.publish("PROVIDER_FAILED", {
                "reason": errors.PROVIDER_UNAVAILABLE,
                "eligibility_reason": eligibility_reason,
            })
            return errors.PROVIDER_UNAVAILABLE, None
        if self.provider is None:
            self.audit.publish("PROVIDER_FAILED", {"reason": errors.PROVIDER_REQUIRED})
            return errors.PROVIDER_REQUIRED, None
        provider_id = self.provider.provider_id()
        if provider_id != self.eligibility.provider_id:
            self.audit.publish("PROVIDER_FAILED", {
                "reason": errors.PROVIDER_UNAUTHORIZED,
                "provider_id": provider_id,
            })
            return errors.PROVIDER_UNAUTHORIZED, None
        self.audit.publish("PROVIDER_CONNECTED", {"provider_id": provider_id})
        self.audit.publish("PROVIDER_REQUESTED", {"provider_id": provider_id, "property_id": property_id})
        status, response = self.provider.retrieve(property_id)
        if status != errors.PASS:
            self.audit.publish("PROVIDER_FAILED", {"reason": status})
            return status, None
        evidence = response.get("evidence", [])
        provenance = response.get("provenance")
        source_reference = response.get("source_reference")
        if not evidence:
            self.audit.publish("PROVIDER_FAILED", {"reason": errors.EMPTY_EVIDENCE})
            return errors.EMPTY_EVIDENCE, None
        if not provenance:
            self.audit.publish("PROVIDER_FAILED", {"reason": errors.PROVENANCE_MISSING})
            return errors.PROVENANCE_MISSING, None
        if not source_reference:
            self.audit.publish("PROVIDER_FAILED", {"reason": errors.SOURCE_REFERENCE_MISSING})
            return errors.SOURCE_REFERENCE_MISSING, None
        package = ProviderPackage(
            provider_id=provider_id,
            provider_name=self.provider.provider_name(),
            legal_basis=provenance.get("legal_basis", ""),
            source_reference=source_reference,
            property_id=property_id,
            evidence=evidence,
            connector_version=self.provider.connector_version(),
            adapter_version="LPA-001.0",
        )
        if not package.legal_basis or not package.property_id:
            self.audit.publish("PROVIDER_FAILED", {"reason": errors.INVALID_PACKAGE})
            return errors.INVALID_PACKAGE, None
        self.audit.publish("PROVIDER_RESPONSE_RECEIVED", {
            "provider_id": provider_id,
            "evidence_count": len(evidence),
        })
        self.audit.publish("PROVIDER_PACKAGE_CREATED", {
            "provider_id": provider_id,
            "property_id": property_id,
        })
        self.audit.publish("PROVIDER_COMPLETED", {
            "provider_id": provider_id,
            "property_id": property_id,
            "evidence_count": len(evidence),
        })
        return errors.PASS, package
    def attempt_write(self):
        self.audit.publish("PROVIDER_FAILED", {"reason": errors.READ_ONLY_PROVIDER})
        return False, errors.READ_ONLY_PROVIDER
    def assign_confidence(self):
        self.audit.publish("PROVIDER_FAILED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
