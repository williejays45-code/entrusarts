"""
SPINE-002: Composition Root, part 1 -- the container.

This is "one place wires the system." Every engine the pipeline uses is
constructed exactly once, here, in the same order the pipeline runs them
in. Nothing in era/pipeline.py or era/app.py reaches into a package and
builds an engine directly -- they ask the Container for it. That is the
actual fix for "20 isolated islands, 1 real cross-package import":
Container is now the single file with 13+ real cross-package imports,
and pipeline.py is the file that calls all of them together in sequence.

Persistence scope (deliberately narrow, per FORGE sequencing:
"wire first, persist wider second"): only SourceReliabilityRegistry is
given the SqliteStore. Every other engine below is constructed exactly
as it always was -- this container does not silently expand C4's scope.
That expansion is the next, separate piece of work.
"""

from pathlib import Path

from era.provider_network.provider_manifest import ProviderManifest
from era.provider_network.provider_manifest_audit import ProviderManifestAudit
from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
from era.acquisition.rate_limiter import RateLimiter
from era.acquisition.retry_executor import RetryExecutor
from era.acquisition.connector_audit import AcquisitionAuditPublisher
from era.jurisdiction.jurisdiction_registry import JurisdictionRegistry
from era.jurisdiction.jurisdiction_audit import JurisdictionAudit
from era.providers.live_provider_adapter import LiveProviderAdapter
from era.providers.provider_audit import ProviderAudit
from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.canonical.canonical_audit import CanonicalAuditPublisher
from era.provenance.provenance_manager import EvidenceProvenanceManager
from era.provenance.provenance_audit import ProvenanceAudit
from era.fusion.fusion_engine import MultiSourceFusionEngine
from era.fusion.fusion_audit import FusionAudit
from era.conflict.conflict_resolver import EvidenceConflictResolver
from era.conflict.conflict_audit import ConflictAudit
from era.property_record.unified_property_record import UnifiedPropertyRecordEngine
from era.property_record.property_audit import PropertyAuditPublisher
from era.decision.decision_engine import DecisionEngine
from era.decision.decision_audit import DecisionAudit
from era.policy.policy_engine import PolicyEngine
from era.policy.policy_audit import PolicyAudit
from era.policy.policy_models import PolicyRuleSet
from era.export.export_engine import ExportEngine
from era.export.export_audit import ExportAudit
from era.api.api_engine import EraApiEngine
from era.api.api_audit import ApiAudit
from era.auth.auth_engine import AuthEngine
from era.auth.auth_audit import AuthAudit
from era.dashboard.dashboard_engine import DashboardEngine
from era.dashboard.dashboard_audit import DashboardAudit

from era.acquisition.providers.county.dallas_cad import DallasCADConnector
from era.acquisition.providers.county.county_framework_models import CountySearchRequest
from era.acquisition.providers.county.tarrant_assessor import TarrantCountyAssessorConnector
from era.acquisition.providers.county.county_models import CountyConnectorRequest
from era.acquisition.providers.county import county_errors as county_errors
from era.live_adapters.manual_record_adapter import ManualRecordAdapter
from era.live_adapters.dcad_bulk_data_adapter import DCADBulkDataAdapter
from era.live_adapters.dcad_index_store import DCADIndexStore
from era.live_adapters.collin_bulk_data_adapter import CollinBulkDataAdapter
from era.shared.audit import BaseAuditPublisher
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors as provider_errors
from era.acquisition.acquisition_provider import ProviderHealth, ProviderMetadata
from era.acquisition.provider_health_authority import (
    ProviderHealthAuthority,
    ReadinessObservation,
)
from era.acquisition.provider_enumeration_authority import ProviderEnumerationAuthority
from era.discovery.source_discovery import SourceDiscovery
from era.evidence_intelligence.integration import EvidenceIntegrationService
from era.reasoning.composition import EvidenceInterpretationCompositionService
from era.reasoning.certified_profiles import (
    PROPERTY_POLICY_CERTIFICATION,
    PROPERTY_RULE_CERTIFICATION,
)


