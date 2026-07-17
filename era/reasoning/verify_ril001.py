"""RIL-001 deterministic typed interpretation and boundary verification."""

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from era.canonical.canonical_enums import (
    EvidenceCategory, EvidenceSourceClass, EvidenceValueType,
)
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.provenance.provenance_enums import EvidenceStatus
from era.provenance.provenance_models import ProvenanceRecord
from era.reasoning.contracts import (
    ALLOWED, APPLICABLE, BLOCKED, CONCLUDED, INDETERMINATE,
    INSUFFICIENT_EVIDENCE, IRRELEVANT, NOT_APPLICABLE, OPPOSES, SUPPORTS,
    InterpretationContext, InterpretationRequest, InterpretationResult,
    InterpretationUnit, PolicyConstraint,
)
from era.reasoning.field_predicate import (
    EQUALS, EXISTS, IN_DECLARED_SET, NOT_EQUALS, RULE_PROFILE_VERSION,
    FieldPredicateInterpreter, FieldPredicateRule,
)


def canonical(evidence_id, field_name, value, value_type, property_id="PROP-1"):
    return CanonicalEvidenceRecord(
        evidence_id=evidence_id,
        property_id=property_id,
        category=EvidenceCategory.BUILDING,
        field_name=field_name,
        raw_value=value,
        normalized_value=value,
        units=None,
        provenance=Provenance(
            "DCAD", "Dallas CAD", "DCAD", EvidenceSourceClass.PUBLIC_RECORD,
            "2026-07-13T00:00:00+00:00", "PUBLIC_RECORD", "ECM-1", evidence_id,
        ),
        value_type=value_type,
        created_at="2026-07-13T00:00:00+00:00",
    )


def provenance(record, status=EvidenceStatus.ACTIVE, superseded_by=None, **changes):
    values = dict(
        evidence_id=record.evidence_id,
        property_id=record.property_id,
        canonical_field=record.field_name,
        canonical_value=record.normalized_value,
        original_value=record.raw_value,
        provider_id="DCAD",
        provider_name="Dallas CAD",
        legal_basis="PUBLIC_RECORD",
        source_reference="DCAD",
        retrieved_at="2026-07-13T00:00:00+00:00",
        connector_version="1",
        adapter_version="1",
        normalization_version="ECM-1",
        evidence_hash="a" * 64,
        previous_evidence_id=None,
        superseded_by=superseded_by,
        chain_position=1,
        status=status,
        created_at="2026-07-13T00:00:00+00:00",
        artifact_sha256="b" * 64,
        package_id="PKG-1",
        execution_id="EXEC-1",
        canonical_source_id="src:tx-dallas:dcad:appraisal:parcel",
        parser_id="CSV",
        parser_version="1",
        schema_profile_id="DCAD",
        schema_profile_version="1",
        source_location=f"row:1/field:{record.field_name}",
        trace_contract_version="1",
        candidate_id=f"CAND-{record.evidence_id}",
        candidate_validation_status="VALID",
        artifact_algorithm="SHA256",
        artifact_digest="b" * 64,
        artifact_byte_length=100,
        artifact_media_type="text/csv",
        artifact_content_uri="artifact://PKG-1/1",
        original_lexical_value=record.raw_value,
        parsed_value=record.normalized_value,
        proposed_value_type=record.value_type.value,
    )
    values.update(changes)
    return ProvenanceRecord(**values)


def request(records, provenance_records=None, jurisdiction="TX-DALLAS", as_of="2026-07-13", operation_id="OP-1"):
    records = tuple(records)
    provenance_records = tuple(provenance_records or tuple(provenance(item) for item in records))
    return InterpretationRequest(
        operation_id=operation_id,
        property_id="PROP-1",
        evidence=records,
        provenance=provenance_records,
        context=InterpretationContext(
            jurisdiction, as_of, "PROPERTY-RULES", "1", "POLICY", "1", "c" * 64,
        ),
        observed_at="2026-07-13T01:00:00+00:00",
    )


def rule(rule_id, field, value_type, operator, expected, jurisdiction="TX-DALLAS"):
    return FieldPredicateRule(
        rule_id, "1", jurisdiction, date(2020, 1, 1), None,
        field, value_type, operator, expected,
    )


def policy(effect=ALLOWED, version="1"):
    return (PolicyConstraint("POLICY", version, "INTERPRET", effect, "APPROVED"),)


