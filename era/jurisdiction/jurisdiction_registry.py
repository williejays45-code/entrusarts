from era.jurisdiction.jurisdiction_audit import JurisdictionAudit
from era.jurisdiction.jurisdiction_models import JurisdictionRecord
from era.jurisdiction.jurisdiction_enums import ProviderOperationalStatus, ProviderRole
from era.jurisdiction import jurisdiction_errors as errors
class JurisdictionRegistry:
    def __init__(self, audit=None):
        self.records = {}
        self.audit = audit or JurisdictionAudit()
    def _key(self, state: str, county: str):
        return f"{state.strip().upper()}::{county.strip().upper()}"
    def register_jurisdiction(self, record: JurisdictionRecord):
        if record is None:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.JURISDICTION_REQUIRED})
            return errors.JURISDICTION_REQUIRED
        if not record.state:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.STATE_REQUIRED})
            return errors.STATE_REQUIRED
        if not record.county:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.COUNTY_REQUIRED})
            return errors.COUNTY_REQUIRED
        if not record.providers:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.PROVIDER_REQUIRED})
            return errors.PROVIDER_REQUIRED
        provider_ids = [provider.provider_id for provider in record.providers]
        if len(provider_ids) != len(set(provider_ids)):
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.DUPLICATE_PROVIDER})
            return errors.DUPLICATE_PROVIDER
        for provider in record.providers:
            if not isinstance(provider.role, ProviderRole):
                self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.PROVIDER_REQUIRED})
                return errors.PROVIDER_REQUIRED
            if not isinstance(provider.status, ProviderOperationalStatus):
                self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.PROVIDER_REQUIRED})
                return errors.PROVIDER_REQUIRED
        key = self._key(record.state, record.county)
        if key in self.records:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.DUPLICATE_JURISDICTION})
            return errors.DUPLICATE_JURISDICTION
        self.records[key] = record
        self.audit.publish("JURISDICTION_REGISTERED", {
            "state": record.state,
            "county": record.county,
            "provider_count": len(record.providers),
        })
        return errors.PASS
    def resolve(self, request, operational_only=False):
        if request is None:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.JURISDICTION_REQUIRED})
            return errors.JURISDICTION_REQUIRED, []
        if not request.state:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.STATE_REQUIRED})
            return errors.STATE_REQUIRED, []
        if not request.county:
            self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.COUNTY_REQUIRED})
            return errors.COUNTY_REQUIRED, []
        record = self.records.get(self._key(request.state, request.county))
        if record is None:
            self.audit.publish("JURISDICTION_BLOCKED", {
                "reason": errors.JURISDICTION_NOT_FOUND,
                "state": request.state,
                "county": request.county,
            })
            return errors.JURISDICTION_NOT_FOUND, []
        providers = record.providers
        if operational_only:
            providers = [
                provider for provider in providers
                if provider.status == ProviderOperationalStatus.OPERATIONAL
            ]
        self.audit.publish("JURISDICTION_RESOLVED", {
            "state": request.state,
            "county": request.county,
            "provider_count": len(providers),
            "operational_only": operational_only,
        })
        return errors.PASS, providers
    def list_provider_ids(self, state: str, county: str):
        """Geographic mapping only; provider status is intentionally ignored."""
        record = self.records.get(self._key(state, county))
        if record is None:
            return tuple()
        return tuple(sorted({provider.provider_id for provider in record.providers}))
    def attempt_write(self):
        self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.READ_ONLY_JURISDICTION})
        return False, errors.READ_ONLY_JURISDICTION
    def assign_confidence(self):
        self.audit.publish("JURISDICTION_BLOCKED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
