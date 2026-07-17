import sys
from era.providers.live_provider_adapter import LiveProviderAdapter
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors
from era.acquisition.acquisition_provider import ProviderHealth
from era.acquisition.provider_health_authority import HEALTHY
from era.acquisition.provider_enumeration_authority import (
    ProviderEligibilityProjection,
    ProviderEnumerationDetail,
    ProviderEnumerationResult,
)
from era.orchestration.orchestration_models import OrchestrationRequest
from era.orchestration.era_orchestrator import ERAOrchestrationEngine
from era.orchestration import orchestration_errors
from era.property_record.unified_property_record import UnifiedPropertyRecordEngine
from era.property_record.property_models import PropertyIdentity, EvidenceEntry
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record import property_errors
class DallasCADProvider:
    def provider_id(self):
        return "COUNTY_DALLAS_CAD"
    def provider_name(self):
        return "Dallas Central Appraisal District"
    def connector_version(self):
        return "1.0"
    def health_check(self):
        return True
    def retrieve(self, property_id):
        return provider_errors.PASS, {
            "source_reference": "DCAD-PUBLIC-SEARCH-MANUAL-CAPTURE",
            "provenance": {"legal_basis": "PUBLIC_RECORD"},
            "evidence": [
                ProviderEvidence("address", "5926 Sandhurst Ln Unit 224"),
                ProviderEvidence("city", "Dallas"),
                ProviderEvidence("county", "Dallas"),
                ProviderEvidence("state", "TX"),
                ProviderEvidence("property_type", "CONDOMINIUM"),
            ],
        }
class LPAProviderBridge:
    def __init__(self, provider):
        self.eligibility = ProviderEligibilityProjection(
            provider.provider_id(), object(), provider, ProviderHealth(True, HEALTHY)
        )
        self.adapter = LiveProviderAdapter(provider, eligibility=self.eligibility)
    def retrieve(self, property_id):
        status, package = self.adapter.run(property_id)
        if status != provider_errors.PASS:
            return orchestration_errors.PROVIDER_FAILED, []
        return orchestration_errors.PASS, [
            {"field": item.field_name, "value": item.raw_value}
            for item in package.evidence
        ]
class MockSourceRegistry:
    def get_connector(self, provider_id):
        class Connector:
            status = "ACTIVE"
        return Connector()
class SimpleCanonical:
    def canonicalize(self, raw_evidence):
        return orchestration_errors.PASS, [
            {"field_name": item["field"], "normalized_value": item["value"]}
            for item in raw_evidence
        ]
class UPRBridge:
    def __init__(self):
        self.upr = UnifiedPropertyRecordEngine()
        identity = PropertyIdentity(
            property_id="ERA-PR-2026-000001",
            address="5926 Sandhurst Ln Unit 224",
            city="Dallas",
            state="TX",
            zip_code="75206",
            county="Dallas",
            parcel_apn="DCAD-PENDING",
            latitude=None,
            longitude=None,
            property_type=PropertyType.CONDO,
            strategy_type=StrategyType.BUY_HOLD,
        )
        self.upr.create_property(identity)
    def update_property(self, property_id, canonical_records):
        added = 0
        for index, rec in enumerate(canonical_records, start=1):
            evidence = EvidenceEntry(
                evidence_id=f"LPI-DCAD-{index:03d}",
                property_id=property_id,
                category="IDENTITY",
                value=rec["normalized_value"],
                connector="COUNTY_DALLAS_CAD",
                original_source="Dallas Central Appraisal District",
                retrieved_at="LPA-001",
                normalization_version="LPI-001",
                audit_reference="LPI-001-DCAD",
            )
            status, _ = self.upr.add_evidence(property_id, evidence)
            if status == property_errors.PASS:
                added += 1
        return orchestration_errors.PASS if added == len(canonical_records) else orchestration_errors.UPR_UPDATE_FAILED
class MockERI:
    def trigger(self, property_id):
        return orchestration_errors.PASS
print("LPI-001 LIVE PROVIDER INTEGRATION VERIFICATION")
print("=" * 70)
engine = ERAOrchestrationEngine(
    source_registry=MockSourceRegistry(),
    providers={
        "COUNTY_DALLAS_CAD": LPAProviderBridge(DallasCADProvider())
    },
    canonical=SimpleCanonical(),
    upr=UPRBridge(),
    eri=MockERI(),
    eligibility_evaluator=lambda provider_ids: ProviderEnumerationResult(
        eligible=(ProviderEligibilityProjection(
            "COUNTY_DALLAS_CAD",
            object(),
            engine_provider := LPAProviderBridge(DallasCADProvider()),
            ProviderHealth(True, HEALTHY),
        ),),
        exclusions=(),
        detail=ProviderEnumerationDetail(
            seeded=("COUNTY_DALLAS_CAD",), geographic_mappings=("COUNTY_DALLAS_CAD",),
            after_lifecycle=("COUNTY_DALLAS_CAD",), after_capability=("COUNTY_DALLAS_CAD",),
            after_geography=("COUNTY_DALLAS_CAD",), after_runtime=("COUNTY_DALLAS_CAD",),
            after_health=("COUNTY_DALLAS_CAD",),
        ),
    ),
)
status, result = engine.run(
    OrchestrationRequest(
        property_id="ERA-PR-2026-000001",
        providers=["COUNTY_DALLAS_CAD"],
    )
)
happy_ok = (
    status == orchestration_errors.PASS
    and result is not None
    and result.property_id == "ERA-PR-2026-000001"
    and result.providers_run == ["COUNTY_DALLAS_CAD"]
    and result.evidence_count == 5
    and result.canonical_count == 5
)
print("STATUS:", status)
print("PROPERTY:", result.property_id if result else None)
print("PROVIDERS:", result.providers_run if result else None)
print("EVIDENCE COUNT:", result.evidence_count if result else None)
print("CANONICAL COUNT:", result.canonical_count if result else None)
print("PASS:", happy_ok)
print()
print("EOE AUDIT EVENTS:", len(engine.audit.events))
for event in engine.audit.events:
    print(event)
print()
print("OVERALL:", "PASS" if happy_ok else "FAIL")
_ERA_OVERALL_OK = (happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
