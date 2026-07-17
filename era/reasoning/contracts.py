"""RIL-CONTRACT-001 immutable, evidence-traceable interpretation contracts.

This module defines the boundary only. It contains no inference, scoring,
recommendation, persistence, canonicalization, or provenance registration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json

from era.canonical.canonical_models import CanonicalEvidenceRecord
from era.provenance.provenance_models import ProvenanceRecord


CONTRACT_VERSION = "1"

SUPPORTS = "SUPPORTS"
OPPOSES = "OPPOSES"
IRRELEVANT = "IRRELEVANT"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
EVIDENCE_DISPOSITIONS = frozenset({SUPPORTS, OPPOSES, IRRELEVANT})

APPLICABLE = "APPLICABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
RULE_APPLICABILITY = frozenset({APPLICABLE, NOT_APPLICABLE, INSUFFICIENT_EVIDENCE})

CONCLUDED = "CONCLUDED"
INDETERMINATE = "INDETERMINATE"
UNIT_STATUSES = frozenset({CONCLUDED, INDETERMINATE, NOT_APPLICABLE})

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
RESULT_STATUSES = frozenset({COMPLETE, PARTIAL, FAILED})

ALLOWED = "ALLOWED"
BLOCKED = "BLOCKED"
LIMITED = "LIMITED"
POLICY_EFFECTS = frozenset({ALLOWED, BLOCKED, LIMITED})


def _required(*values):
    if any(value is None or (isinstance(value, str) and not value.strip()) for value in values):
        raise ValueError("REQUIRED_CONTRACT_VALUE_MISSING")


def _json_ready(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


@dataclass(frozen=True)
class ApprovedContextValue:
    key: str
    value: str
    authority_reference: str

    def __post_init__(self):
        _required(self.key, self.value, self.authority_reference)


@dataclass(frozen=True)
class InterpretationContext:
    jurisdiction: str
    as_of: str
    rule_set_id: str
    rule_set_version: str
    policy_id: str
    policy_version: str
    configuration_digest: str
    approved_metadata: tuple[ApprovedContextValue, ...] = ()

    def __post_init__(self):
        _required(
            self.jurisdiction,
            self.as_of,
            self.rule_set_id,
            self.rule_set_version,
            self.policy_id,
            self.policy_version,
            self.configuration_digest,
        )
        if not isinstance(self.approved_metadata, tuple):
            raise ValueError("APPROVED_METADATA_MUST_BE_IMMUTABLE")
        keys = tuple(item.key for item in self.approved_metadata)
        if len(keys) != len(set(keys)):
            raise ValueError("DUPLICATE_CONTEXT_KEY")


@dataclass(frozen=True)
class InterpretationRequest:
    operation_id: str
    property_id: str
    evidence: tuple[CanonicalEvidenceRecord, ...]
    provenance: tuple[ProvenanceRecord, ...]
    context: InterpretationContext
    observed_at: str
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self):
        _required(
            self.operation_id,
            self.property_id,
            self.observed_at,
            self.contract_version,
        )
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError("INTERPRETATION_CONTRACT_VERSION_MISMATCH")
        if not isinstance(self.evidence, tuple) or not isinstance(self.provenance, tuple):
            raise ValueError("INTERPRETATION_INPUTS_MUST_BE_IMMUTABLE")
        if not self.evidence:
            raise ValueError("CANONICAL_EVIDENCE_REQUIRED")
        if any(not isinstance(item, CanonicalEvidenceRecord) for item in self.evidence):
            raise TypeError("CANONICAL_EVIDENCE_ONLY")
        if any(not isinstance(item, ProvenanceRecord) for item in self.provenance):
            raise TypeError("EPM_PROVENANCE_ONLY")

        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        provenance_ids = tuple(item.evidence_id for item in self.provenance)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("DUPLICATE_CANONICAL_EVIDENCE_ID")
        if len(provenance_ids) != len(set(provenance_ids)):
            raise ValueError("DUPLICATE_PROVENANCE_EVIDENCE_ID")
        if set(evidence_ids) != set(provenance_ids):
            raise ValueError("CANONICAL_PROVENANCE_MEMBERSHIP_MISMATCH")
        if any(item.property_id != self.property_id for item in self.evidence):
            raise ValueError("CANONICAL_PROPERTY_MISMATCH")
        if any(item.property_id != self.property_id for item in self.provenance):
            raise ValueError("PROVENANCE_PROPERTY_MISMATCH")

    def semantic_id(self) -> str:
        """Stable identity excluding operation ID and observation timestamp."""
        evidence = sorted(
            (_json_ready(asdict(item)) for item in self.evidence),
            key=lambda item: item["evidence_id"],
        )
        provenance = sorted(
            (_json_ready(asdict(item)) for item in self.provenance),
            key=lambda item: item["evidence_id"],
        )
        # Record-materialization timestamps are operational observations,
        # not evidence semantics. Source retrieval/as-of timestamps remain.
        for item in evidence:
            item.pop("created_at", None)
        for item in provenance:
            item.pop("created_at", None)
        context = _json_ready(asdict(self.context))
        context["approved_metadata"] = sorted(
            context["approved_metadata"], key=lambda item: item["key"]
        )
        material = json.dumps(
            {
                "contract_version": self.contract_version,
                "property_id": self.property_id,
                "evidence": evidence,
                "provenance": provenance,
                "context": context,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True)
class EvidenceDisposition:
    evidence_id: str
    rule_id: str
    disposition: str
    reason_code: str

    def __post_init__(self):
        _required(self.evidence_id, self.rule_id, self.reason_code)
        if self.disposition not in EVIDENCE_DISPOSITIONS:
            raise ValueError("UNKNOWN_EVIDENCE_DISPOSITION")


@dataclass(frozen=True)
class RuleApplicability:
    rule_id: str
    rule_version: str
    status: str
    reason_code: str
    jurisdiction: str
    effective_from: str
    effective_to: str | None
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self):
        _required(
            self.rule_id,
            self.rule_version,
            self.status,
            self.reason_code,
            self.jurisdiction,
            self.effective_from,
        )
        if self.status not in RULE_APPLICABILITY:
            raise ValueError("UNKNOWN_RULE_APPLICABILITY")
        if not isinstance(self.required_fields, tuple) or not isinstance(self.missing_fields, tuple):
            raise ValueError("RULE_FIELDS_MUST_BE_IMMUTABLE")
        if self.missing_fields and self.status != INSUFFICIENT_EVIDENCE:
            raise ValueError("MISSING_FIELDS_REQUIRE_INSUFFICIENT_STATUS")
        if self.status == INSUFFICIENT_EVIDENCE and not self.missing_fields:
            raise ValueError("INSUFFICIENT_STATUS_REQUIRES_MISSING_FIELDS")
        if not set(self.missing_fields).issubset(set(self.required_fields)):
            raise ValueError("MISSING_FIELDS_MUST_BE_REQUIRED")


@dataclass(frozen=True)
class PolicyConstraint:
    policy_id: str
    policy_version: str
    constraint_id: str
    effect: str
    reason_code: str

    def __post_init__(self):
        _required(
            self.policy_id,
            self.policy_version,
            self.constraint_id,
            self.reason_code,
        )
        if self.effect not in POLICY_EFFECTS:
            raise ValueError("UNKNOWN_POLICY_EFFECT")


@dataclass(frozen=True)
class InterpretationUnit:
    unit_id: str
    property_id: str
    subject: str
    predicate: str
    object_value: str | None
    status: str
    reason_code: str
    applicability: RuleApplicability
    evidence_dispositions: tuple[EvidenceDisposition, ...]
    policy_constraints: tuple[PolicyConstraint, ...] = ()

    def __post_init__(self):
        _required(
            self.unit_id,
            self.property_id,
            self.subject,
            self.predicate,
            self.status,
            self.reason_code,
        )
        if self.status not in UNIT_STATUSES:
            raise ValueError("UNKNOWN_INTERPRETATION_STATUS")
        if self.status == CONCLUDED and (self.object_value is None or not str(self.object_value).strip()):
            raise ValueError("CONCLUDED_VALUE_REQUIRED")
        if self.status != CONCLUDED and self.object_value is not None:
            raise ValueError("NON_CONCLUSION_CANNOT_ASSERT_VALUE")
        if not isinstance(self.evidence_dispositions, tuple) or not isinstance(self.policy_constraints, tuple):
            raise ValueError("INTERPRETATION_COLLECTIONS_MUST_BE_IMMUTABLE")
        if any(item.rule_id != self.applicability.rule_id for item in self.evidence_dispositions):
            raise ValueError("DISPOSITION_RULE_MISMATCH")
        evidence_ids = tuple(item.evidence_id for item in self.evidence_dispositions)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("DUPLICATE_RULE_EVIDENCE_DISPOSITION")
        if self.applicability.status == INSUFFICIENT_EVIDENCE and self.status != INDETERMINATE:
            raise ValueError("INSUFFICIENT_EVIDENCE_CANNOT_CONCLUDE")
        if self.applicability.status == NOT_APPLICABLE and self.status != NOT_APPLICABLE:
            raise ValueError("NON_APPLICABLE_RULE_CANNOT_CONCLUDE")


@dataclass(frozen=True)
class InterpretationResult:
    request: InterpretationRequest
    units: tuple[InterpretationUnit, ...]
    result_status: str
    reason_code: str

    def __post_init__(self):
        _required(self.result_status, self.reason_code)
        if self.result_status not in RESULT_STATUSES:
            raise ValueError("UNKNOWN_INTERPRETATION_RESULT_STATUS")
        if not isinstance(self.units, tuple):
            raise ValueError("INTERPRETATION_UNITS_MUST_BE_IMMUTABLE")
        unit_ids = tuple(item.unit_id for item in self.units)
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("DUPLICATE_INTERPRETATION_UNIT_ID")
        input_ids = {item.evidence_id for item in self.request.evidence}
        for unit in self.units:
            if unit.property_id != self.request.property_id:
                raise ValueError("INTERPRETATION_PROPERTY_MISMATCH")
            disposition_ids = {item.evidence_id for item in unit.evidence_dispositions}
            if disposition_ids != input_ids:
                raise ValueError("INCOMPLETE_EVIDENCE_DISPOSITION_LEDGER")
            for constraint in unit.policy_constraints:
                if (
                    constraint.policy_id != self.request.context.policy_id
                    or constraint.policy_version != self.request.context.policy_version
                ):
                    raise ValueError("POLICY_CONSTRAINT_VERSION_MISMATCH")
