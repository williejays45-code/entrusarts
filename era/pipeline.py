"""
SPINE-002: Composition Root, part 2 -- the pipeline.

This is where the 20 previously-isolated packages actually talk to each
other. Every hop below is a real adapter converting one engine's real
output dataclass into the next engine's real input dataclass -- not a
bare string or a caller-supplied trace ID (that pattern is exactly what
C2 closed inside recommendation; this file is the same discipline
applied at the pipeline level: each stage only consumes what the
previous stage actually produced).

Pipeline order (per FORGE spec):
  Provider/Registry -> SRR -> JRE -> LPA -> ECM -> EPM -> MSF -> ECR
  -> UPR -> DEC -> POL -> EXP -> API/DASH

RATE-RETRY-001 adds a RATE_LIMIT gate between SRR and LPA, and wraps
the LPA call itself with retry enforcement -- see era.acquisition
.rate_limiter / .retry_executor. Neither changes what any stage from
ECM onward does; they only gate/wrap the request that produces LPA's
input.

PSE is not wired -- it does not exist anywhere in this archive.
"""

from dataclasses import dataclass, field, asdict
import threading
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.canonical import canonical_errors as canonical_errors
from era.provenance.provenance_models import ProvenanceInput
from era.provenance import provenance_errors as provenance_errors
from era.fusion.fusion_models import FusionEvidence
from era.fusion import fusion_errors as fusion_errors
from era.conflict import conflict_errors as conflict_errors
from era.property_record.property_models import PropertyIdentity, EvidenceEntry
from era.property_record import property_errors as property_errors
from era.decision.decision_models import DecisionInput
from era.decision.decision_enums import DecisionState
from era.decision import decision_errors as decision_errors
from era.policy.policy_models import PolicyDecisionInput
from era.policy import policy_errors as policy_errors
from era.export.export_models import ExportRequest
from era.export.export_enums import ExportFormat
from era.export import export_errors as export_errors
from era.jurisdiction.jurisdiction_models import JurisdictionRequest
from era.jurisdiction import jurisdiction_errors as jurisdiction_errors
from era.providers import provider_errors as provider_errors
from era.acquisition.connector_enums import ConnectorStatus
from era.acquisition.provider_enumeration_authority import ProviderEnumerationRequest