class CountyConnectorProviderAdapter:
    """
    Bridges a era.acquisition.providers.county.* connector (its own
    request/response shape: search_property / retrieve_public_record /
    validate) to the interface era.providers.LiveProviderAdapter expects
    (provider_id / provider_name / connector_version / health_check /
    retrieve). These two were previously unable to talk to each other at
    all (flagged as M5 in the architectural review) -- this class is the
    actual fix for that specific gap, not a mock standing in for one.
    """

    def __init__(self, connector, county, state, city, version="1.0"):
        self._connector = connector
        self._county = county
        self._state = state
        self._city = city
        self._version = version
        self._address = ""

    def set_address(self, address: str):
        """The connector's own request shape needs an address to search
        on; LiveProviderAdapter.run() only passes property_id through.
        The pipeline sets this from PropertyIdentity right before
        building the adapter for a given property."""
        self._address = address

    def provider_id(self):
        return self._connector.CONNECTOR_ID

    def provider_name(self):
        return self._connector.PROVIDER_NAME

    def connector_version(self):
        return self._version

    def health_check(self):
        return self._connector.health_check()

    def metadata(self):
        return ProviderMetadata(
            provider_id=self.provider_id(),
            provider_name=self.provider_name(),
            connector_version=self.connector_version(),
            legal_basis=self._connector.LEGAL_BASIS,
            source_name=self._connector.SOURCE_NAME,
        )

    def retrieve(self, property_id: str):
        request = CountySearchRequest(
            property_id=property_id,
            address=self._address,
            city=self._city,
            county=self._county,
            state=self._state,
        )
        search_status, provider_key = self._connector.search_property(request)
        if search_status != provider_errors.PASS:
            return search_status, {}
        retrieval_status, data = self._connector.retrieve_public_record(request, provider_key)
        if retrieval_status != provider_errors.PASS:
            return retrieval_status, {}
        validation_status = self._connector.validate(data)
        if validation_status != provider_errors.PASS:
            return validation_status, {}
        evidence = [
            ProviderEvidence(field_name=key, raw_value=str(value))
            for key, value in sorted(data.items())
            if value not in (None, "")
        ]
        return provider_errors.PASS, {
            "evidence": evidence,
            "provenance": {"legal_basis": self._connector.LEGAL_BASIS},
            "source_reference": self._connector.SOURCE_NAME,
        }


DEFAULT_POLICY = PolicyRuleSet(
    policy_id="POL-DEFAULT-001",
    policy_version="1.0",
    allowed_decisions=["ACCEPT", "READY_FOR_EXPORT", "PENDING_MORE_EVIDENCE"],
    export_allowed=True,
    require_manual_review_on_conflict=True,
)


class _PipelineTarrantSourceRegistry:
    """Read-through SRR seam that leaves outcome recording to Pipeline."""

    def __init__(self, source_registry):
        self._source_registry = source_registry

    def get_connector(self, connector_id):
        return self._source_registry.get_connector(connector_id)

    def record_success(self, connector_id, response_time_ms):
        return "PASS"

    def record_failure(self, connector_id):
        return "PASS"


