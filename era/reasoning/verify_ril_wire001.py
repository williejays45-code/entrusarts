"""RIL-WIRE-001 EIA-to-interpretation composition verification."""

from dataclasses import FrozenInstanceError
from pathlib import Path

from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.evidence_intelligence.integration import (
    COMPLETE as EIA_COMPLETE,
    FAILED as EIA_FAILED,
    FAILED_PARSING,
    PARTIAL as EIA_PARTIAL,
    SUCCEEDED,
    CandidateIntegrationOutcome,
    EvidenceIntegrationResult,
    EvidenceIntegrationService,
)
from era.evidence_intelligence.verify_eia_wire001 import item, policy as eia_policy
from era.provenance.provenance_manager import EvidenceProvenanceManager
from era.reasoning.certified_profiles import (
    PROPERTY_INTERPRETATION_POLICY,
    PROPERTY_PARCEL_IDENTIFIER_PRESENT,
    PROPERTY_POLICY_CERTIFICATION,
    PROPERTY_RULE_CERTIFICATION,
)
from era.reasoning.composition import (
    COMPLETE, FAILED, PARTIAL,
    EvidenceInterpretationCompositionResult,
    EvidenceInterpretationCompositionService,
)
from era.reasoning.contracts import (
    ALLOWED, CONCLUDED, INDETERMINATE, INSUFFICIENT_EVIDENCE,
    InterpretationContext, InterpretationResult, PolicyConstraint,
)
from era.reasoning.field_predicate import FieldPredicateInterpreter, FieldPredicateRule


def integrate():
    return EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (item(),), eia_policy())


def context(jurisdiction="TX-DALLAS"):
    return InterpretationContext(
        jurisdiction=jurisdiction,
        as_of="2026-07-13",
        rule_set_id="PROPERTY-COMPLETENESS",
        rule_set_version="1",
        policy_id="RIL-POLICY",
        policy_version="1",
        configuration_digest="d" * 64,
    )


def policy():
    return PROPERTY_INTERPRETATION_POLICY


def certified_service(interpreter=None):
    return EvidenceInterpretationCompositionService(
        interpreter,
        trusted_rule_certifications=(PROPERTY_RULE_CERTIFICATION,),
        trusted_policy_certifications=(PROPERTY_POLICY_CERTIFICATION,),
    )


class CountingInterpreter:
    def __init__(self):
        self.calls = 0
        self.delegate = FieldPredicateInterpreter()

    def evaluate(self, *args, **kwargs):
        self.calls += 1
        return self.delegate.evaluate(*args, **kwargs)


def compose(service, integration_result, operation_id="OP-1", observed_at="2026-07-13T10:00:00+00:00"):
    return service.compose(
        integration_result,
        (PROPERTY_PARCEL_IDENTIFIER_PRESENT,),
        policy(),
        context(),
        operation_id=operation_id,
        observed_at=observed_at,
        max_rules=4,
        max_evidence=16,
        rule_certification=PROPERTY_RULE_CERTIFICATION,
        policy_certification=PROPERTY_POLICY_CERTIFICATION,
    )


