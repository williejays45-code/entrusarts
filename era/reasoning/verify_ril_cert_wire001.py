"""RIL-CERT-WIRE-001 certification-admission and boundary verification."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from pathlib import Path

from era.canonical.canonical_enums import EvidenceValueType
from era.reasoning.certification import (
    PolicyCertificationProjection,
    RuleCertificationProjection,
    policy_constraint_fingerprint,
    rule_fingerprint,
)
from era.reasoning.certified_profiles import (
    PROPERTY_INTERPRETATION_POLICY,
    PROPERTY_PARCEL_IDENTIFIER_PRESENT,
    PROPERTY_POLICY_CERTIFICATION,
    PROPERTY_RULE_CERTIFICATION,
)
from era.reasoning.composition import (
    COMPLETE, FAILED, EvidenceInterpretationCompositionService,
)
from era.reasoning.contracts import ALLOWED, InterpretationContext, PolicyConstraint
from era.reasoning.field_predicate import EXISTS, FieldPredicateRule
from era.reasoning.verify_ril_wire001 import (
    CountingInterpreter, certified_service, context, integrate,
)


def invoke(
    service, *, rules=(PROPERTY_PARCEL_IDENTIFIER_PRESENT,),
    constraints=PROPERTY_INTERPRETATION_POLICY, request_context=None,
    rule_certification=PROPERTY_RULE_CERTIFICATION,
    policy_certification=PROPERTY_POLICY_CERTIFICATION,
    operation_id="CERT-OP-1", observed_at="2026-07-13T12:00:00+00:00",
):
    return service.compose(
        integrate(), rules, constraints, request_context or context(),
        operation_id=operation_id, observed_at=observed_at,
        max_rules=8, max_evidence=32,
        rule_certification=rule_certification,
        policy_certification=policy_certification,
    )


def run_checks():
    counter = CountingInterpreter()
    valid = invoke(certified_service(counter))

    unknown_rule = FieldPredicateRule(
        "UNREVIEWED_RUNTIME_RULE", "999", "TX-DALLAS",
        date(2026, 1, 1), None, "parcel_id", EvidenceValueType.TEXT,
        EXISTS, None,
    )
    same_identity_changed_semantics = FieldPredicateRule(
        PROPERTY_PARCEL_IDENTIFIER_PRESENT.rule_id,
        PROPERTY_PARCEL_IDENTIFIER_PRESENT.rule_version,
        PROPERTY_PARCEL_IDENTIFIER_PRESENT.jurisdiction,
        PROPERTY_PARCEL_IDENTIFIER_PRESENT.effective_from,
        PROPERTY_PARCEL_IDENTIFIER_PRESENT.effective_to,
        "situs_address", EvidenceValueType.TEXT, EXISTS, None,
    )
    forged_rule_certification = RuleCertificationProjection.issue(
        "FORGED-RULE-CERT", "1", "CALLER",
        (unknown_rule,),
    )
    unreviewed_constraint = PolicyConstraint(
        "UNREVIEWED_POLICY", "999", "UNREVIEWED_CONSTRAINT",
        ALLOWED, "UNREVIEWED_REASON",
    )
    unreviewed_context = InterpretationContext(
        jurisdiction="TX-DALLAS", as_of="2026-07-13",
        rule_set_id="PROPERTY-COMPLETENESS", rule_set_version="1",
        policy_id="UNREVIEWED_POLICY", policy_version="999",
        configuration_digest="d" * 64,
    )
    forged_policy_certification = PolicyCertificationProjection.issue(
        "FORGED-POLICY-CERT", "1", "CALLER",
        "UNREVIEWED_POLICY", "999", (unreviewed_constraint,),
    )
    changed_constraint = PolicyConstraint(
        "RIL-POLICY", "1", "INTERPRET_PUBLIC_RECORD",
        ALLOWED, "CHANGED_REASON",
    )

    missing_rule = invoke(certified_service(), rule_certification=None)
    untrusted_rule = invoke(
        certified_service(), rules=(unknown_rule,),
        rule_certification=forged_rule_certification,
    )
    mismatched_rule = invoke(
        certified_service(), rules=(unknown_rule,),
        rule_certification=PROPERTY_RULE_CERTIFICATION,
    )
    semantic_rule_change = invoke(
        certified_service(), rules=(same_identity_changed_semantics,),
        rule_certification=PROPERTY_RULE_CERTIFICATION,
    )
    missing_policy = invoke(certified_service(), policy_certification=None)
    untrusted_policy = invoke(
        certified_service(), constraints=(unreviewed_constraint,),
        request_context=unreviewed_context,
        policy_certification=forged_policy_certification,
    )
    mismatched_policy = invoke(
        certified_service(), constraints=(changed_constraint,),
        policy_certification=PROPERTY_POLICY_CERTIFICATION,
    )
    no_trust_anchor = invoke(EvidenceInterpretationCompositionService())

    try:
        PROPERTY_RULE_CERTIFICATION.certification_id = "CHANGED"
        rule_frozen = False
    except FrozenInstanceError:
        rule_frozen = True
    try:
        replace(PROPERTY_RULE_CERTIFICATION, authority_reference="CHANGED")
        tamper_rejected = False
    except ValueError:
        tamper_rejected = True

    replay = invoke(
        certified_service(), operation_id="CERT-OP-REPLAY",
        observed_at="2099-01-01T00:00:00+00:00",
    )

    checks = {
        "certified_operation_completes": valid.status == COMPLETE,
        "certification_retained_in_result": valid.rule_certification is PROPERTY_RULE_CERTIFICATION and valid.policy_certification is PROPERTY_POLICY_CERTIFICATION,
        "valid_operation_invokes_ril_once": counter.calls == 1,
        "missing_rule_certification_fails_before_ril": missing_rule.status == FAILED and missing_rule.reason_code == "RULE_CERTIFICATION_REQUIRED" and missing_rule.interpretation_result is None,
        "caller_cannot_self_certify_rule": untrusted_rule.status == FAILED and untrusted_rule.reason_code == "RULE_CERTIFICATION_UNTRUSTED",
        "trusted_rule_projection_requires_exact_rules": mismatched_rule.status == FAILED and mismatched_rule.reason_code == "RULE_CERTIFICATION_MISMATCH",
        "full_rule_semantics_fingerprinted": semantic_rule_change.status == FAILED and semantic_rule_change.reason_code == "RULE_CERTIFICATION_MISMATCH" and rule_fingerprint(same_identity_changed_semantics) != rule_fingerprint(PROPERTY_PARCEL_IDENTIFIER_PRESENT),
        "missing_policy_certification_fails_before_ril": missing_policy.status == FAILED and missing_policy.reason_code == "POLICY_CERTIFICATION_REQUIRED" and missing_policy.interpretation_result is None,
        "caller_cannot_self_certify_policy": untrusted_policy.status == FAILED and untrusted_policy.reason_code == "POLICY_CERTIFICATION_UNTRUSTED",
        "trusted_policy_projection_requires_exact_constraints": mismatched_policy.status == FAILED and mismatched_policy.reason_code == "POLICY_CERTIFICATION_MISMATCH",
        "full_policy_semantics_fingerprinted": policy_constraint_fingerprint(changed_constraint) != policy_constraint_fingerprint(PROPERTY_INTERPRETATION_POLICY[0]),
        "unanchored_service_fails_closed": no_trust_anchor.status == FAILED and no_trust_anchor.reason_code == "RULE_CERTIFICATION_UNTRUSTED",
        "rule_projection_immutable": rule_frozen,
        "projection_tampering_rejected": tamper_rejected,
        "rule_projection_digest_is_sha256": len(PROPERTY_RULE_CERTIFICATION.projection_digest) == 64,
        "policy_projection_digest_is_sha256": len(PROPERTY_POLICY_CERTIFICATION.projection_digest) == 64,
        "semantic_replay_preserved": replay.interpretation_result.units[0].unit_id == valid.interpretation_result.units[0].unit_id,
        "upstream_eia_retained": valid.integration_result.status == "COMPLETE" and bool(valid.integration_result.outcomes),
    }

    base = Path(__file__).parents[1]
    source = (base / "reasoning" / "certification.py").read_text(encoding="utf-8").lower()
    composition = (base / "reasoning" / "composition.py").read_text(encoding="utf-8").lower()
    container = (base / "container.py").read_text(encoding="utf-8").lower()
    pipeline = (base / "pipeline.py").read_text(encoding="utf-8").lower()
    checks.update({
        "container_anchors_rule_certification": "property_rule_certification" in container and "trusted_rule_certifications=" in container,
        "container_anchors_policy_certification": "property_policy_certification" in container and "trusted_policy_certifications=" in container,
        "no_registry_or_discovery": all(term not in source + composition for term in ("registry", "discover", "default_rule", "default_policy")),
        "no_persistence": all(term not in source + composition for term in ("sqlite", ".save(", "persist(")),
        "no_confidence_or_recommendation": all(term not in source + composition for term in ("confidence", "recommend")),
        "no_legacy_reasoning": "reasoning_engine" not in source + composition,
        "no_new_reasoning_language": "fieldpredicateinterpreter" not in source,
        "pipeline_unchanged_by_certification": "certification" not in pipeline and "evidence_interpretation" not in pipeline,
    })
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"RIL-CERT-WIRE-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
