"""RIL contracts. Reasoning implementation is intentionally not present."""

from era.reasoning.contracts import (
    APPLICABLE,
    INSUFFICIENT_EVIDENCE,
    IRRELEVANT,
    NOT_APPLICABLE,
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
from era.reasoning.field_predicate import (
    EQUALS, EXISTS, IN_DECLARED_SET, NOT_EQUALS,
    FieldPredicateInterpreter, FieldPredicateRule,
)
from era.reasoning.composition import (
    EvidenceInterpretationCompositionResult,
    EvidenceInterpretationCompositionService,
)
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

__all__ = (
    "APPLICABLE",
    "INSUFFICIENT_EVIDENCE",
    "IRRELEVANT",
    "NOT_APPLICABLE",
    "OPPOSES",
    "SUPPORTS",
    "ApprovedContextValue",
    "EvidenceDisposition",
    "InterpretationContext",
    "InterpretationRequest",
    "InterpretationResult",
    "InterpretationUnit",
    "PolicyConstraint",
    "RuleApplicability",
    "EQUALS",
    "EXISTS",
    "IN_DECLARED_SET",
    "NOT_EQUALS",
    "FieldPredicateInterpreter",
    "FieldPredicateRule",
    "EvidenceInterpretationCompositionResult",
    "EvidenceInterpretationCompositionService",
    "PolicyCertificationProjection",
    "RuleCertificationProjection",
    "policy_constraint_fingerprint",
    "rule_fingerprint",
    "PROPERTY_INTERPRETATION_POLICY",
    "PROPERTY_PARCEL_IDENTIFIER_PRESENT",
    "PROPERTY_POLICY_CERTIFICATION",
    "PROPERTY_RULE_CERTIFICATION",
)