FIELD_CATEGORY = {
    "property_address": EvidenceCategory.IDENTITY,
    "city": EvidenceCategory.IDENTITY,
    "county": EvidenceCategory.IDENTITY,
    "state": EvidenceCategory.IDENTITY,
    "property_type": EvidenceCategory.BUILDING,
    "total_appraised_value": EvidenceCategory.MARKET,
    "land_value": EvidenceCategory.LAND,
    "improvement_value": EvidenceCategory.BUILDING,
    "parcel_id": EvidenceCategory.PARCEL,
    "owner_name": EvidenceCategory.OWNERSHIP,
    "legal_description": EvidenceCategory.LEGAL,
    "zip_code": EvidenceCategory.IDENTITY,
    "source_record_id": EvidenceCategory.IDENTITY,
    "owner_mailing_address": EvidenceCategory.OWNERSHIP,
    "owner_mailing_city": EvidenceCategory.OWNERSHIP,
    "owner_mailing_state": EvidenceCategory.OWNERSHIP,
    "owner_mailing_zip_code": EvidenceCategory.OWNERSHIP,
    "legal_acreage": EvidenceCategory.LAND,
    "effective_size_acres": EvidenceCategory.LAND,
    "land_area_sqft": EvidenceCategory.LAND,
    "living_area": EvidenceCategory.BUILDING,
    "state_code": EvidenceCategory.PARCEL,
    "state_description": EvidenceCategory.PARCEL,
    "property_use_code": EvidenceCategory.PARCEL,
    "property_use_description": EvidenceCategory.PARCEL,
    "property_type_code": EvidenceCategory.PARCEL,
    "land_type_code": EvidenceCategory.LAND,
    "land_type_description": EvidenceCategory.LAND,
    "commercial_flag": EvidenceCategory.BUILDING,
    "effective_year_built": EvidenceCategory.BUILDING,
    "year_built": EvidenceCategory.BUILDING,
    "bedrooms": EvidenceCategory.BUILDING,
    "bathrooms": EvidenceCategory.BUILDING,
    "stories": EvidenceCategory.BUILDING,
    "units": EvidenceCategory.BUILDING,
    "pool": EvidenceCategory.BUILDING,
    "property_status": EvidenceCategory.TAX,
    "current_value_year": EvidenceCategory.TAX,
    "current_improvement_homesite_value": EvidenceCategory.BUILDING,
    "current_improvement_non_homesite_value": EvidenceCategory.BUILDING,
    "current_land_homesite_value": EvidenceCategory.LAND,
    "current_land_non_homesite_value": EvidenceCategory.LAND,
    "current_ag_use_value": EvidenceCategory.LAND,
    "current_ag_market_value": EvidenceCategory.LAND,
    "current_market_value": EvidenceCategory.MARKET,
    "current_ag_loss_value": EvidenceCategory.LAND,
    "current_appraised_value": EvidenceCategory.MARKET,
    "current_ten_percent_cap": EvidenceCategory.TAX,
    "current_assessed_value": EvidenceCategory.TAX,
    "certified_value_year": EvidenceCategory.TAX,
    "certified_improvement_homesite_value": EvidenceCategory.BUILDING,
    "certified_improvement_non_homesite_value": EvidenceCategory.BUILDING,
    "certified_land_homesite_value": EvidenceCategory.LAND,
    "certified_land_non_homesite_value": EvidenceCategory.LAND,
    "certified_ag_use_value": EvidenceCategory.LAND,
    "certified_ag_market_value": EvidenceCategory.LAND,
    "certified_market_value": EvidenceCategory.MARKET,
    "certified_ag_loss_value": EvidenceCategory.LAND,
    "certified_appraised_value": EvidenceCategory.MARKET,
    "certified_ten_percent_cap": EvidenceCategory.TAX,
    "certified_assessed_value": EvidenceCategory.TAX,
}