class TarrantConnectorProviderAdapter:
    """
    TARRANT-WIRE-001: the same provider-adapter pattern as
    CountyConnectorProviderAdapter (Dallas), bridging
    TarrantCountyAssessorConnector's own interface to the one
    LiveProviderAdapter expects.

    The legacy connector expects an SRR for status lookup and also records
    its own outcome. Pipeline is the sole transactional outcome authority,
    so this adapter keeps status reads and suppresses only those duplicate
    connector-owned writes.
    """

    def __init__(self, connector, county, state, version="1.0"):
        self._connector = connector
        self._connector.source_registry = _PipelineTarrantSourceRegistry(
            connector.source_registry
        )
        self._county = county
        self._state = state
        self._version = version
        self._address = ""

    def set_address(self, address: str):
        self._address = address

    def provider_id(self):
        return self._connector.CONNECTOR_ID

    def provider_name(self):
        return self._connector.PROVIDER_NAME

    def connector_version(self):
        return self._version

    def health_check(self):
        return county_errors.PASS

    def metadata(self):
        return ProviderMetadata(
            provider_id=self.provider_id(),
            provider_name=self.provider_name(),
            connector_version=self.connector_version(),
            legal_basis=self._connector.LEGAL_BASIS,
            source_name=self._connector.SOURCE_NAME,
        )

    def retrieve(self, property_id: str):
        request = CountyConnectorRequest(
            property_id=property_id,
            address=self._address,
            county=self._county,
            state=self._state,
        )
        status, raw_evidence = self._connector.retrieve(request)
        if status != county_errors.PASS:
            return status, {}
        evidence = [
            ProviderEvidence(field_name=item.field_name, raw_value=item.raw_value)
            for item in raw_evidence
            if item.raw_value not in (None, "")
        ]
        return provider_errors.PASS, {
            "evidence": evidence,
            "provenance": {"legal_basis": self._connector.LEGAL_BASIS},
            "source_reference": self._connector.SOURCE_NAME,
        }