def run_checks():
    full = integrate()
    counter = CountingInterpreter()
    service = certified_service(counter)
    complete = compose(service, full)
    interpretation = complete.interpretation_result
    unit = interpretation.units[0]

    upstream_parcel = next(
        outcome for outcome in full.outcomes if outcome.field_name == "parcel_id"
    )
    request_parcel = next(
        record for record in interpretation.request.evidence if record.field_name == "parcel_id"
    )
    request_parcel_provenance = next(
        record for record in interpretation.request.provenance
        if record.evidence_id == request_parcel.evidence_id
    )

    failed_outcome = CandidateIntegrationOutcome(
        2, "CAND-FAILED", "situs_address", FAILED_PARSING,
        "MISSING_REQUIRED_FIELD", None, None,
    )
    partial_eia = EvidenceIntegrationResult(
        EIA_PARTIAL, full.property_id, full.mapping_policy_id,
        full.mapping_policy_version, full.outcomes + (failed_outcome,),
    )
    partial = compose(service, partial_eia)

    value_only_outcomes = tuple(
        outcome for outcome in full.outcomes
        if outcome.field_name == "total_appraised_value"
    )
    value_only_eia = EvidenceIntegrationResult(
        EIA_COMPLETE, full.property_id, full.mapping_policy_id,
        full.mapping_policy_version, value_only_outcomes,
    )
    missing = compose(service, value_only_eia)
    missing_unit = missing.interpretation_result.units[0]

    failed_eia = EvidenceIntegrationResult(
        EIA_FAILED, full.property_id, full.mapping_policy_id,
        full.mapping_policy_version, (failed_outcome,),
    )
    failed_counter = CountingInterpreter()
    failed = compose(certified_service(failed_counter), failed_eia)

    malformed_success = CandidateIntegrationOutcome(
        1, "CAND-BAD", "parcel_id", SUCCEEDED, "", None, None,
    )
    malformed_eia = EvidenceIntegrationResult(
        EIA_COMPLETE, full.property_id, full.mapping_policy_id,
        full.mapping_policy_version, (malformed_success,),
    )
    malformed = compose(certified_service(), malformed_eia)

    replay_full = integrate()
    replay = compose(
        certified_service(),
        EvidenceIntegrationResult(
            replay_full.status, replay_full.property_id,
            replay_full.mapping_policy_id, replay_full.mapping_policy_version,
            tuple(reversed(replay_full.outcomes)),
        ),
        operation_id="OP-REPLAY",
        observed_at="2099-01-01T00:00:00+00:00",
    )

    try:
        PROPERTY_PARCEL_IDENTIFIER_PRESENT.rule_id = "CHANGED"
        frozen = False
    except FrozenInstanceError:
        frozen = True

    checks = {
        "eia_completed_before_composition": full.status == EIA_COMPLETE,
        "composition_result_immutable_model": isinstance(complete, EvidenceInterpretationCompositionResult),
        "existing_interpretation_result_reused": isinstance(interpretation, InterpretationResult),
        "complete_status": complete.status == COMPLETE,
        "one_certified_rule_one_unit": len(interpretation.units) == 1,
        "certified_profile_is_field_predicate": isinstance(PROPERTY_PARCEL_IDENTIFIER_PRESENT, FieldPredicateRule),
        "certified_profile_atomic_parcel_rule": PROPERTY_PARCEL_IDENTIFIER_PRESENT.rule_id == "PROPERTY_PARCEL_IDENTIFIER_PRESENT" and PROPERTY_PARCEL_IDENTIFIER_PRESENT.required_canonical_field == "parcel_id",
        "certified_rule_concluded": unit.status == CONCLUDED and unit.object_value == "true",
        "eia_invokes_ril_once": counter.calls == 3,
        "canonical_record_same_object": request_parcel is upstream_parcel.canonical_record,
        "provenance_record_same_object": request_parcel_provenance is upstream_parcel.provenance_record,
        "evidence_id_survives": request_parcel.evidence_id == upstream_parcel.canonical_record.evidence_id,
        "provenance_link_survives": request_parcel_provenance.evidence_id == request_parcel.evidence_id,
        "parser_trace_survives": request_parcel_provenance.artifact_sha256 == upstream_parcel.provenance_record.artifact_sha256 and bool(request_parcel_provenance.parser_id),
        "partial_eia_visible": partial.status == PARTIAL and partial.integration_result is partial_eia,
        "failed_outcome_preserved_exactly": partial.integration_result.outcomes[-1] is failed_outcome,
        "partial_still_interprets_successes": partial.interpretation_result.units[0].status == CONCLUDED,
        "missing_parcel_indeterminate": missing.status == PARTIAL and missing_unit.status == INDETERMINATE,
        "missing_parcel_is_insufficient": missing_unit.applicability.status == INSUFFICIENT_EVIDENCE and missing_unit.applicability.missing_fields == ("parcel_id",),
        "missing_is_never_opposition": all(item.disposition != "OPPOSES" for item in missing_unit.evidence_dispositions),
        "failed_eia_visible_without_ril_call": failed.status == FAILED and failed.reason_code == "NO_SUCCESSFUL_EVIDENCE" and failed_counter.calls == 0,
        "failed_eia_outcome_preserved": failed.integration_result is failed_eia and failed.integration_result.outcomes[0] is failed_outcome,
        "malformed_success_fails_closed": malformed.status == FAILED and malformed.reason_code == "INCOMPLETE_SUCCESSFUL_EIA_OUTCOME" and malformed.interpretation_result is None,
        "semantic_replay_identity": replay.interpretation_result.units[0].unit_id == unit.unit_id,
        "semantic_replay_outcome": replay.interpretation_result.units[0].status == unit.status and replay.interpretation_result.units[0].object_value == unit.object_value,
        "certified_profile_immutable": frozen,
    }

    composition_source = (Path(__file__).parent / "composition.py").read_text(encoding="utf-8").lower()
    profile_source = (Path(__file__).parent / "certified_profiles.py").read_text(encoding="utf-8").lower()
    container_source = (Path(__file__).parents[1] / "container.py").read_text(encoding="utf-8").lower()
    checks.update({
        "container_exposes_composition_seam": "self.evidence_interpretation = evidenceinterpretationcompositionservice(" in container_source,
        "no_legacy_reasoning": "reasoning_engine" not in composition_source and "reasoning_engine" not in profile_source,
        "no_reparse": "deterministicartifactparser" not in composition_source and ".parse(" not in composition_source,
        "no_recanonicalization": "normalize_record(" not in composition_source,
        "no_provenance_registration": "register_evidence(" not in composition_source,
        "no_persistence": all(term not in composition_source for term in ("sqlite", ".save(", "persist(")),
        "no_confidence_or_recommendation": all(term not in composition_source for term in ("confidence", "recommend")),
        "no_rule_discovery_or_default_profile": "certified_profiles" not in composition_source and "default_rule" not in composition_source,
        "profile_module_not_registry": all(
            term not in profile_source
            for term in ("class ruleregistry", "class policyregistry", "registry =", "registry[")
        ),
        "pipeline_not_modified_by_seam": "self.evidence_interpretation" not in (Path(__file__).parents[1] / "pipeline.py").read_text(encoding="utf-8").lower(),
    })
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"RIL-WIRE-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