# ECM-TYPE-001 / ECM-OFFICIAL-TEXT-001: field_name -> EvidenceValueType,
# same lookup pattern as FIELD_CATEGORY above, so canonicalization
# knows what KIND of value each field carries. Unmapped fields default
# to TEXT (see the .get(item.field_name, EvidenceValueType.TEXT) call
# below) -- every existing Dallas/Tarrant/Manual field (all genuinely
# text) is completely unaffected by this addition. Only DCAD's real
# numeric, identifier, and official-text fields are mapped to their
# real types here.
#
# legal_description is OFFICIAL_TEXT, not plain TEXT -- real DCAD legal
# text legitimately contains percentages (e.g. "4.98% CE") that plain
# TEXT's leakage guard would reject. See canonical_engine.py's
# OFFICIAL_TEXT_LEAK_PATTERNS for what's still blocked.
FIELD_VALUE_TYPE = {
    "total_appraised_value": EvidenceValueType.CURRENCY,
    "land_value": EvidenceValueType.CURRENCY,
    "improvement_value": EvidenceValueType.CURRENCY,
    "parcel_id": EvidenceValueType.IDENTIFIER,
    "zip_code": EvidenceValueType.IDENTIFIER,
    "legal_description": EvidenceValueType.OFFICIAL_TEXT,
    "source_record_id": EvidenceValueType.IDENTIFIER,
    "owner_mailing_zip_code": EvidenceValueType.IDENTIFIER,
    "legal_acreage": EvidenceValueType.DECIMAL,
    "effective_size_acres": EvidenceValueType.DECIMAL,
    "land_area_sqft": EvidenceValueType.DECIMAL,
    "living_area": EvidenceValueType.DECIMAL,
    "state_code": EvidenceValueType.ENUM,
    "property_use_code": EvidenceValueType.ENUM,
    "property_type_code": EvidenceValueType.ENUM,
    "land_type_code": EvidenceValueType.ENUM,
    "commercial_flag": EvidenceValueType.BOOLEAN,
    "effective_year_built": EvidenceValueType.INTEGER,
    "year_built": EvidenceValueType.INTEGER,
    "bedrooms": EvidenceValueType.DECIMAL,
    "bathrooms": EvidenceValueType.DECIMAL,
    "stories": EvidenceValueType.INTEGER,
    "units": EvidenceValueType.INTEGER,
    "pool": EvidenceValueType.BOOLEAN,
    "property_status": EvidenceValueType.ENUM,
    "current_value_year": EvidenceValueType.INTEGER,
    "current_improvement_homesite_value": EvidenceValueType.CURRENCY,
    "current_improvement_non_homesite_value": EvidenceValueType.CURRENCY,
    "current_land_homesite_value": EvidenceValueType.CURRENCY,
    "current_land_non_homesite_value": EvidenceValueType.CURRENCY,
    "current_ag_use_value": EvidenceValueType.CURRENCY,
    "current_ag_market_value": EvidenceValueType.CURRENCY,
    "current_market_value": EvidenceValueType.CURRENCY,
    "current_ag_loss_value": EvidenceValueType.CURRENCY,
    "current_appraised_value": EvidenceValueType.CURRENCY,
    "current_ten_percent_cap": EvidenceValueType.CURRENCY,
    "current_assessed_value": EvidenceValueType.CURRENCY,
    "certified_value_year": EvidenceValueType.INTEGER,
    "certified_improvement_homesite_value": EvidenceValueType.CURRENCY,
    "certified_improvement_non_homesite_value": EvidenceValueType.CURRENCY,
    "certified_land_homesite_value": EvidenceValueType.CURRENCY,
    "certified_land_non_homesite_value": EvidenceValueType.CURRENCY,
    "certified_ag_use_value": EvidenceValueType.CURRENCY,
    "certified_ag_market_value": EvidenceValueType.CURRENCY,
    "certified_market_value": EvidenceValueType.CURRENCY,
    "certified_ag_loss_value": EvidenceValueType.CURRENCY,
    "certified_appraised_value": EvidenceValueType.CURRENCY,
    "certified_ten_percent_cap": EvidenceValueType.CURRENCY,
    "certified_assessed_value": EvidenceValueType.CURRENCY,
}

REQUIRED_IDENTITY_FIELDS = {"property_address", "city", "county", "state"}


def _normalize_text(value: str) -> str:
    return " ".join(str(value).split())


@dataclass
class StageResult:
    """One pipeline stage's outcome, kept individually inspectable
    rather than folded into a single opaque success/fail flag -- so a
    caller (or verify_spine002.py) can see exactly which stage failed."""
    name: str
    status: str
    ok: bool
    detail: object = None


@dataclass
class PipelineResult:
    property_id: str
    stages: list = field(default_factory=list)
    provider_package: object = None
    canonical_records: list = field(default_factory=list)
    provenance_records: list = field(default_factory=list)
    fusion_package: object = None
    conflict_reports: list = field(default_factory=list)
    property_record: object = None
    decision_record: object = None
    policy_result: object = None
    export_package: object = None
    dashboard_view: object = None
    ok: bool = False

    def stage(self, name):
        return next((s for s in self.stages if s.name == name), None)


