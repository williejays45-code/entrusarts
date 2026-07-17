"""
ERA Verification Taxonomy.

Classifies every verify_*.py module by level, engine, purpose, and
production/legacy status -- as a central registry, not as metadata
embedded in each of the 53 individual verify scripts. Deliberate
choice: editing 53 working, currently-passing files to inject headers
carries real risk (a single misplaced edit breaks a script that has
been correct for a long time) for a purely organizational goal. A
single source-of-truth mapping gets the same classification outcome
with zero risk to anything that currently passes -- consistent with
the instruction to build on existing progress without changing working
code.

Levels, per FORGE's ERA Verification Standard:
  UNIT        -- one engine's own logic, in isolation.
  INTEGRATION -- two or more engines/subsystems working together.
  SYSTEM      -- full pipeline / cross-cutting concerns (transactions,
                 concurrency, schema versioning, the master gate itself).
  LEGACY      -- retained for regression coverage of superseded code;
                 a passing result does not validate any current
                 production path.

If a new verify_*.py is added and not yet classified here, verify_all.py
reports it under an explicit "UNCLASSIFIED" group rather than silently
dropping it from the taxonomy view -- new work is visible immediately,
not invisible until someone remembers to classify it.
"""

UNIT = "UNIT"
INTEGRATION = "INTEGRATION"
SYSTEM = "SYSTEM"
LEGACY = "LEGACY"

PRODUCTION = "PRODUCTION"
# LEGACY status mirrors LEGACY level for the two legacy modules; kept as
# a separate field (not derived from level) in case a future SYSTEM- or
# INTEGRATION-level module is ever deliberately retired without being
# deleted, the same way the two DCAD stub verifiers were.

