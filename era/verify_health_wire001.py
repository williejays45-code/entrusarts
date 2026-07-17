"""HA-WIRE-001 compatibility after PER-001 shared eligibility wiring."""

from pathlib import Path

from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.provider_health_authority import HEALTHY
from era.acquisition.provider_enumeration_authority import (
    HEALTH_UNAVAILABLE,
    ProviderEligibilityProjection,
    ProviderExclusion,
)
from era.providers.live_provider_adapter import LiveProviderAdapter
from era.providers import provider_errors


class Provider:
    def __init__(self): self.retrievals = 0
    def provider_id(self): return "COUNTY_DALLAS_CAD"
    def provider_name(self): return "Dallas CAD"
    def connector_version(self): return "1.0"
    def retrieve(self, property_id):
        self.retrievals += 1
        return provider_errors.PASS, {
            "evidence": [object()], "provenance": {"legal_basis": "PUBLIC_RECORD"},
            "source_reference": "DCAD",
        }


checks = {}
provider = Provider()
eligibility = ProviderEligibilityProjection(
    provider.provider_id(), object(), provider, ProviderHealth(True, HEALTHY)
)
adapter = LiveProviderAdapter(provider, eligibility=eligibility)
status, _ = adapter.run("P")
checks["lpa_consumes_shared_eligibility"] = status == provider_errors.PASS and provider.retrievals == 1

blocked_provider = Provider()
blocked = LiveProviderAdapter(
    blocked_provider,
    exclusion=ProviderExclusion(blocked_provider.provider_id(), HEALTH_UNAVAILABLE),
)
blocked_status, _ = blocked.run("P")
checks["lpa_blocks_ineligible_provider"] = blocked_status == provider_errors.PROVIDER_UNAVAILABLE
checks["ineligible_provider_not_retrieved"] = blocked_provider.retrievals == 0

era_dir = Path(__file__).resolve().parent
lpa_source = (era_dir / "providers" / "live_provider_adapter.py").read_text(encoding="utf-8")
orch_source = (era_dir / "orchestration" / "era_orchestrator.py").read_text(encoding="utf-8")
checks["no_lpa_direct_probe"] = "health_check(" not in lpa_source
checks["no_orchestrator_direct_health"] = "health_evaluator" not in orch_source
checks["no_lpa_allowlist"] = "APPROVED_PROVIDERS" not in lpa_source
checks["no_orchestrator_allowlist"] = "APPROVED_PROVIDERS" not in orch_source

for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values())
print(f"HA-WIRE-001 CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