def raises(expected, constructor, message=None):
    try:
        constructor()
    except expected as exc:
        return message is None or str(exc) == message
    return False


def meaning(unit):
    return (
        unit.predicate, unit.object_value, unit.status, unit.reason_code,
        unit.applicability.status,
        tuple((item.evidence_id, item.disposition, item.reason_code) for item in unit.evidence_dispositions),
    )


def run_checks():
    records = (
        canonical("EV-PARCEL", "parcel_id", "001", EvidenceValueType.IDENTIFIER),
        canonical("EV-YEAR", "year_built", "1998", EvidenceValueType.INTEGER),
        canonical("EV-OWNER", "owner", "SMITH", EvidenceValueType.TEXT),
        canonical("EV-CLASS", "property_class", "A", EvidenceValueType.ENUM),
    )
    rules = (
        rule("RULE-EQUALS", "parcel_id", EvidenceValueType.IDENTIFIER, EQUALS, "001"),
        rule("RULE-NOT-EQUALS", "year_built", EvidenceValueType.INTEGER, NOT_EQUALS, 2000),
        rule("RULE-EXISTS", "owner", EvidenceValueType.TEXT, EXISTS, None),
        rule("RULE-IN-SET", "property_class", EvidenceValueType.ENUM, IN_DECLARED_SET, ("A", "B")),
    )
    service = FieldPredicateInterpreter()
    req = request(records)
    before = (tuple(asdict(item) for item in req.evidence), tuple(asdict(item) for item in req.provenance))
    result = service.evaluate(req, rules, policy(), max_rules=8, max_evidence=16)
    after = (tuple(asdict(item) for item in req.evidence), tuple(asdict(item) for item in req.provenance))
    units = {item.applicability.rule_id: item for item in result.units}

    reverse_req = request(tuple(reversed(records)), tuple(reversed(req.provenance)), operation_id="OP-2")
    reverse_result = service.evaluate(reverse_req, tuple(reversed(rules)), policy(), max_rules=8, max_evidence=16)
    reverse_units = {item.applicability.rule_id: item for item in reverse_result.units}

    changed_records = tuple(
        replace(item, raw_value="2000", normalized_value="2000") if item.evidence_id == "EV-YEAR" else item
        for item in records
    )
    changed_provenance = tuple(
        replace(item, original_value="2000", canonical_value="2000", parsed_value="2000")
        if item.evidence_id == "EV-YEAR" else item
        for item in req.provenance
    )
    changed = service.evaluate(
        request(changed_records, changed_provenance), rules, policy(),
        max_rules=8, max_evidence=16,
    )
    changed_units = {item.applicability.rule_id: item for item in changed.units}

    conflict_record = canonical("EV-YEAR-2", "year_built", "2001", EvidenceValueType.INTEGER)
    conflict_req = request(records + (conflict_record,))
    conflict = service.evaluate(
        conflict_req, (rules[1],), policy(), max_rules=8, max_evidence=16,
    ).units[0]

    missing_records = tuple(item for item in records if item.field_name != "owner")
    missing = service.evaluate(
        request(missing_records), (rules[2],), policy(), max_rules=8, max_evidence=16,
    ).units[0]

    irrelevant_record = canonical("EV-CITY", "city", "Dallas", EvidenceValueType.TEXT)
    irrelevant_result = service.evaluate(
        request(records + (irrelevant_record,)), (rules[0],), policy(),
        max_rules=8, max_evidence=16,
    ).units[0]

    decimal_record = canonical("EV-VALUE", "market_value", "152500.00", EvidenceValueType.DECIMAL)
    decimal_rule = rule(
        "RULE-DECIMAL", "market_value", EvidenceValueType.DECIMAL,
        EQUALS, Decimal("152500.00"),
    )
    decimal_result = service.evaluate(
        request((decimal_record,)), (decimal_rule,), policy(), max_rules=8, max_evidence=16,
    ).units[0]

    decimal_equivalent = canonical("EV-VALUE-2", "market_value", "152500.0", EvidenceValueType.DECIMAL)
    decimal_equivalent_result = service.evaluate(
        request((decimal_record, decimal_equivalent)), (decimal_rule,), policy(),
        max_rules=8, max_evidence=16,
    ).units[0]

    date_record = canonical("EV-DATE", "appraisal_date", "2026-01-01", EvidenceValueType.DATE)
    date_rule = rule(
        "RULE-DATE", "appraisal_date", EvidenceValueType.DATE,
        EQUALS, date(2026, 1, 1),
    )
    date_result = service.evaluate(
        request((date_record,)), (date_rule,), policy(), max_rules=8, max_evidence=16,
    ).units[0]

    checks = {
        "returns_verified_result_model": isinstance(result, InterpretationResult),
        "returns_verified_unit_models_only": all(isinstance(item, InterpretationUnit) for item in result.units),
        "one_unit_per_rule": len(result.units) == len(rules),
        "rule_order_canonical": tuple(item.applicability.rule_id for item in result.units) == tuple(sorted(item.rule_id for item in rules)),
        "equals_operator_exact": units["RULE-EQUALS"].status == CONCLUDED and units["RULE-EQUALS"].object_value == "true",
        "not_equals_operator_exact": units["RULE-NOT-EQUALS"].status == CONCLUDED and units["RULE-NOT-EQUALS"].object_value == "true",
        "exists_operator_exact": units["RULE-EXISTS"].status == CONCLUDED and units["RULE-EXISTS"].object_value == "true",
        "declared_set_operator_exact": units["RULE-IN-SET"].status == CONCLUDED and units["RULE-IN-SET"].object_value == "true",
        "decimal_comparison_exact": decimal_result.status == CONCLUDED and decimal_result.object_value == "true",
        "equivalent_decimal_lexicals_not_conflict": decimal_equivalent_result.status == CONCLUDED,
        "date_comparison_exact": date_result.status == CONCLUDED and date_result.object_value == "true",
        "every_evidence_dispositioned_per_rule": all(len(item.evidence_dispositions) == len(records) for item in result.units),
        "verified_disposition_vocabulary_only": all(item.disposition in {SUPPORTS, OPPOSES, IRRELEVANT} for unit in result.units for item in unit.evidence_dispositions),
        "supporting_ids_derived_from_dispositions": tuple(item.evidence_id for item in units["RULE-EQUALS"].evidence_dispositions if item.disposition == SUPPORTS) == ("EV-PARCEL",),
        "opposing_ids_derived_not_stored": not hasattr(units["RULE-EQUALS"], "opposing_evidence_ids"),
        "reordered_evidence_same_units": all(meaning(units[key]) == meaning(reverse_units[key]) for key in units),
        "reordered_evidence_same_replay_ids": all(units[key].unit_id == reverse_units[key].unit_id for key in units),
        "declared_set_order_semantically_irrelevant": service.evaluate(req, (rules[3],), policy(), max_rules=8, max_evidence=16).units[0].unit_id == service.evaluate(req, (replace(rules[3], expected_value=("B", "A")),), policy(), max_rules=8, max_evidence=16).units[0].unit_id,
        "changed_field_affects_declaring_rule": meaning(units["RULE-NOT-EQUALS"]) != meaning(changed_units["RULE-NOT-EQUALS"]),
        "changed_field_does_not_change_other_meaning": all(meaning(units[key]) == meaning(changed_units[key]) for key in units if key != "RULE-NOT-EQUALS"),
        "conflict_is_indeterminate": conflict.status == INDETERMINATE and conflict.reason_code == "CONFLICTING_CANONICAL_VALUES",
        "conflict_has_no_asserted_value": conflict.object_value is None,
        "absence_is_insufficient_not_opposition": missing.status == INDETERMINATE and missing.applicability.status == INSUFFICIENT_EVIDENCE and missing.applicability.missing_fields == ("owner",),
        "missing_has_no_invented_id": all(item.evidence_id in {record.evidence_id for record in missing_records} for item in missing.evidence_dispositions),
        "irrelevant_evidence_does_not_change_outcome": (irrelevant_result.status, irrelevant_result.object_value) == (units["RULE-EQUALS"].status, units["RULE-EQUALS"].object_value),
        "irrelevant_evidence_updates_complete_trace": irrelevant_result.unit_id != units["RULE-EQUALS"].unit_id,
        "jurisdiction_mismatch_not_applicable": service.evaluate(request(records, jurisdiction="TX-TARRANT"), (rules[0],), policy(), max_rules=8, max_evidence=16).units[0].status == NOT_APPLICABLE,
        "inactive_provenance_fails_evaluation": service.evaluate(request(records, (provenance(records[0], status=EvidenceStatus.REJECTED),) + req.provenance[1:]), (rules[0],), policy(), max_rules=8, max_evidence=16).reason_code == "INACTIVE_PROVENANCE",
        "superseded_provenance_fails_evaluation": service.evaluate(request(records, (provenance(records[0], superseded_by="EV-NEXT"),) + req.provenance[1:]), (rules[0],), policy(), max_rules=8, max_evidence=16).reason_code == "SUPERSEDED_PROVENANCE",
        "incomplete_provenance_fails_evaluation": service.evaluate(request(records, (replace(req.provenance[0], parser_id=""),) + req.provenance[1:]), (rules[0],), policy(), max_rules=8, max_evidence=16).reason_code == "INCOMPLETE_PROVENANCE",
        "invalid_provenance_fails_evaluation": service.evaluate(request(records, (replace(req.provenance[0], candidate_validation_status="INVALID"),) + req.provenance[1:]), (rules[0],), policy(), max_rules=8, max_evidence=16).reason_code == "INVALID_PROVENANCE",
        "mapping_mismatch_fails_evaluation": service.evaluate(request(records, (replace(req.provenance[0], canonical_value="WRONG"),) + req.provenance[1:]), (rules[0],), policy(), max_rules=8, max_evidence=16).reason_code == "CANONICAL_PROVENANCE_MAPPING_MISMATCH",
        "policy_version_mismatch_fails_closed": service.evaluate(req, (rules[0],), policy(version="2"), max_rules=8, max_evidence=16).reason_code == "POLICY_VERSION_MISMATCH",
        "policy_block_visible_indeterminate": service.evaluate(req, (rules[0],), policy(effect=BLOCKED), max_rules=8, max_evidence=16).units[0].reason_code == "POLICY_BLOCKED_EVALUATION",
        "rule_limit_fails_without_truncation": len(service.evaluate(req, rules, policy(), max_rules=1, max_evidence=16).units) == len(rules),
        "evidence_limit_fails_closed": service.evaluate(req, (rules[0],), policy(), max_rules=8, max_evidence=1).reason_code == "EVALUATION_LIMIT_EXCEEDED",
        "unknown_profile_version_rejected": raises(ValueError, lambda: replace(rules[0], profile_version="2"), "UNKNOWN_RULE_PROFILE_VERSION"),
        "unknown_operator_rejected": raises(ValueError, lambda: replace(rules[0], comparison_operator="FUZZY"), "UNKNOWN_COMPARISON_OPERATOR"),
        "silent_integer_string_coercion_rejected": raises(TypeError, lambda: replace(rules[1], expected_value="2000"), "RULE_EXPECTED_VALUE_TYPE_MISMATCH"),
        "floating_decimal_rejected": raises(TypeError, lambda: replace(decimal_rule, expected_value=152500.0), "RULE_EXPECTED_VALUE_TYPE_MISMATCH"),
        "duplicate_rule_identity_rejected": raises(ValueError, lambda: service.evaluate(req, (rules[0], rules[0]), policy(), max_rules=8, max_evidence=16), "DUPLICATE_RULE_IDENTITY"),
        "inputs_not_mutated": before == after,
        "rule_profile_version_locked": all(item.profile_version == RULE_PROFILE_VERSION for item in rules),
    }

    try:
        rules[0].rule_id = "CHANGED"
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["rules_immutable"] = frozen

    source = (Path(__file__).parent / "field_predicate.py").read_text(encoding="utf-8").lower()
    checks.update({
        "no_legacy_engine": "reasoning_engine" not in source,
        "no_persistence": all(term not in source for term in ("sqlite", ".save(", "persist(")),
        "no_confidence": "confidence" not in source,
        "no_recommendation": "recommend" not in source,
        "no_learning_or_randomness": all(term not in source for term in ("machine learning", "import random", "llm_", "bayesian", "fuzzy")),
        "no_conflict_resolver": "conflictresolver" not in source and "era.conflict" not in source,
        "no_acquisition_or_parser_dependency": all(term not in source for term in ("acquisition_execution", "rawartifact", "deterministicartifactparser", "source discovery")),
        "no_hidden_rule_registry": "rule_registry" not in source and "default_rule" not in source,
    })
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"RIL-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