class Pipeline:
    def __init__(self, container):
        self.c = container
        # Concurrency fix (post-checkpoint-review): the TXN-001
        # snapshot/restore mechanism (_snapshot_engine_state /
        # _restore_engine_state) reads each engine's dict, and on
        # rollback replaces it wholesale with the pre-run snapshot.
        # That is not safe if two run_property() calls interleave --
        # one run's rollback could silently discard another run's
        # concurrently-successful writes, made in the window between
        # the first run's snapshot and its restore. A single lock
        # around the whole transactional body serializes pipeline runs,
        # trading concurrency for correctness here. This does not
        # weaken anything CONCUR-001 already proved -- that suite
        # verified real SQLite-level concurrency (multiple threads
        # against SqliteStore directly), which is unrelated to and
        # unaffected by this in-process, per-Pipeline-instance lock.
        self._run_lock = threading.Lock()

    # ---- one-time setup, run before any property flows through ----

    def bootstrap_jurisdiction(self, state, county, providers):
        from era.jurisdiction.jurisdiction_models import JurisdictionRecord
        record = JurisdictionRecord(state=state, county=county, providers=providers)
        return self.c.jre.register_jurisdiction(record)

    def bootstrap_connector(self, connector_record):
        return self.c.srr.register_connector(connector_record)

    # ---- main flow ----

    def run_property(self, property_id: str, identity: PropertyIdentity,
                      state: str, county: str, provider_id: str,
                      export_format: ExportFormat = ExportFormat.JSON):
        """
        TXN-001: if the container has a persistence_store, every
        persisted write this run makes (SRR, UPR, EPM, ECR, DEC, POL,
        EXP) happens inside one SQLite transaction, opened here and
        committed only if the entire pipeline reaches result.ok = True.
        Any stage failure, or any unexpected exception, rolls the whole
        transaction back -- so a run that fails at DEC, POL, or EXP
        leaves zero durable trace of the writes that already happened
        earlier in that same run (SRR/UPR/EPM/ECR), not a partial record.

        Audit events are deliberately outside this transaction (see
        era.shared.persistence.Transaction's docstring) -- they record
        what was attempted, including rolled-back attempts, immediately
        and independently.

        With no persistence_store (in-memory mode), conn is always None
        and every call below behaves exactly as it did before TXN-001 --
        this adds zero transactional overhead when nothing is persisted.
        """
        result = PipelineResult(property_id=property_id)
        store = self.c.persistence_store
        with self._run_lock:
            txn = store.transaction() if store else None
            conn = txn.conn if txn else None
            # TXN-001: snapshot the in-memory state of every engine this
            # run can mutate, but only when a transaction is actually
            # open. A SQLite rollback undoes the durable writes; without
            # this, each engine's own in-memory dict (self.records,
            # self.connectors, etc.) would still reflect the
            # rolled-back attempt for the rest of this process's
            # lifetime -- correct on disk, stale in memory. Restoring
            # the snapshot on failure keeps memory and disk in
            # agreement, the same guarantee C4's single-engine rollback
            # already gave one engine at a time, now extended across
            # the whole pipeline run as one unit. self._run_lock (see
            # __init__) is what makes this snapshot/restore safe under
            # concurrent callers -- see that comment for why.
            snapshot = self._snapshot_engine_state() if txn else None
            try:
                self._run_property_body(
                    result, identity, state, county, provider_id, export_format, conn
                )
            except Exception:
                if txn:
                    txn.rollback()
                    self._restore_engine_state(snapshot)
                raise
            if txn:
                if result.ok:
                    txn.commit()
                else:
                    txn.rollback()
                    self._restore_engine_state(snapshot)
        return result

    def _snapshot_engine_state(self):
        return {
            "srr": dict(self.c.srr.connectors),
            "upr": dict(self.c.upr.records),
            "epm": dict(self.c.epm.records),
            "ecr": dict(self.c.ecr.reports),
            "dec": dict(self.c.dec.records),
            "pol": dict(self.c.pol.results),
            "exp": dict(self.c.exp.records),
        }

    def _restore_engine_state(self, snapshot):
        self.c.srr.connectors = snapshot["srr"]
        self.c.upr.records = snapshot["upr"]
        self.c.epm.records = snapshot["epm"]
        self.c.ecr.reports = snapshot["ecr"]
        self.c.dec.records = snapshot["dec"]
        self.c.pol.results = snapshot["pol"]
        self.c.exp.records = snapshot["exp"]

    def _run_property_body(self, result, identity: PropertyIdentity,
                            state: str, county: str, provider_id: str,
                            export_format: ExportFormat, conn):
        property_id = result.property_id
        enumeration = self.c.provider_enumeration_authority.enumerate(
            ProviderEnumerationRequest(
                state=state,
                county=county,
                requested_provider_ids=(provider_id,),
            )
        )
        eligibility = enumeration.get(provider_id)
        exclusion = enumeration.exclusion_for(provider_id)

        def record_stage(name, status, ok, detail=None):
            result.stages.append(StageResult(name, status, ok, detail))
            return ok

        # 1. JRE -- resolve operational providers for this jurisdiction
        geographic_ok = provider_id in enumeration.detail.geographic_mappings
        if not record_stage(
            "JRE",
            jurisdiction_errors.PASS if geographic_ok else jurisdiction_errors.JURISDICTION_NOT_FOUND,
            geographic_ok,
            enumeration.detail.geographic_mappings,
        ):
            return
        if not geographic_ok:
            record_stage("JRE_PROVIDER_NOT_OPERATIONAL", "PROVIDER_NOT_OPERATIONAL", False)
            return

        # 2. SRR -- the connector must actually be registered and active
        connector = self.c.srr.get_connector(provider_id)
        srr_ok = provider_id in enumeration.detail.after_capability
        if not record_stage("SRR", "ACTIVE" if srr_ok else "CONNECTOR_NOT_ACTIVE", srr_ok, connector):
            return

        # 3. RATE-RETRY-001 -- enforce the connector's declared request
        # limits before spending a request at all.
        allowed, rate_reason = self.c.rate_limiter.check_and_record(
            provider_id, connector.resource_policy
        )
        if not record_stage("RATE_LIMIT", rate_reason, allowed):
            return

        # 4. LPA -- retrieve evidence through the standard adapter, with
        # retry enforcement around the call. On the happy path (attempt
        # succeeds first try, as every existing Dallas/Tarrant test
        # does) this changes nothing observable: RetryExecutor only
        # publishes an audit event and sleeps when there actually was a
        # transient failure to retry past.
        lpa = self.c.build_lpa(
            provider_id,
            address=identity.address,
            eligibility=eligibility,
            exclusion=exclusion,
        )
        lpa_status, package = self.c.retry_executor.run(
            provider_id, connector.retry_policy, lambda: lpa.run(property_id)
        )
        if not record_stage("LPA", lpa_status, lpa_status == provider_errors.PASS, package):
            self.c.srr.record_failure(provider_id, conn=conn)
            return
        self.c.srr.record_success(provider_id, response_time_ms=0, conn=conn)
        result.provider_package = package

        # 5. ECM -- canonicalize every field the provider returned
        canonical_records = []
        for item in package.evidence:
            provenance = Provenance(
                connector_id=package.provider_id,
                provider_name=package.provider_name,
                source_name=package.source_reference,
                source_class=EvidenceSourceClass.PUBLIC_RECORD,
                retrieved_at=package.retrieved_at,
                legal_basis=package.legal_basis,
                normalization_version="ECM-001.0",
                audit_reference=f"{package.provider_id}:{property_id}",
            )
            record = CanonicalEvidenceRecord(
                evidence_id=f"EV-{property_id}-{item.field_name}",
                property_id=property_id,
                category=FIELD_CATEGORY.get(item.field_name, EvidenceCategory.IDENTITY),
                field_name=item.field_name,
                raw_value=item.raw_value,
                normalized_value=_normalize_text(item.raw_value),
                units=None,
                provenance=provenance,
                value_type=FIELD_VALUE_TYPE.get(item.field_name, EvidenceValueType.TEXT),
            )
            ecm_status, normalized = self.c.ecm.normalize_record(record)
            if ecm_status != canonical_errors.PASS:
                record_stage(f"ECM:{item.field_name}", ecm_status, False)
                continue
            canonical_records.append(normalized)
        if not record_stage("ECM", "PASS" if canonical_records else "NO_FIELDS_NORMALIZED",
                             bool(canonical_records)):
            return
        result.canonical_records = canonical_records

        # 6. EPM -- register provenance-chained evidence
        provenance_records = []
        for canonical in canonical_records:
            epm_input = ProvenanceInput(
                evidence_id=canonical.evidence_id,
                property_id=canonical.property_id,
                canonical_field=canonical.field_name,
                canonical_value=canonical.normalized_value,
                original_value=canonical.raw_value,
                provider_id=canonical.provenance.connector_id,
                provider_name=canonical.provenance.provider_name,
                legal_basis=canonical.provenance.legal_basis,
                source_reference=canonical.provenance.source_name,
                retrieved_at=canonical.provenance.retrieved_at,
                connector_version=package.connector_version,
                adapter_version=package.adapter_version,
                normalization_version=canonical.provenance.normalization_version,
            )
            epm_status, epm_record = self.c.epm.register_evidence(epm_input, conn=conn)
            if epm_status != provenance_errors.PASS:
                record_stage(f"EPM:{canonical.field_name}", epm_status, False)
                continue
            provenance_records.append(epm_record)
        if not record_stage("EPM", "PASS" if provenance_records else "NO_EVIDENCE_REGISTERED",
                             bool(provenance_records)):
            return
        result.provenance_records = provenance_records

        # 7. MSF -- fuse fields across sources
        fusion_evidence = [
            FusionEvidence(
                evidence_id=pr.evidence_id, property_id=pr.property_id,
                field_name=pr.canonical_field, normalized_value=pr.canonical_value,
                provider_id=pr.provider_id, source_reference=pr.source_reference,
            )
            for pr in provenance_records
        ]
        msf_status, fusion_package = self.c.msf.fuse(fusion_evidence)
        if not record_stage("MSF", msf_status, msf_status == fusion_errors.PASS, fusion_package):
            return
        result.fusion_package = fusion_package

        # 8. ECR -- conflict detection over the same evidence shape MSF used
        ecr_status, conflict_reports = self.c.ecr.resolve(fusion_evidence, conn=conn)
        has_conflicts = ecr_status == conflict_errors.PASS
        record_stage("ECR", ecr_status, True, conflict_reports)  # NO_CONFLICT is a valid outcome
        result.conflict_reports = conflict_reports

        # 9. UPR -- unified property record
        upr_status, upr_record = self.c.upr.create_property(identity, conn=conn)
        if upr_status not in (property_errors.PASS,):
            if upr_status != property_errors.DUPLICATE_PROPERTY:
                record_stage("UPR_CREATE", upr_status, False)
                return
            upr_record = self.c.upr.records[identity.property_id]
        record_stage("UPR_CREATE", "PASS", True)
        for canonical, pr in zip(canonical_records, provenance_records):
            entry = EvidenceEntry(
                evidence_id=pr.evidence_id, property_id=pr.property_id,
                category=canonical.category.value, value=pr.canonical_value,
                connector=pr.provider_id, original_source=pr.source_reference,
                retrieved_at=pr.retrieved_at, normalization_version=pr.normalization_version,
                audit_reference=pr.evidence_hash,
            )
            self.c.upr.add_evidence(identity.property_id, entry, conn=conn)
        record_stage("UPR_EVIDENCE", "PASS", True, upr_record)
        result.property_record = upr_record

        # 10. DEC -- decision
        single_source_only = all(f.source_count == 1 for f in fusion_package.fields)
        required_fields_present = REQUIRED_IDENTITY_FIELDS.issubset(
            {r.field_name for r in canonical_records}
        )
        decision_input = DecisionInput(
            property_id=property_id,
            evidence_count=len(provenance_records),
            required_fields_present=required_fields_present,
            has_conflicts=has_conflicts,
            has_policy_violation=False,
            manual_review_flag=False,
            single_source_only=single_source_only,
            export_ready=required_fields_present and not has_conflicts and not single_source_only,
            supporting_evidence_ids=[pr.evidence_id for pr in provenance_records],
        )
        dec_status, decision_record = self.c.dec.decide(decision_input, conn=conn)
        if not record_stage("DEC", dec_status, dec_status == decision_errors.PASS, decision_record):
            return
        result.decision_record = decision_record

        # 11. POL -- policy
        policy_input = PolicyDecisionInput(
            property_id=property_id,
            decision=decision_record.decision.value,
            has_conflicts=has_conflicts,
            export_requested=True,
            policy_violation=False,
            supporting_evidence_ids=decision_record.supporting_evidence_ids,
        )
        pol_status, policy_result = self.c.pol.evaluate(self.c.default_policy, policy_input, conn=conn)
        if not record_stage("POL", pol_status, pol_status == policy_errors.PASS, policy_result):
            return
        result.policy_result = policy_result

        # 12. EXP -- export
        export_request = ExportRequest(
            property_id=property_id,
            decision=decision_record.decision.value,
            policy_verdict=policy_result.verdict.value,
            provenance_complete=len(provenance_records) == len(canonical_records),
            export_format=export_format,
            payload={
                "decision_id": decision_record.decision_id,
                "policy_id": policy_result.policy_id,
                "evidence_count": len(provenance_records),
            },
        )
        exp_status, export_package = self.c.exp.export(export_request, conn=conn)
        if not record_stage("EXP", exp_status, exp_status == export_errors.PASS, export_package):
            result.export_package = export_package
            return
        result.export_package = export_package

        # 13. Populate the shared result store API/DASH read from --
        # this is the step that proves API/DASH are not islands: they
        # read exactly what the pipeline wrote, through one shared object.
        # Deliberately NOT part of the SQLite transaction -- api_store is
        # an in-memory dict, not persisted state, and is only populated
        # once every durable stage above has already succeeded.
        aggregated_audit = []
        for namespace, engine in self.c.all_engines().items():
            for event in engine.audit.events:
                aggregated_audit.append({"namespace": namespace, **event})

        self.c.api_store["properties"][property_id] = asdict(identity)
        self.c.api_store["evidence"][property_id] = [asdict(pr) for pr in provenance_records]
        self.c.api_store["decisions"][property_id] = {
            "decision_id": decision_record.decision_id,
            "decision": decision_record.decision.value,
            "reason": decision_record.reason.value,
        }
        self.c.api_store["policies"][property_id] = {
            "policy_id": policy_result.policy_id,
            "verdict": policy_result.verdict.value,
            "reason": policy_result.reason.value,
        }
        if export_package is not None:
            self.c.api_store["exports"][property_id] = {
                "export_id": export_package.export_id,
                "status": export_package.status.value,
            }
        self.c.api_store["audits"][property_id] = aggregated_audit

        # 14. DASH -- build the dashboard from the same store API reads
        dashboard_data = {
            "property": self.c.api_store["properties"][property_id],
            "evidence": {"count": len(self.c.api_store["evidence"][property_id])},
            "conflicts": {"count": len(conflict_reports)},
            "decision": self.c.api_store["decisions"][property_id],
            "policy": self.c.api_store["policies"][property_id],
            "export": self.c.api_store["exports"].get(property_id, {}),
            "audit": {"event_count": len(aggregated_audit)},
            "health": {"status": "OPERATIONAL"},
        }
        dash_status, dashboard_view = self.c.dash.build_dashboard(property_id, dashboard_data)
        record_stage("DASH", dash_status, dash_status == "PASS", dashboard_view)
        result.dashboard_view = dashboard_view

        result.ok = True
