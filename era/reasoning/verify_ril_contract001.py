"""RIL-CONTRACT-001 immutability, traceability, and boundary verification."""

from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.provenance.provenance_enums import EvidenceStatus
from era.provenance.provenance_models import ProvenanceRecord
from era.reasoning.contracts import (
    APPLICABLE,
    CONCLUDED,
    INDETERMINATE,
    INSUFFICIENT_EVIDENCE,
    IRRELEVANT,
    OPPOSES,
    SUPPORTS,
    ApprovedContextValue,
    EvidenceDisposition,
    InterpretationContext,
    InterpretationRequest,
    InterpretationResult,
    InterpretationUnit,
    PolicyConstraint,
    RuleApplicability,
)


def canonical(evidence_id, field_name, value):
    return CanonicalEvidenceRecord(
        evidence_id=evidence_id,
        property_id="PROP-1",
        category=EvidenceCategory.BUILDING,
        field_name=field_name,
        raw_value=value,
        normalized_value=value,
        units=None,
        provenance=Provenance(
            "DCAD", "Dallas CAD", "DCAD", EvidenceSourceClass.PUBLIC_RECORD,
            "2026-07-13T00:00:00+00:00", "PUBLIC_RECORD", "ECM-1", evidence_id,
        ),
        created_at="2026-07-13T00:00:00+00:00",
    )


def provenance(evidence_id, field_name, value):
    return ProvenanceRecord(
        evidence_id=evidence_id, property_id="PROP-1", canonical_field=field_name,
        canonical_value=value, original_value=value, provider_id="DCAD",
        provider_name="Dallas CAD", legal_basis="PUBLIC_RECORD",
        source_reference="DCAD", retrieved_at="2026-07-13T00:00:00+00:00",
        connector_version="1", adapter_version="1", normalization_version="ECM-1",
        evidence_hash="a" * 64, previous_evidence_id=None, superseded_by=None,
        chain_position=1, status=EvidenceStatus.ACTIVE,
        created_at="2026-07-13T00:00:00+00:00",
    )


def context(metadata=()):
    return InterpretationContext(
        "TX-DALLAS", "2026-07-13", "PROPERTY-RULES", "1", "POLICY", "1",
        "b" * 64, tuple(metadata),
    )


def request(operation_id="OP-1", observed_at="2026-07-13T01:00:00+00:00", reverse=False):
    evidence = (
        canonical("EV-1", "year_built", "1998"),
        canonical("EV-2", "living_area", "2432"),
    )
    provenance_records = (
        provenance("EV-1", "year_built", "1998"),
        provenance("EV-2", "living_area", "2432"),
    )
    if reverse:
        evidence = tuple(reversed(evidence))
        provenance_records = tuple(reversed(provenance_records))
    return InterpretationRequest(
        operation_id, "PROP-1", evidence, provenance_records,
        context((ApprovedContextValue("use", "residential", "POLICY:1"),)),
        observed_at,
    )


def raises(expected, constructor):
    try:
        constructor()
    except expected:
        return True
    return False


