"""RIL-001 deterministic typed field-predicate interpretation.

The evaluator is stateless and consumes only the verified RIL contract,
explicit rule profiles, and supplied policy projections.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import re

from era.canonical.canonical_enums import EvidenceValueType
from era.provenance.provenance_enums import EvidenceStatus
from era.reasoning.contracts import (
    APPLICABLE, BLOCKED, COMPLETE, CONCLUDED, FAILED, INDETERMINATE,
    INSUFFICIENT_EVIDENCE, IRRELEVANT, NOT_APPLICABLE, OPPOSES, PARTIAL,
    SUPPORTS, EvidenceDisposition, InterpretationResult, InterpretationUnit,
    PolicyConstraint, RuleApplicability,
)


RULE_PROFILE_VERSION = "1"

EQUALS = "EQUALS"
NOT_EQUALS = "NOT_EQUALS"
EXISTS = "EXISTS"
IN_DECLARED_SET = "IN_DECLARED_SET"
COMPARISON_OPERATORS = frozenset({EQUALS, NOT_EQUALS, EXISTS, IN_DECLARED_SET})

RIL_REQUIRED_PROVENANCE_FIELDS = (
    "evidence_hash", "provider_id", "source_reference", "retrieved_at",
    "normalization_version", "artifact_sha256", "package_id", "execution_id",
    "canonical_source_id", "parser_id", "parser_version", "schema_profile_id",
    "schema_profile_version", "source_location", "candidate_id",
    "candidate_validation_status",
)


def _required(*values):
    if any(value is None or (isinstance(value, str) and not value.strip()) for value in values):
        raise ValueError("REQUIRED_RULE_VALUE_MISSING")


def _expected_type(value_type):
    if value_type == EvidenceValueType.INTEGER:
        return int
    if value_type in {EvidenceValueType.DECIMAL, EvidenceValueType.CURRENCY}:
        return Decimal
    if value_type == EvidenceValueType.BOOLEAN:
        return bool
    if value_type == EvidenceValueType.DATE:
        return date
    return str


def _is_exact_type(value, value_type):
    expected = _expected_type(value_type)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is date:
        return isinstance(value, date) and not isinstance(value, datetime)
    return type(value) is expected


def _json_ready(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


@dataclass(frozen=True)
class FieldPredicateRule:
    rule_id: str
    rule_version: str
    jurisdiction: str
    effective_from: date
    effective_to: date | None
    required_canonical_field: str
    required_ecm_value_type: EvidenceValueType
    comparison_operator: str
    expected_value: object | None
    profile_version: str = RULE_PROFILE_VERSION

    def __post_init__(self):
        _required(
            self.rule_id, self.rule_version, self.jurisdiction, self.effective_from,
            self.required_canonical_field, self.comparison_operator, self.profile_version,
        )
        if self.profile_version != RULE_PROFILE_VERSION:
            raise ValueError("UNKNOWN_RULE_PROFILE_VERSION")
        if not isinstance(self.effective_from, date) or isinstance(self.effective_from, datetime):
            raise TypeError("RULE_EFFECTIVE_FROM_MUST_BE_DATE")
        if self.effective_to is not None and (
            not isinstance(self.effective_to, date) or isinstance(self.effective_to, datetime)
        ):
            raise TypeError("RULE_EFFECTIVE_TO_MUST_BE_DATE")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("INVALID_RULE_EFFECTIVE_INTERVAL")
        if not isinstance(self.required_ecm_value_type, EvidenceValueType):
            raise TypeError("RULE_ECM_VALUE_TYPE_REQUIRED")
        if self.comparison_operator not in COMPARISON_OPERATORS:
            raise ValueError("UNKNOWN_COMPARISON_OPERATOR")

        if self.comparison_operator == EXISTS:
            if self.expected_value is not None:
                raise ValueError("EXISTS_RULE_CANNOT_DECLARE_EXPECTED_VALUE")
            return
        if self.comparison_operator == IN_DECLARED_SET:
            if not isinstance(self.expected_value, tuple) or not self.expected_value:
                raise ValueError("DECLARED_SET_MUST_BE_NONEMPTY_TUPLE")
            if any(not _is_exact_type(item, self.required_ecm_value_type) for item in self.expected_value):
                raise TypeError("DECLARED_SET_TYPE_MISMATCH")
            if len(self.expected_value) != len(set(self.expected_value)):
                raise ValueError("DUPLICATE_DECLARED_SET_VALUE")
            return
        if not _is_exact_type(self.expected_value, self.required_ecm_value_type):
            raise TypeError("RULE_EXPECTED_VALUE_TYPE_MISMATCH")


class FieldPredicateInterpreter:
    """Pure RIL-001 evaluator. It owns no registry, clock, store, or policy."""

    def evaluate(
        self, request, rules: tuple[FieldPredicateRule, ...],
        policy_constraints: tuple[PolicyConstraint, ...], *, max_rules: int,
        max_evidence: int,
    ) -> InterpretationResult:
        if not isinstance(rules, tuple) or not all(isinstance(rule, FieldPredicateRule) for rule in rules):
            raise TypeError("EXPLICIT_IMMUTABLE_RULES_REQUIRED")
        if not rules:
            return InterpretationResult(request, (), FAILED, "RULES_REQUIRED")
        identities = tuple((rule.rule_id, rule.rule_version) for rule in rules)
        if len(identities) != len(set(identities)):
            raise ValueError("DUPLICATE_RULE_IDENTITY")
        if not isinstance(policy_constraints, tuple) or not all(
            isinstance(item, PolicyConstraint) for item in policy_constraints
        ):
            raise TypeError("IMMUTABLE_POLICY_PROJECTION_REQUIRED")

        ordered_rules = tuple(sorted(rules, key=lambda item: (item.rule_id, item.rule_version)))
        ordered_policy = tuple(sorted(
            policy_constraints,
            key=lambda item: (item.policy_id, item.policy_version, item.constraint_id),
        ))
        global_failure = self._preflight(
            request, ordered_rules, ordered_policy, max_rules, max_evidence,
        )
        if global_failure:
            units = tuple(
                self._blocked_unit(request, rule, ordered_policy, global_failure)
                for rule in ordered_rules
            )
            return InterpretationResult(request, units, FAILED, global_failure)

        units = tuple(self._evaluate_rule(request, rule, ordered_policy) for rule in ordered_rules)
        indeterminate = sum(item.status == INDETERMINATE for item in units)
        if indeterminate == len(units):
            result_status, reason = FAILED, "NO_CONCLUSIVE_RULES"
        elif indeterminate:
            result_status, reason = PARTIAL, "PARTIAL_RULE_EVALUATION"
        else:
            result_status, reason = COMPLETE, "ALL_RULES_EVALUATED"
        return InterpretationResult(request, units, result_status, reason)

    @staticmethod
    def _preflight(request, rules, policy_constraints, max_rules, max_evidence):
        if type(max_rules) is not int or type(max_evidence) is not int or max_rules <= 0 or max_evidence <= 0:
            return "INVALID_EVALUATION_LIMIT"
        if len(rules) > max_rules or len(request.evidence) > max_evidence:
            return "EVALUATION_LIMIT_EXCEEDED"
        if not policy_constraints:
            return "POLICY_PROJECTION_REQUIRED"
        constraint_ids = tuple(item.constraint_id for item in policy_constraints)
        if len(constraint_ids) != len(set(constraint_ids)):
            return "DUPLICATE_POLICY_CONSTRAINT"
        if any(
            item.policy_id != request.context.policy_id
            or item.policy_version != request.context.policy_version
            for item in policy_constraints
        ):
            return "POLICY_VERSION_MISMATCH"

        by_evidence = {item.evidence_id: item for item in request.evidence}
        for provenance in request.provenance:
            if provenance.status != EvidenceStatus.ACTIVE:
                return "INACTIVE_PROVENANCE"
            if provenance.superseded_by is not None:
                return "SUPERSEDED_PROVENANCE"
            if any(not getattr(provenance, field, None) for field in RIL_REQUIRED_PROVENANCE_FIELDS):
                return "INCOMPLETE_PROVENANCE"
            if provenance.candidate_validation_status != "VALID":
                return "INVALID_PROVENANCE"
            evidence = by_evidence[provenance.evidence_id]
            if (
                provenance.canonical_field != evidence.field_name
                or provenance.canonical_value != evidence.normalized_value
            ):
                return "CANONICAL_PROVENANCE_MAPPING_MISMATCH"
        return None

    def _evaluate_rule(self, request, rule, policy_constraints):
        as_of = self._parse_as_of(request.context.as_of)
        if as_of is None:
            return self._blocked_unit(request, rule, policy_constraints, "INVALID_AS_OF_DATE")
        if request.context.jurisdiction != rule.jurisdiction:
            return self._not_applicable(request, rule, policy_constraints, "JURISDICTION_NOT_APPLICABLE")
        if as_of < rule.effective_from or (rule.effective_to is not None and as_of > rule.effective_to):
            return self._not_applicable(request, rule, policy_constraints, "OUTSIDE_EFFECTIVE_INTERVAL")
        if any(item.effect == BLOCKED for item in policy_constraints):
            return self._blocked_unit(request, rule, policy_constraints, "POLICY_BLOCKED_EVALUATION")

        relevant = tuple(item for item in request.evidence if item.field_name == rule.required_canonical_field)
        if not relevant:
            applicability = self._applicability(
                rule, INSUFFICIENT_EVIDENCE, "REQUIRED_FIELD_MISSING",
                (rule.required_canonical_field,),
            )
            return self._unit(
                request, rule, policy_constraints, applicability,
                self._all_irrelevant(request, rule, "FIELD_NOT_CONSUMED"),
                INDETERMINATE, None, "REQUIRED_FIELD_MISSING",
            )
        if any(item.value_type != rule.required_ecm_value_type for item in relevant):
            applicability = self._applicability(rule, APPLICABLE, "ECM_TYPE_MISMATCH")
            dispositions = tuple(
                EvidenceDisposition(
                    item.evidence_id, rule.rule_id, IRRELEVANT,
                    "ECM_TYPE_MISMATCH" if item in relevant else "FIELD_NOT_CONSUMED",
                )
                for item in sorted(request.evidence, key=lambda value: value.evidence_id)
            )
            return self._unit(
                request, rule, policy_constraints, applicability, dispositions,
                INDETERMINATE, None, "ECM_TYPE_MISMATCH",
            )

        try:
            parsed = tuple((item, self._typed_value(item.normalized_value, item.value_type)) for item in relevant)
        except (ValueError, InvalidOperation):
            return self._blocked_unit(request, rule, policy_constraints, "MALFORMED_CANONICAL_VALUE")

        dispositions_by_id = {}
        for item in request.evidence:
            if item.field_name != rule.required_canonical_field:
                dispositions_by_id[item.evidence_id] = EvidenceDisposition(
                    item.evidence_id, rule.rule_id, IRRELEVANT, "FIELD_NOT_CONSUMED",
                )
        results = []
        for item, typed_value in parsed:
            satisfies = self._compare(rule, typed_value)
            results.append((item, typed_value, satisfies))
            dispositions_by_id[item.evidence_id] = EvidenceDisposition(
                item.evidence_id, rule.rule_id, SUPPORTS if satisfies else OPPOSES,
                "VALUE_SATISFIES_RULE" if satisfies else "VALUE_OPPOSES_RULE",
            )
        dispositions = tuple(dispositions_by_id[key] for key in sorted(dispositions_by_id))
        distinct_values = {item[1] for item in results}
        applicability = self._applicability(rule, APPLICABLE, "RULE_APPLICABLE")
        if len(distinct_values) > 1:
            return self._unit(
                request, rule, policy_constraints, applicability, dispositions,
                INDETERMINATE, None, "CONFLICTING_CANONICAL_VALUES",
            )
        satisfied = results[0][2]
        return self._unit(
            request, rule, policy_constraints, applicability, dispositions,
            CONCLUDED, "true" if satisfied else "false",
            "RULE_SATISFIED" if satisfied else "RULE_NOT_SATISFIED",
        )

    @staticmethod
    def _parse_as_of(value):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _typed_value(value, value_type):
        if not isinstance(value, str) or value != value.strip():
            raise ValueError("NON_CANONICAL_LEXICAL_VALUE")
        if value_type in {
            EvidenceValueType.TEXT, EvidenceValueType.OFFICIAL_TEXT,
            EvidenceValueType.IDENTIFIER, EvidenceValueType.GEO, EvidenceValueType.ENUM,
        }:
            return value
        if value_type == EvidenceValueType.INTEGER:
            if not re.fullmatch(r"[+-]?(0|[1-9][0-9]*)", value):
                raise ValueError("MALFORMED_INTEGER")
            return int(value)
        if value_type == EvidenceValueType.DECIMAL:
            return Decimal(value)
        if value_type == EvidenceValueType.CURRENCY:
            candidate = value.replace(",", "")
            if candidate.startswith("$"):
                candidate = candidate[1:]
            return Decimal(candidate)
        if value_type == EvidenceValueType.BOOLEAN:
            if value not in {"true", "false"}:
                raise ValueError("MALFORMED_BOOLEAN")
            return value == "true"
        if value_type == EvidenceValueType.DATE:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("NON_CANONICAL_DATE")
            return parsed
        raise ValueError("UNSUPPORTED_ECM_TYPE")

    @staticmethod
    def _compare(rule, value):
        if rule.comparison_operator == EXISTS:
            return True
        if rule.comparison_operator == EQUALS:
            return value == rule.expected_value
        if rule.comparison_operator == NOT_EQUALS:
            return value != rule.expected_value
        return value in rule.expected_value

    def _not_applicable(self, request, rule, policy_constraints, reason):
        applicability = self._applicability(rule, NOT_APPLICABLE, reason)
        return self._unit(
            request, rule, policy_constraints, applicability,
            self._all_irrelevant(request, rule, reason), NOT_APPLICABLE, None, reason,
        )

    def _blocked_unit(self, request, rule, policy_constraints, reason):
        applicability = self._applicability(rule, APPLICABLE, reason)
        safe_policy = tuple(
            item for item in policy_constraints
            if item.policy_id == request.context.policy_id
            and item.policy_version == request.context.policy_version
        )
        return self._unit(
            request, rule, safe_policy, applicability,
            self._all_irrelevant(request, rule, reason), INDETERMINATE, None, reason,
        )

    @staticmethod
    def _all_irrelevant(request, rule, reason):
        return tuple(
            EvidenceDisposition(item.evidence_id, rule.rule_id, IRRELEVANT, reason)
            for item in sorted(request.evidence, key=lambda value: value.evidence_id)
        )

    @staticmethod
    def _applicability(rule, status, reason, missing_fields=()):
        return RuleApplicability(
            rule.rule_id, rule.rule_version, status, reason, rule.jurisdiction,
            rule.effective_from.isoformat(),
            rule.effective_to.isoformat() if rule.effective_to else None,
            (rule.required_canonical_field,), tuple(missing_fields),
        )

    def _unit(
        self, request, rule, policy_constraints, applicability, dispositions,
        status, object_value, reason,
    ):
        return InterpretationUnit(
            unit_id=self._unit_id(
                request, rule, policy_constraints, applicability, dispositions,
                status, object_value, reason,
            ),
            property_id=request.property_id,
            subject=request.property_id,
            predicate=f"{rule.required_canonical_field}.{rule.comparison_operator.lower()}",
            object_value=object_value,
            status=status,
            reason_code=reason,
            applicability=applicability,
            evidence_dispositions=tuple(dispositions),
            policy_constraints=tuple(policy_constraints),
        )

    @staticmethod
    def _unit_id(
        request, rule, policy_constraints, applicability, dispositions,
        status, object_value, reason,
    ):
        rule_material = _json_ready(asdict(rule))
        if rule.comparison_operator == IN_DECLARED_SET:
            rule_material["expected_value"] = sorted(
                rule_material["expected_value"],
                key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
            )
        material = {
            "request_semantic_id": request.semantic_id(),
            "rule": rule_material,
            "policy": sorted(
                (_json_ready(asdict(item)) for item in policy_constraints),
                key=lambda item: (item["policy_id"], item["policy_version"], item["constraint_id"]),
            ),
            "applicability": _json_ready(asdict(applicability)),
            "dispositions": sorted(
                (_json_ready(asdict(item)) for item in dispositions),
                key=lambda item: item["evidence_id"],
            ),
            "status": status,
            "object_value": object_value,
            "reason": reason,
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "INT-" + hashlib.sha256(encoded).hexdigest()
