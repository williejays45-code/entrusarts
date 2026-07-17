from dataclasses import replace
from era.provider_network.provider_manifest_audit import ProviderManifestAudit
from era.provider_network.provider_manifest_enums import ProviderNetworkStatus, ProviderNetworkRole
from era.provider_network import provider_manifest_errors as errors
class ProviderManifest:
    def __init__(self, audit=None):
        self.providers = {}
        self.audit = audit or ProviderManifestAudit()
    def register_provider(self, provider):
        if provider is None:
            self.audit.publish("PROVIDER_BLOCKED", {"reason": errors.PROVIDER_REQUIRED})
            return errors.PROVIDER_REQUIRED
        if not provider.provider_id:
            self.audit.publish("PROVIDER_BLOCKED", {"reason": errors.PROVIDER_ID_REQUIRED})
            return errors.PROVIDER_ID_REQUIRED
        if provider.provider_id in self.providers:
            self.audit.publish("PROVIDER_BLOCKED", {
                "reason": errors.DUPLICATE_PROVIDER,
                "provider_id": provider.provider_id,
            })
            return errors.DUPLICATE_PROVIDER
        if not isinstance(provider.status, ProviderNetworkStatus):
            self.audit.publish("PROVIDER_BLOCKED", {"reason": errors.INVALID_STATUS})
            return errors.INVALID_STATUS
        if not isinstance(provider.role, ProviderNetworkRole):
            self.audit.publish("PROVIDER_BLOCKED", {"reason": errors.INVALID_ROLE})
            return errors.INVALID_ROLE
        self.providers[provider.provider_id] = provider
        self.audit.publish("PROVIDER_REGISTERED", {
            "provider_id": provider.provider_id,
            "state": provider.state,
            "county": provider.county,
            "role": provider.role.value,
            "status": provider.status.value,
        })
        return errors.PASS
    def update_status(self, provider_id, status):
        provider = self.providers.get(provider_id)
        if provider is None:
            self.audit.publish("PROVIDER_BLOCKED", {
                "reason": errors.UNKNOWN_PROVIDER,
                "provider_id": provider_id,
            })
            return errors.UNKNOWN_PROVIDER
        if not isinstance(status, ProviderNetworkStatus):
            self.audit.publish("PROVIDER_BLOCKED", {"reason": errors.INVALID_STATUS})
            return errors.INVALID_STATUS
        self.providers[provider_id] = replace(provider, status=status)
        self.audit.publish("PROVIDER_STATUS_UPDATED", {
            "provider_id": provider_id,
            "status": status.value,
        })
        return errors.PASS
    def get_provider(self, provider_id):
        return self.providers.get(provider_id)
    def list_by_state(self, state):
        target = state.strip().upper()
        return [
            provider for provider in self.providers.values()
            if provider.state.strip().upper() == target
        ]
    def list_operational(self):
        return [
            provider for provider in self.providers.values()
            if provider.status == ProviderNetworkStatus.OPERATIONAL
        ]
    def attempt_write(self):
        self.audit.publish("PROVIDER_BLOCKED", {
            "reason": errors.READ_ONLY_MANIFEST,
        })
        return False, errors.READ_ONLY_MANIFEST
    def assign_confidence(self):
        self.audit.publish("PROVIDER_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