TAXONOMY = {
    # ---- UNIT: acquisition / connectors ----
    "era.acquisition.connectors.verify_registry_wrapper": {
        "level": UNIT, "engine": "ACQUISITION", "status": PRODUCTION,
        "purpose": "Connector registry wrapper behavior in isolation.",
    },
    "era.acquisition.providers.county.verify_county_framework": {
        "level": UNIT, "engine": "ACQUISITION", "status": PRODUCTION,
        "purpose": "DallasCADConnector against CountyConnectorBase, in isolation.",
    },
    "era.acquisition.providers.county.verify_tarrant_connector": {
        "level": UNIT, "engine": "ACQUISITION", "status": PRODUCTION,
        "purpose": "TarrantCountyAssessorConnector, in isolation.",
    },
    "era.acquisition.verify_srr001": {
        "level": UNIT, "engine": "SRR", "status": PRODUCTION,
        "purpose": "SourceReliabilityRegistry core logic, in-memory.",
    },
    "era.acquisition.verify_srr001_persistence": {
        "level": UNIT, "engine": "SRR", "status": PRODUCTION,
        "purpose": "SourceReliabilityRegistry restart survival.",
    },
    "era.acquisition.verify_health_authority001": {
        "level": UNIT, "engine": "PROVIDER_HEALTH_AUTHORITY", "status": PRODUCTION,
        "purpose": "HA-001 stateless provider-health derivation from SRR facts and provider observations.",
    },
    "era.acquisition.verify_health_authority002": {
        "level": UNIT, "engine": "PROVIDER_HEALTH_AUTHORITY", "status": PRODUCTION,
        "purpose": "HA-001 finalized closed-vocabulary derivation, normalization, and explainability.",
    },
    "era.acquisition.verify_provider_enumeration001": {
        "level": INTEGRATION, "engine": "PROVIDER_ENUMERATION_AUTHORITY", "status": PRODUCTION,
        "purpose": "PER-001 SRR-seeded monotonic provider eligibility, fail-closed exclusions, and bypass scan.",
    },
    "era.acquisition.verify_provider_enumeration_bypass001": {
        "level": INTEGRATION, "engine": "PROVIDER_ENUMERATION_AUTHORITY", "status": PRODUCTION,
        "purpose": "PER-001 repository-wide production authority-bypass scan.",
    },
    "era.discovery.verify_sdr001": {
        "level": INTEGRATION, "engine": "SOURCE_DISCOVERY", "status": PRODUCTION,
        "purpose": "SDR-001 deterministic bounded source discovery and boundary enforcement.",
    },
    "era.discovery.verify_sdr002": {
        "level": INTEGRATION, "engine": "SOURCE_RESOLUTION", "status": PRODUCTION,
        "purpose": "SDR-002 canonical source identity, declared-alias resolution, and boundary proof.",
    },
    "era.discovery.verify_sdr003": {
        "level": INTEGRATION, "engine": "ACQUISITION_PLANNING", "status": PRODUCTION,
        "purpose": "SDR-003 deterministic replayable acquisition planning and boundary proof.",
    },
    "era.discovery.verify_sdr004": {
        "level": INTEGRATION, "engine": "ACQUISITION_PACKAGE", "status": PRODUCTION,
        "purpose": "SDR-004 immutable AX package validation, partial-outcome preservation, and handoff boundary.",
    },
    "era.evidence_intelligence.verify_eil_contract001": {
        "level": INTEGRATION, "engine": "EVIDENCE_CONTRACT", "status": PRODUCTION,
        "purpose": "EIL-CONTRACT-001 deterministic package identity and EPM-owned parser-trace survival.",
    },
    "era.evidence_intelligence.verify_eil_contract002": {
        "level": INTEGRATION, "engine": "EVIDENCE_CONTRACT", "status": PRODUCTION,
        "purpose": "EIL-CONTRACT-002 immutable parser profiles and explicit compatibility enforcement.",
    },
    "era.evidence_intelligence.verify_eil001": {
        "level": INTEGRATION, "engine": "EVIDENCE_INTELLIGENCE", "status": PRODUCTION,
        "purpose": "EIL-001 deterministic CSV, JSON, ZIP inspection, and MDB-derived parsing into traceable evidence candidates.",
    },
    "era.evidence_intelligence.verify_eia_wire001": {
        "level": INTEGRATION, "engine": "EVIDENCE_INTEGRATION", "status": PRODUCTION,
        "purpose": "EIA-WIRE-001 validated membership and deterministic trace-preserving EIL-to-ECM-to-EPM production handoff.",
    },
    "era.reasoning.verify_ril_contract001": {
        "level": INTEGRATION, "engine": "REASONING_CONTRACT", "status": PRODUCTION,
        "purpose": "RIL-CONTRACT-001 immutable canonical-evidence interpretation boundary, disposition completeness, and replay identity.",
    },
    "era.reasoning.verify_ril001": {
        "level": INTEGRATION, "engine": "REASONING_INTERPRETATION", "status": PRODUCTION,
        "purpose": "RIL-001 explicit typed field-predicate applicability, complete evidence disposition, conflict preservation, and semantic replay.",
    },
    "era.reasoning.verify_ril_wire001": {
        "level": INTEGRATION, "engine": "EVIDENCE+REASONING", "status": PRODUCTION,
        "purpose": "RIL-WIRE-001 successful EIA canonical/provenance handoff into one explicit certified RIL rule with partial/failure transparency.",
    },
    "era.reasoning.verify_ril_cert_wire001": {
        "level": INTEGRATION, "engine": "REASONING_CERTIFICATION", "status": PRODUCTION,
        "purpose": "RIL-CERT-WIRE-001 immutable trust-anchored rule and policy certification admission before interpretation.",
    },
    "era.acquisition_execution.verify_ax001": {
        "level": INTEGRATION, "engine": "ACQUISITION_EXECUTION", "status": PRODUCTION,
        "purpose": "AX-001 plan fidelity, explicit attempts, raw artifact integrity, and execution boundaries.",
    },
    "era.acquisition_execution.verify_ax_adapt001": {
        "level": INTEGRATION, "engine": "ACQUISITION_EXECUTION", "status": PRODUCTION,
        "purpose": "AX-ADAPT-001 genuine pre-parse byte capture and fail-closed provider seams.",
    },
    "era.artifact_storage.verify_art001": {
        "level": INTEGRATION, "engine": "ARTIFACT_STORAGE", "status": PRODUCTION,
        "purpose": "ART-001 governed write-once admission, exact historical recovery, integrity quarantine, durable audit ordering, and authority-boundary proof.",
    },

    # ---- LEGACY ----
    "era.acquisition.providers.county.verify_legacy_dcad_capture": {
        "level": LEGACY, "engine": "DCAD_LEGACY_STUB", "status": LEGACY,
        "purpose": "Original DCADPublicRecordCapture stub, predates real DCAD data.",
    },
    "era.acquisition.providers.county.verify_legacy_dcad_to_upr": {
        "level": LEGACY, "engine": "DCAD_LEGACY_STUB", "status": LEGACY,
        "purpose": "Original stub through to UPR, predates real DCAD data.",
    },

    # ---- UNIT: API / auth ----
    "era.api.verify_api001": {
        "level": UNIT, "engine": "API", "status": PRODUCTION,
        "purpose": "EraApiEngine endpoints against a synthetic store.",
    },
    "era.auth.verify_auth001": {
        "level": UNIT, "engine": "AUTH", "status": PRODUCTION,
        "purpose": "AuthEngine authenticate/authorize logic.",
    },
    "era.auth.verify_auth_token_wire001": {
        "level": UNIT, "engine": "AUTH", "status": PRODUCTION,
        "purpose": "AUTH-TOKEN-WIRE-001: locked resolution rule, secret-leak checks (raw token never in SQLite/audit), restart survival, cross-DB isolation.",
    },

    # ---- UNIT: canonical / ECM ----
    "era.canonical.verify_ecm001": {
        "level": UNIT, "engine": "ECM", "status": PRODUCTION,
        "purpose": "CanonicalEvidenceModel core validation, pre-typing.",
    },
    "era.canonical.verify_ecm_type001": {
        "level": UNIT, "engine": "ECM", "status": PRODUCTION,
        "purpose": "EvidenceValueType-typed normalization (ECM-TYPE-001).",
    },
    "era.canonical.verify_ecm_official_text001": {
        "level": UNIT, "engine": "ECM", "status": PRODUCTION,
        "purpose": "OFFICIAL_TEXT type, distinct from TEXT's leakage rules.",
    },

    # ---- UNIT: conflict / dashboard / decision / export / fusion /
    # jurisdiction / orchestration / policy / property_record /
    # provenance / provider_network / providers / recommendation /
    # sensitivity / trace ----
    "era.conflict.verify_ecr001": {
        "level": UNIT, "engine": "ECR", "status": PRODUCTION,
        "purpose": "EvidenceConflictResolver core logic.",
    },
    "era.conflict.verify_ecr001_persistence": {
        "level": UNIT, "engine": "ECR", "status": PRODUCTION,
        "purpose": "EvidenceConflictResolver restart survival.",
    },
    "era.dashboard.verify_dash001": {
        "level": UNIT, "engine": "DASHBOARD", "status": PRODUCTION,
        "purpose": "DashboardEngine card assembly.",
    },
    "era.decision.verify_dec001": {
        "level": UNIT, "engine": "DEC", "status": PRODUCTION,
        "purpose": "DecisionEngine rule logic.",
    },
    "era.decision.verify_dec001_persistence": {
        "level": UNIT, "engine": "DEC", "status": PRODUCTION,
        "purpose": "DecisionEngine restart survival.",
    },
    "era.export.verify_exp001": {
        "level": UNIT, "engine": "EXP", "status": PRODUCTION,
        "purpose": "ExportEngine authorization/blocking logic.",
    },
    "era.export.verify_exp001_persistence": {
        "level": UNIT, "engine": "EXP", "status": PRODUCTION,
        "purpose": "ExportEngine restart survival.",
    },
    "era.fusion.verify_msf001": {
        "level": UNIT, "engine": "MSF", "status": PRODUCTION,
        "purpose": "MultiSourceFusionEngine consensus logic.",
    },
    "era.improvement.verify_improvement_analyzer": {
        "level": UNIT, "engine": "IMPROVEMENT", "status": PRODUCTION,
        "purpose": "ImprovementAnalyzer priority-scoring logic.",
    },
    "era.jurisdiction.verify_jre001": {
        "level": UNIT, "engine": "JRE", "status": PRODUCTION,
        "purpose": "JurisdictionRegistry resolution logic.",
    },
    "era.orchestration.verify_eoe001": {
        "level": UNIT, "engine": "ORCHESTRATION", "status": PRODUCTION,
        "purpose": "ERAOrchestrationEngine control flow with injected fakes.",
    },
    "era.policy.verify_pol001": {
        "level": UNIT, "engine": "POL", "status": PRODUCTION,
        "purpose": "PolicyEngine verdict logic.",
    },
    "era.policy.verify_pol001_persistence": {
        "level": UNIT, "engine": "POL", "status": PRODUCTION,
        "purpose": "PolicyEngine restart survival.",
    },
    "era.property_record.verify_upr001": {
        "level": UNIT, "engine": "UPR", "status": PRODUCTION,
        "purpose": "UnifiedPropertyRecordEngine core logic.",
    },
    "era.property_record.verify_upr001_persistence": {
        "level": UNIT, "engine": "UPR", "status": PRODUCTION,
        "purpose": "UnifiedPropertyRecordEngine restart survival.",
    },
    "era.provenance.verify_epm001_persistence": {
        "level": UNIT, "engine": "EPM", "status": PRODUCTION,
        "purpose": "EvidenceProvenanceManager restart survival, incl. chain supersession.",
    },
    "era.provider_network.verify_epp002": {
        "level": UNIT, "engine": "PROVIDER_NETWORK", "status": PRODUCTION,
        "purpose": "ProviderManifest registration logic.",
    },
    "era.providers.verify_lpa001": {
        "level": UNIT, "engine": "LPA", "status": PRODUCTION,
        "purpose": "LiveProviderAdapter gating logic against a fake provider.",
    },
    "era.providers.verify_lpi001": {
        "level": UNIT, "engine": "LPA", "status": PRODUCTION,
        "purpose": "LiveProviderAdapter integration variant, still isolated.",
    },
    "era.recommendation.verify_eri002": {
        "level": UNIT, "engine": "RECOMMENDATION", "status": PRODUCTION,
        "purpose": "RecommendationEngine core gating (C2 trust boundary).",
    },
    "era.recommendation.verify_eri002_full_gate": {
        "level": UNIT, "engine": "RECOMMENDATION", "status": PRODUCTION,
        "purpose": "RecommendationEngine full itemized gate + audit reconciliation.",
    },
    "era.recommendation.verify_eri002_regression": {
        "level": UNIT, "engine": "RECOMMENDATION", "status": PRODUCTION,
        "purpose": "RecommendationEngine regression + audit trail.",
    },
    "era.sensitivity.verify_eri003_audit": {
        "level": UNIT, "engine": "SENSITIVITY", "status": PRODUCTION,
        "purpose": "ContributionAnalyzer audit trail.",
    },
    "era.sensitivity.verify_eri003_phase1": {
        "level": UNIT, "engine": "SENSITIVITY", "status": PRODUCTION,
        "purpose": "ContributionAnalyzer phase-1 scoring logic.",
    },
    "era.sensitivity.verify_eri003_regression": {
        "level": UNIT, "engine": "SENSITIVITY", "status": PRODUCTION,
        "purpose": "ContributionAnalyzer regression coverage.",
    },
    "era.trace.verify_dte001": {
        "level": UNIT, "engine": "TRACE", "status": PRODUCTION,
        "purpose": "DependencyTraceEngine core logic.",
    },

    # ---- INTEGRATION: two or more engines/subsystems together ----
    "era.provenance.verify_ecm_to_epm": {
        "level": INTEGRATION, "engine": "ECM+EPM", "status": PRODUCTION,
        "purpose": "Canonical evidence flowing into provenance registration.",
    },
    "era.live_adapters.verify_dcad_join001": {
        "level": INTEGRATION, "engine": "DCAD_BULK_ADAPTER", "status": PRODUCTION,
        "purpose": "Real two-table DCAD join (ACCOUNT_APPRL_YEAR + ACCOUNT_INFO) through the full pipeline.",
    },
    "era.live_adapters.verify_dcad_map_auth001": {
        "level": INTEGRATION, "engine": "DCAD_BULK_ADAPTER", "status": PRODUCTION,
        "purpose": "DCAD-MAP-AUTH-001 hard review: ADMIN/FOUNDER-only mutation gate on register_account_mapping(), retrieve() unaffected, no caller-supplied identity override.",
    },
    "era.live_adapters.verify_dcad_index001": {
        "level": INTEGRATION, "engine": "DCAD_INDEX_STORE", "status": PRODUCTION,
        "purpose": "Disk-backed streaming index (DCAD-INDEX-001): atomic build, restart survival, fingerprint reuse.",
    },
    "era.acquisition.providers.county.verify_dcad_index_operational": {
        "level": SYSTEM, "engine": "DCAD_INDEX_STORE", "status": PRODUCTION,
        "purpose": "Operational memory benchmark: psutil-sampled RSS in an isolated child process, 3-run matrix.",
    },
    "era.acquisition.providers.county.verify_dcad_live_local_only": {
        "level": SYSTEM, "engine": "DCAD_BULK_ADAPTER", "status": PRODUCTION,
        "purpose": (
            "LIVE-DCAD-VERIFY-001: real network download against the actual DCAD Data "
            "Products URL, real ZIP, real join, real pipeline, restart survival. "
            "LOCAL-MACHINE ONLY -- requires a real --download-url and real network "
            "access this sandboxed environment does not have. Excluded from the "
            "routine master gate; run explicitly on a machine that can reach the "
            "real endpoint. A result here (once run) is the first genuine evidence "
            "about live network behavior anywhere in this project -- everything else "
            "is proven against MockHttpTransport and real captured data, not a live call."
        ),
    },
    "era.live_adapters.verify_live_adapter001a": {
        "level": INTEGRATION, "engine": "MANUAL_ADAPTER", "status": PRODUCTION,
        "purpose": "Manual capture adapter through the full pipeline, incl. OP-AUTH-001.",
    },
    "era.live_adapters.verify_live_adapter001b": {
        "level": INTEGRATION, "engine": "DCAD_BULK_ADAPTER", "status": PRODUCTION,
        "purpose": "DCAD Phase 1 (Account_Apprl_Year only) through the full pipeline.",
    },
    "era.live_adapters.verify_collin_bulk_adapter001": {
        "level": INTEGRATION, "engine": "COLLIN_BULK_ADAPTER", "status": PRODUCTION,
        "purpose": "Collin bulk MDB adapter mapping, readiness prerequisites, and pipeline integration.",
    },
    "era.network.verify_network001b": {
        "level": INTEGRATION, "engine": "NETWORK", "status": PRODUCTION,
        "purpose": "Binary/ZIP transport support + retry integration.",
    },
    "era.verify_network001": {
        "level": INTEGRATION, "engine": "NETWORK", "status": PRODUCTION,
        "purpose": "Transport status mapping + retry integration.",
    },
    "era.verify_audit_persistence": {
        "level": INTEGRATION, "engine": "AUDIT", "status": PRODUCTION,
        "purpose": "Cross-engine audit trail persistence and restart survival.",
    },
    "era.verify_auth_wire001": {
        "level": INTEGRATION, "engine": "AUTH+API", "status": PRODUCTION,
        "purpose": "AuthEngine wired into the API access path.",
    },
    "era.verify_rate_retry001": {
        "level": INTEGRATION, "engine": "RATE_LIMITER+RETRY_EXECUTOR", "status": PRODUCTION,
        "purpose": "Rate limiting + retry enforcement, incl. real pipeline integration check.",
    },
    "era.verify_tarrant_wire001": {
        "level": INTEGRATION, "engine": "TARRANT_ADAPTER", "status": PRODUCTION,
        "purpose": "Tarrant connector through the full pipeline, alongside Dallas.",
    },
    "era.verify_health_wire001": {
        "level": INTEGRATION, "engine": "PROVIDER_HEALTH_AUTHORITY", "status": PRODUCTION,
        "purpose": "HA-WIRE-001 system consumer wiring, fail-closed behavior, audit reasons, and bypass scan.",
    },

    # ---- SYSTEM: full pipeline / cross-cutting concerns ----
    "era.verify_spine002": {
        "level": SYSTEM, "engine": "PIPELINE", "status": PRODUCTION,
        "purpose": "Full 13-stage composition-root pipeline, end to end.",
    },
    "era.verify_txn001": {
        "level": SYSTEM, "engine": "PIPELINE", "status": PRODUCTION,
        "purpose": "Cross-engine transaction boundary and rollback.",
    },
    "era.verify_concur001": {
        "level": SYSTEM, "engine": "PERSISTENCE", "status": PRODUCTION,
        "purpose": "Real SQLite concurrency under the persistence layer.",
    },
    "era.verify_schema001": {
        "level": SYSTEM, "engine": "PERSISTENCE", "status": PRODUCTION,
        "purpose": "Schema versioning and migration across the persistence layer.",
    },
    "era.verify_persistence_error_handling": {
        "level": SYSTEM, "engine": "PERSISTENCE", "status": PRODUCTION,
        "purpose": "Cross-engine persistence failure handling and rollback.",
    },
    "era.verify_all": {
        "level": SYSTEM, "engine": "VERIFICATION_GATE", "status": PRODUCTION,
        "purpose": "The master gate itself -- excluded from its own run.",
    },
}


def classify(module: str) -> dict:
    """Returns the taxonomy entry for a module, or a clearly-marked
    UNCLASSIFIED placeholder if it isn't in TAXONOMY yet -- new verify
    scripts are visible immediately in reports, not silently dropped."""
    return TAXONOMY.get(module, {
        "level": "UNCLASSIFIED", "engine": "UNKNOWN", "status": "UNKNOWN",
        "purpose": "Not yet classified in era/verification_taxonomy.py.",
    })