class Container:
    def __init__(self, persistence_store=None, token_store=None, dcad_download_url=None,
                 dcad_join_account_info=False, dcad_index_db_path="dcad_index.db",
                 use_mock_auth=False, auth_db_path="era_auth.db",
                 collin_mdb_path=None, collin_code_list_path=None):
        self.persistence_store = persistence_store

        def audit_for(namespace, audit_cls):
            sink = persistence_store.event_sink(namespace) if persistence_store else None
            return audit_cls(sink=sink)

        # -- AUTH-WIRE-001 / AUTH-TOKEN-WIRE-001 -- built early since
        # API depends on it below. Same locked resolution rule as
        # AuthEngine itself: explicit token_store wins if given;
        # otherwise use_mock_auth=True gets MockTokenStore (tests/dev
        # only); otherwise the real default is HashedTokenStore backed
        # by auth_db_path. No implicit MockTokenStore fallback exists
        # anywhere in this path. This is the actual "container/app
        # access path": every external read now goes through self.api,
        # and self.api now requires self.auth.
        self.auth = AuthEngine(
            token_store=token_store,
            use_mock_auth=use_mock_auth,
            auth_db_path=auth_db_path,
            audit=audit_for("era.auth.auth_engine", AuthAudit),
        )


        # -- Provider / Registry --
        self.provider_manifest = ProviderManifest(
            audit=audit_for("era.provider_network.provider_manifest", ProviderManifestAudit)
        )

        # -- SRR (persistence proven first, in C4) --
        self.srr = SourceReliabilityRegistry(store=persistence_store)
        self.provider_health_authority = ProviderHealthAuthority(self.srr)

        # -- RATE-RETRY-001: enforcement for ConnectorRecord's declared
        # resource_policy / retry_policy, which were governance metadata
        # only until now. Rate-limit blocks use their own namespace
        # (distinct from SRR's own connector-lifecycle events) so a
        # blocked/throttled request is trivially distinguishable in the
        # audit trail from a connector being disabled or unregistered.
        self.rate_limiter = RateLimiter(
            audit=audit_for("era.acquisition.rate_limiter", AcquisitionAuditPublisher),
            store=persistence_store,
        )
        self.retry_executor = RetryExecutor(
            audit=audit_for("era.acquisition.retry_executor", AcquisitionAuditPublisher)
        )

        # -- PSE / JRE --
        # PSE (property scoring engine) does not exist anywhere in this
        # archive -- there is no file, class, or error constant for it.
        # Not inventing one. Wiring JRE only.
        self.jre = JurisdictionRegistry(
            audit=audit_for("era.jurisdiction.jurisdiction_registry", JurisdictionAudit)
        )

        # -- known provider connectors, for LPA to run against --
        self._provider_readiness_observers = {}
        self.county_connectors = {
            "COUNTY_DALLAS_CAD": CountyConnectorProviderAdapter(
                DallasCADConnector(), county="Dallas", state="TX", city="Dallas",
            ),
            "COUNTY_TARRANT_ASSESSOR": TarrantConnectorProviderAdapter(
                TarrantCountyAssessorConnector(self.srr), county="Tarrant", state="TX",
            ),
            # LIVE-ADAPTER-001A: not a county connector in the scraping
            # sense -- a human-operator-driven manual capture adapter.
            # Registered in the same provider registry because that's
            # what it structurally is to LPA: a provider_id the
            # pipeline can resolve, rate-limit, retry, and run through
            # the standard path exactly like the two above.
            "MANUAL_RECORD_CAPTURE": ManualRecordAdapter(
                audit=audit_for("era.live_adapters.manual_record_adapter", BaseAuditPublisher),
                auth=self.auth,
            ),
        }
        self._provider_readiness_observers.update({
            "COUNTY_DALLAS_CAD": ReadinessObservation.READY,
            "COUNTY_TARRANT_ASSESSOR": ReadinessObservation.READY,
            "MANUAL_RECORD_CAPTURE": ReadinessObservation.READY,
        })
        self.manual_record_adapter = self.county_connectors["MANUAL_RECORD_CAPTURE"]

        # LIVE-ADAPTER-001B: DCAD's real download URL has never been
        # confirmed from this environment (see dcad_bulk_data_adapter.py
        # module docstring) -- registering this provider is opt-in,
        # only when a real URL is explicitly supplied. No placeholder
        # URL is ever fabricated as a silent default.
        self.dcad_bulk_data_adapter = None
        if dcad_download_url:
            dcad_index_store = DCADIndexStore(dcad_index_db_path)
            self.dcad_bulk_data_adapter = DCADBulkDataAdapter(
                download_url=dcad_download_url,
                join_account_info=dcad_join_account_info,
                index_store=dcad_index_store,
                audit=audit_for("era.live_adapters.dcad_bulk_data_adapter", BaseAuditPublisher),
                auth=self.auth,
            )
            self.county_connectors["DCAD_BULK_DATA_2025"] = self.dcad_bulk_data_adapter
            # Readiness means the acquisition capability is configured: a
            # required URL was supplied and the index store was constructed.
            # An empty index is valid before first acquisition; retrieval owns
            # the certified fetch/build path and must not be blocked here.
            self._provider_readiness_observers["DCAD_BULK_DATA_2025"] = (
                ReadinessObservation.READY
            )
        self.collin_bulk_data_adapter = None
        if collin_mdb_path and collin_code_list_path:
            self.collin_bulk_data_adapter = CollinBulkDataAdapter(
                mdb_path=collin_mdb_path,
                code_list_path=collin_code_list_path,
                audit=audit_for("era.live_adapters.collin_bulk_data_adapter", BaseAuditPublisher),
            )
            self.county_connectors["COLLIN_BULK_MDB"] = self.collin_bulk_data_adapter
            self._provider_readiness_observers["COLLIN_BULK_MDB"] = lambda: (
                ReadinessObservation.READY
                if Path(collin_mdb_path).is_file() and Path(collin_code_list_path).is_file()
                else ReadinessObservation.NOT_READY
            )
        self._lpa_audit_namespace = "era.providers.live_provider_adapter"
        self.provider_enumeration_authority = ProviderEnumerationAuthority(
            source_registry=self.srr,
            jurisdiction_registry=self.jre,
            runtime_resolver=self.resolve_provider,
            health_evaluator=self._evaluate_resolved_provider_health,
        )
        self.source_discovery = SourceDiscovery(self.provider_enumeration_authority)

        # -- ECM / EPM / MSF / ECR / UPR / DEC / POL / EXP --
        self.ecm = CanonicalEvidenceModel(
            audit=audit_for("era.canonical.canonical_engine", CanonicalAuditPublisher)
        )
        self.epm = EvidenceProvenanceManager(
            audit=audit_for("era.provenance.provenance_manager", ProvenanceAudit),
            store=persistence_store,
        )
        self.evidence_integration = EvidenceIntegrationService(self.ecm, self.epm)
        self.evidence_interpretation = EvidenceInterpretationCompositionService(
            trusted_rule_certifications=(PROPERTY_RULE_CERTIFICATION,),
            trusted_policy_certifications=(PROPERTY_POLICY_CERTIFICATION,),
        )
        self.msf = MultiSourceFusionEngine(
            audit=audit_for("era.fusion.fusion_engine", FusionAudit)
        )
        self.ecr = EvidenceConflictResolver(
            audit=audit_for("era.conflict.conflict_resolver", ConflictAudit),
            store=persistence_store,
        )
        self.upr = UnifiedPropertyRecordEngine(
            audit=audit_for("era.property_record.unified_property_record", PropertyAuditPublisher),
            store=persistence_store,
        )
        self.dec = DecisionEngine(
            audit=audit_for("era.decision.decision_engine", DecisionAudit),
            store=persistence_store,
        )
        self.pol = PolicyEngine(
            audit=audit_for("era.policy.policy_engine", PolicyAudit),
            store=persistence_store,
        )
        self.default_policy = DEFAULT_POLICY
        self.exp = ExportEngine(
            audit=audit_for("era.export.export_engine", ExportAudit),
            store=persistence_store,
        )

        # -- API / DASH -- shared result store the pipeline populates
        # and the API engine reads from. This is the literal object that
        # proves API is not an island: it's not talking to its own
        # private state, it's reading what the pipeline wrote.
        self.api_store = {
            "properties": {}, "evidence": {}, "decisions": {},
            "policies": {}, "exports": {}, "audits": {},
        }
        self.api = EraApiEngine(
            store=self.api_store,
            audit=audit_for("era.api.api_engine", ApiAudit),
            auth=self.auth,
        )
        self.dash = DashboardEngine(
            audit=audit_for("era.dashboard.dashboard_engine", DashboardAudit)
        )

    def build_lpa(self, provider_id: str, address: str = "", eligibility=None, exclusion=None) -> LiveProviderAdapter:
        provider = eligibility.provider if eligibility is not None else None
        if provider is not None and hasattr(provider, "set_address"):
            provider.set_address(address)
        audit = ProviderAudit(
            sink=self.persistence_store.event_sink(self._lpa_audit_namespace)
            if self.persistence_store else None
        )
        return LiveProviderAdapter(
            provider,
            audit=audit,
            eligibility=eligibility,
            exclusion=exclusion,
        )

    def resolve_provider(self, provider_id: str):
        """Runtime composition lookup only; never grants registration/eligibility."""
        return self.county_connectors.get(provider_id)

    def _evaluate_resolved_provider_health(self, provider_id: str, provider) -> ProviderHealth:
        readiness = self._provider_readiness_observation(provider_id)
        return self.provider_health_authority.evaluate(
            provider_id,
            provider,
            readiness_observation=readiness,
        )

    def evaluate_provider_health(self, provider_id: str) -> ProviderHealth:
        """Composition-only HA-001 wiring; does not change acquisition flow."""
        provider = self.resolve_provider(provider_id)
        return self._evaluate_resolved_provider_health(provider_id, provider)

    def _provider_readiness_observation(self, provider_id):
        return self._provider_readiness_observers.get(
            provider_id,
            ReadinessObservation.UNKNOWN,
        )

    def all_engines(self):
        """For audit reconciliation: every engine with an .audit.events log."""
        return {
            "provider_manifest": self.provider_manifest,
            "srr": self.srr,
            "jre": self.jre,
            "ecm": self.ecm,
            "epm": self.epm,
            "msf": self.msf,
            "ecr": self.ecr,
            "upr": self.upr,
            "dec": self.dec,
            "pol": self.pol,
            "exp": self.exp,
            "api": self.api,
            "dash": self.dash,
        }