def run_checks():
    req = request()
    applicability = RuleApplicability(
        "RULE-AGE", "1", APPLICABLE, "JURISDICTION_AND_DATE_MATCH",
        "TX-DALLAS", "2020-01-01", None, ("year_built",), (),
    )
    dispositions = (
        EvidenceDisposition("EV-1", "RULE-AGE", SUPPORTS, "VALUE_SATISFIES_RULE"),
        EvidenceDisposition("EV-2", "RULE-AGE", IRRELEVANT, "FIELD_NOT_CONSUMED"),
    )
    unit = InterpretationUnit(
        "UNIT-1", "PROP-1", "PROP-1", "has_known_year_built", "true",
        CONCLUDED, "RULE_SATISFIED", applicability, dispositions,
        (PolicyConstraint("POLICY", "1", "C-1", "ALLOWED", "WITHIN_SCOPE"),),
    )
    result = InterpretationResult(req, (unit,), "COMPLETE", "ALL_RULES_EVALUATED")

    checks = {
        "canonical_evidence_is_input": all(isinstance(item, CanonicalEvidenceRecord) for item in req.evidence),
        "epm_provenance_is_input": all(isinstance(item, ProvenanceRecord) for item in req.provenance),
        "evidence_provenance_membership_exact": {x.evidence_id for x in req.evidence} == {x.evidence_id for x in req.provenance},
        "semantic_id_sha256": len(req.semantic_id()) == 64 and all(c in "0123456789abcdef" for c in req.semantic_id()),
        "operation_metadata_excluded_from_semantics": req.semantic_id() == request("OP-2", "2099-01-01T00:00:00+00:00").semantic_id(),
        "materialization_timestamps_excluded_from_semantics": req.semantic_id() == replace(
            req,
            evidence=tuple(replace(item, created_at="2099-01-01T00:00:00+00:00") for item in req.evidence),
            provenance=tuple(replace(item, created_at="2099-01-01T00:00:00+00:00") for item in req.provenance),
        ).semantic_id(),
        "input_order_irrelevant_to_semantics": req.semantic_id() == request(reverse=True).semantic_id(),
        "context_change_changes_semantics": req.semantic_id() != replace(req, context=replace(req.context, policy_version="2")).semantic_id(),
        "atomic_proposition_shape": (unit.subject, unit.predicate, unit.object_value) == ("PROP-1", "has_known_year_built", "true"),
        "every_evidence_has_disposition": {x.evidence_id for x in unit.evidence_dispositions} == {x.evidence_id for x in req.evidence},
        "supports_and_irrelevant_explicit": {x.disposition for x in dispositions} == {SUPPORTS, IRRELEVANT},
        "rule_applicability_versioned": unit.applicability.rule_id == "RULE-AGE" and unit.applicability.rule_version == "1",
        "policy_constraint_versioned": unit.policy_constraints[0].policy_version == req.context.policy_version,
        "result_retains_request": result.request is req,
        "no_confidence_field": all("confidence" not in item.name.lower() for item in fields(InterpretationResult)) and all("confidence" not in item.name.lower() for item in fields(InterpretationUnit)),
        "no_recommendation_field": all("recommend" not in item.name.lower() for item in fields(InterpretationResult)) and all("recommend" not in item.name.lower() for item in fields(InterpretationUnit)),
        "duplicate_evidence_rejected": raises(ValueError, lambda: replace(req, evidence=(req.evidence[0], req.evidence[0]))),
        "provenance_membership_mismatch_rejected": raises(ValueError, lambda: replace(req, provenance=req.provenance[:1])),
        "noncanonical_input_rejected": raises(TypeError, lambda: replace(req, evidence=(object(),))),
        "unknown_disposition_rejected": raises(ValueError, lambda: EvidenceDisposition("EV-1", "RULE", "MAYBE", "BAD")),
        "duplicate_disposition_rejected": raises(ValueError, lambda: replace(unit, evidence_dispositions=(dispositions[0], dispositions[0]))),
        "incomplete_disposition_ledger_rejected": raises(ValueError, lambda: InterpretationResult(req, (replace(unit, evidence_dispositions=dispositions[:1]),), "PARTIAL", "MISSING")),
        "missing_evidence_is_insufficient": RuleApplicability("RULE-X", "1", INSUFFICIENT_EVIDENCE, "REQUIRED_FIELD_MISSING", "TX-DALLAS", "2020-01-01", None, ("owner",), ("owner",)).status == INSUFFICIENT_EVIDENCE,
        "missing_evidence_cannot_conclude": raises(ValueError, lambda: replace(unit, applicability=RuleApplicability("RULE-AGE", "1", INSUFFICIENT_EVIDENCE, "MISSING", "TX-DALLAS", "2020-01-01", None, ("year_built",), ("year_built",)))),
        "indeterminate_cannot_assert_value": raises(ValueError, lambda: replace(unit, status=INDETERMINATE)),
        "opposition_requires_real_evidence_id": raises(ValueError, lambda: EvidenceDisposition("", "RULE-AGE", OPPOSES, "ABSENCE_IS_NOT_OPPOSITION")),
        "policy_version_mismatch_rejected": raises(ValueError, lambda: InterpretationResult(req, (replace(unit, policy_constraints=(PolicyConstraint("POLICY", "2", "C", "ALLOWED", "BAD"),)),), "COMPLETE", "BAD")),
        "unknown_result_status_rejected": raises(ValueError, lambda: replace(result, result_status="MAYBE")),
    }

    try:
        req.property_id = "CHANGED"
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["request_immutable"] = frozen
    try:
        unit.status = INDETERMINATE
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["interpretation_unit_immutable"] = frozen

    source = (Path(__file__).parent / "contracts.py").read_text(encoding="utf-8").lower()
    checks["no_legacy_engine_dependency"] = "reasoning_engine" not in source
    checks["no_persistence"] = all(term not in source for term in ("sqlite", "database", ".save(", "persist("))
    checks["no_scoring"] = all(term not in source for term in ("base_score", "adjusted_score", "weight_registry"))
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"RIL-CONTRACT-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
