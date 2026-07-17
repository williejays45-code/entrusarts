"""RIL-WIRE-001 trace-preserving EIA-to-RIL composition seam."""

from __future__ import annotations

from dataclasses import dataclass

from era.evidence_intelligence.integration import (
    COMPLETE as EIA_COMPLETE,
    PARTIAL as EIA_PARTIAL,
    SUCCEEDED,
    EvidenceIntegrationResult,
)
from era.reasoning.contracts import (
    COMPLETE as RIL_COMPLETE,
    InterpretationRequest,
    InterpretationResult,
)
from era.reasoning.certification import (
    PolicyCertificationProjection,
    RuleCertificationProjection,
)
from era.reasoning.field_predicate import FieldPredicateInterpreter


COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
COMPOSITION_STATUSES = frozenset({COMPLETE, PARTIAL, FAILED})


@dataclass(frozen=True)
class EvidenceInterpretationCompositionResult:
    status: str
    reason_code: str
    integration_result: EvidenceIntegrationResult
    interpretation_result: InterpretationResult | None
    rule_certification: RuleCertificationProjection | None = None
    policy_certification: PolicyCertificationProjection | None = None

    def __post_init__(self):
        if self.status not in COMPOSITION_STATUSES:
            raise ValueError("UNKNOWN_COMPOSITION_STATUS")
        if not self.reason_code:
            raise ValueError("COMPOSITION_REASON_REQUIRED")
        if not isinstance(self.integration_result, EvidenceIntegrationResult):
            raise TypeError("EIA_INTEGRATION_RESULT_REQUIRED")
        if self.interpretation_result is not None and not isinstance(
            self.interpretation_result, InterpretationResult
        ):
            raise TypeError("RIL_INTERPRETATION_RESULT_REQUIRED")
        if self.status == COMPLETE and self.interpretation_result is None:
            raise ValueError("COMPLETE_COMPOSITION_REQUIRES_INTERPRETATION")
        if self.status == COMPLETE and (
            self.rule_certification is None or self.policy_certification is None
        ):
            raise ValueError("COMPLETE_COMPOSITION_REQUIRES_CERTIFICATION")


class EvidenceInterpretationCompositionService:
    """Select successful EIA pairs and invoke the supplied RIL evaluator once."""

    def __init__(
        self, interpreter=None, *, trusted_rule_certifications=(),
        trusted_policy_certifications=(),
    ):
        self.interpreter = interpreter or FieldPredicateInterpreter()
        if not isinstance(trusted_rule_certifications, tuple) or not all(
            isinstance(item, RuleCertificationProjection)
            for item in trusted_rule_certifications
        ):
            raise TypeError("IMMUTABLE_TRUSTED_RULE_CERTIFICATIONS_REQUIRED")
        if not isinstance(trusted_policy_certifications, tuple) or not all(
            isinstance(item, PolicyCertificationProjection)
            for item in trusted_policy_certifications
        ):
            raise TypeError("IMMUTABLE_TRUSTED_POLICY_CERTIFICATIONS_REQUIRED")
        self._trusted_rule_digests = frozenset(
            item.projection_digest for item in trusted_rule_certifications
        )
        self._trusted_policy_digests = frozenset(
            item.projection_digest for item in trusted_policy_certifications
        )

    def compose(
        self,
        integration_result: EvidenceIntegrationResult,
        rules,
        policy_constraints,
        context,
        *,
        operation_id: str,
        observed_at: str,
        max_rules: int,
        max_evidence: int,
        rule_certification: RuleCertificationProjection | None = None,
        policy_certification: PolicyCertificationProjection | None = None,
    ) -> EvidenceInterpretationCompositionResult:
        if not isinstance(integration_result, EvidenceIntegrationResult):
            raise TypeError("EIA_INTEGRATION_RESULT_REQUIRED")

        certification_failure = self._certification_failure(
            rules, policy_constraints, context,
            rule_certification, policy_certification,
        )
        if certification_failure:
            return self._result(
                FAILED, certification_failure, integration_result, None,
                rule_certification, policy_certification,
            )

        successful = tuple(
            outcome for outcome in integration_result.outcomes
            if outcome.outcome == SUCCEEDED
        )
        unsuccessful = tuple(
            outcome for outcome in integration_result.outcomes
            if outcome.outcome != SUCCEEDED
        )
        if not successful:
            return self._result(
                FAILED, "NO_SUCCESSFUL_EVIDENCE", integration_result, None,
                rule_certification, policy_certification,
            )
        if integration_result.status not in {EIA_COMPLETE, EIA_PARTIAL}:
            return self._result(
                FAILED, "INCONSISTENT_EIA_STATUS", integration_result, None,
                rule_certification, policy_certification,
            )
        if integration_result.status == EIA_COMPLETE and unsuccessful:
            return self._result(
                FAILED, "INCONSISTENT_EIA_COMPLETE_STATUS", integration_result, None,
                rule_certification, policy_certification,
            )
        if any(
            outcome.canonical_record is None or outcome.provenance_record is None
            for outcome in successful
        ):
            return self._result(
                FAILED, "INCOMPLETE_SUCCESSFUL_EIA_OUTCOME", integration_result, None,
                rule_certification, policy_certification,
            )

        ordered = tuple(sorted(
            successful,
            key=lambda outcome: outcome.canonical_record.evidence_id,
        ))
        try:
            request = InterpretationRequest(
                operation_id=operation_id,
                property_id=integration_result.property_id,
                evidence=tuple(outcome.canonical_record for outcome in ordered),
                provenance=tuple(outcome.provenance_record for outcome in ordered),
                context=context,
                observed_at=observed_at,
            )
            interpretation = self.interpreter.evaluate(
                request,
                rules,
                policy_constraints,
                max_rules=max_rules,
                max_evidence=max_evidence,
            )
        except (TypeError, ValueError):
            return self._result(
                FAILED, "INTERPRETATION_INPUT_REJECTED", integration_result, None,
                rule_certification, policy_certification,
            )

        if integration_result.status == EIA_COMPLETE and interpretation.result_status == RIL_COMPLETE:
            return self._result(
                COMPLETE, "EVIDENCE_INTERPRETATION_COMPLETE",
                integration_result, interpretation,
                rule_certification, policy_certification,
            )
        return self._result(
            PARTIAL, "UPSTREAM_OR_INTERPRETATION_PARTIAL",
            integration_result, interpretation,
            rule_certification, policy_certification,
        )

    def _certification_failure(
        self, rules, policy_constraints, context,
        rule_certification, policy_certification,
    ):
        if not isinstance(rule_certification, RuleCertificationProjection):
            return "RULE_CERTIFICATION_REQUIRED"
        if rule_certification.projection_digest not in self._trusted_rule_digests:
            return "RULE_CERTIFICATION_UNTRUSTED"
        if not rule_certification.authorizes(rules):
            return "RULE_CERTIFICATION_MISMATCH"
        if not isinstance(policy_certification, PolicyCertificationProjection):
            return "POLICY_CERTIFICATION_REQUIRED"
        if policy_certification.projection_digest not in self._trusted_policy_digests:
            return "POLICY_CERTIFICATION_UNTRUSTED"
        if not policy_certification.authorizes(policy_constraints, context):
            return "POLICY_CERTIFICATION_MISMATCH"
        return None

    @staticmethod
    def _result(
        status, reason, integration_result, interpretation_result,
        rule_certification, policy_certification,
    ):
        return EvidenceInterpretationCompositionResult(
            status, reason, integration_result, interpretation_result,
            rule_certification, policy_certification,
        )
