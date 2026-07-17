"""Explicit certified RIL rule profiles. This module is not a registry."""

from datetime import date

from era.canonical.canonical_enums import EvidenceValueType
from era.reasoning.certification import (
    PolicyCertificationProjection,
    RuleCertificationProjection,
)
from era.reasoning.contracts import ALLOWED, PolicyConstraint
from era.reasoning.field_predicate import EXISTS, FieldPredicateRule


# RIL-WIRE-001 first certified atomic real-estate rule. The live EIA mapping
# owns parcel_id as TEXT; this profile consumes that verified type unchanged.
PROPERTY_PARCEL_IDENTIFIER_PRESENT = FieldPredicateRule(
    rule_id="PROPERTY_PARCEL_IDENTIFIER_PRESENT",
    rule_version="1",
    jurisdiction="TX-DALLAS",
    effective_from=date(2026, 1, 1),
    effective_to=None,
    required_canonical_field="parcel_id",
    required_ecm_value_type=EvidenceValueType.TEXT,
    comparison_operator=EXISTS,
    expected_value=None,
)


PROPERTY_INTERPRETATION_POLICY = (PolicyConstraint(
    "RIL-POLICY", "1", "INTERPRET_PUBLIC_RECORD",
    ALLOWED, "APPROVED_PUBLIC_RECORD_INTERPRETATION",
),)


# Immutable certification inventory used as Container trust anchors. These
# projections are operation-local inputs, not a mutable registry or store.
PROPERTY_RULE_CERTIFICATION = RuleCertificationProjection.issue(
    "ERA-RULE-CERT-PROPERTY-1", "1", "ERA_ARCHITECTURE_REFERENCE",
    (PROPERTY_PARCEL_IDENTIFIER_PRESENT,),
)
PROPERTY_POLICY_CERTIFICATION = PolicyCertificationProjection.issue(
    "ERA-POLICY-CERT-PROPERTY-1", "1", "ERA_ARCHITECTURE_REFERENCE",
    "RIL-POLICY", "1", PROPERTY_INTERPRETATION_POLICY,
)
