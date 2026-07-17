"""EIA-WIRE-001 trace-preserving EvidenceCandidate -> ECM -> EPM wiring."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from era.canonical import canonical_errors
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.evidence_intelligence.deterministic_parsing import DeterministicArtifactParser
from era.evidence_intelligence.membership import ValidatedArtifactMember
from era.provenance import provenance_errors
from era.provenance.provenance_models import ProvenanceInput


SUCCEEDED = "SUCCEEDED"
FAILED_MEMBERSHIP = "FAILED_MEMBERSHIP"
FAILED_PARSING = "FAILED_PARSING"
FAILED_TRACE = "FAILED_TRACE"
FAILED_MAPPING = "FAILED_MAPPING"
FAILED_SOURCE_CONTEXT = "FAILED_SOURCE_CONTEXT"
FAILED_ECM = "FAILED_ECM"
FAILED_EPM = "FAILED_EPM"
NOT_PROCESSED = "NOT_PROCESSED"
CANDIDATE_OUTCOMES = frozenset({
    SUCCEEDED, FAILED_MEMBERSHIP, FAILED_PARSING, FAILED_TRACE, FAILED_MAPPING,
    FAILED_SOURCE_CONTEXT, FAILED_ECM, FAILED_EPM, NOT_PROCESSED,
})

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
NO_VALID_CANDIDATES = "NO_VALID_CANDIDATES"
AGGREGATE_STATUSES = frozenset({COMPLETE, PARTIAL, FAILED, NO_VALID_CANDIDATES})

EVIDENCE_IDENTITY_VERSION = "1"


@dataclass(frozen=True)
class CandidateFieldMapping:
    field_name: str
    category: EvidenceCategory
    value_type: EvidenceValueType
    units: str | None = None


@dataclass(frozen=True)
class CandidateMappingPolicy:
    policy_id: str
    policy_version: str
    normalization_version: str
    mappings: tuple[CandidateFieldMapping, ...]

    def __post_init__(self):
        if not all((self.policy_id, self.policy_version,
                    self.normalization_version)) or not self.mappings:
            raise ValueError("INVALID_MAPPING_POLICY")
        names = tuple(item.field_name for item in self.mappings)
        if len(names) != len(set(names)):
            raise ValueError("DUPLICATE_FIELD_MAPPING")
        if any(not item.field_name
               or not isinstance(item.category, EvidenceCategory)
               or not isinstance(item.value_type, EvidenceValueType)
               for item in self.mappings):
            raise ValueError("INVALID_FIELD_MAPPING")

    def mapping_for(self, field_name):
        return next((item for item in self.mappings if item.field_name == field_name), None)


@dataclass(frozen=True)
class SourceContext:
    provider_id: str
    canonical_source_id: str
    provider_name: str
    legal_basis: str
    source_reference: str
    connector_version: str
    adapter_version: str
    source_class: EvidenceSourceClass

    def is_complete_for(self, member):
        return (
            self.provider_id == member.provider_id
            and self.canonical_source_id == member.canonical_source_id
            and all((self.provider_name, self.legal_basis, self.source_reference,
                     self.connector_version, self.adapter_version))
            and isinstance(self.source_class, EvidenceSourceClass)
        )


@dataclass(frozen=True)
class IntegrationItem:
    member: ValidatedArtifactMember
    profile: object
    source_context: SourceContext


@dataclass(frozen=True)
class CandidateIntegrationOutcome:
    step_sequence: int
    candidate_id: str
    field_name: str
    outcome: str
    reason: str
    canonical_record: object | None
    provenance_record: object | None


@dataclass(frozen=True)
class EvidenceIntegrationResult:
    status: str
    property_id: str
    mapping_policy_id: str
    mapping_policy_version: str
    outcomes: tuple[CandidateIntegrationOutcome, ...]


class EvidenceIntegrationService:
    """Stateless composition seam. ECM and EPM retain their existing authority."""

    def __init__(self, ecm, epm, parser=None):
        self.ecm = ecm
        self.epm = epm
        self.parser = parser or DeterministicArtifactParser()

    def integrate(self, property_id, items, mapping_policy):
        ordered = tuple(sorted(items, key=lambda item: item.member.step_sequence))
        outcomes = []
        if not property_id:
            return EvidenceIntegrationResult(
                FAILED, property_id, mapping_policy.policy_id,
                mapping_policy.policy_version,
                tuple(self._failure(item, FAILED_MAPPING, "PROPERTY_ID_REQUIRED") for item in ordered),
            )
        sequences = tuple(item.member.step_sequence for item in ordered)
        if len(sequences) != len(set(sequences)):
            return EvidenceIntegrationResult(
                FAILED, property_id, mapping_policy.policy_id,
                mapping_policy.policy_version,
                tuple(self._failure(item, FAILED_MEMBERSHIP, "DUPLICATE_STEP_SEQUENCE") for item in ordered),
            )

        for item in ordered:
            member = item.member
            if not isinstance(member, ValidatedArtifactMember) or not member.is_valid():
                outcomes.append(self._failure(item, FAILED_MEMBERSHIP, "INVALID_VALIDATED_MEMBER"))
                continue
            parsed = self.parser.parse(member, item.profile)
            if not parsed.succeeded:
                reason = ",".join(failure.code for failure in parsed.failures)
                outcomes.append(self._failure(item, FAILED_PARSING, reason))
                continue
            if not parsed.candidates:
                outcomes.append(self._failure(item, NOT_PROCESSED, "NO_CANDIDATES"))
                continue
            for candidate in parsed.candidates:
                if not item.source_context.is_complete_for(member):
                    outcomes.append(self._candidate_failure(
                        member, candidate, FAILED_SOURCE_CONTEXT,
                        "INCOMPLETE_OR_MISMATCHED_SOURCE_CONTEXT",
                    ))
                    continue
                outcomes.append(self._integrate_candidate(
                    property_id, member, item.source_context, mapping_policy, candidate,
                ))

        successes = sum(item.outcome == SUCCEEDED for item in outcomes)
        if not outcomes:
            status = NO_VALID_CANDIDATES
        elif successes == len(outcomes):
            status = COMPLETE
        elif successes:
            status = PARTIAL
        else:
            status = FAILED
        return EvidenceIntegrationResult(
            status, property_id, mapping_policy.policy_id,
            mapping_policy.policy_version, tuple(outcomes),
        )

    def _integrate_candidate(self, property_id, member, context, policy, candidate):
        if candidate.validation_status != "VALID" or not candidate.is_trace_complete():
            return self._candidate_failure(member, candidate, FAILED_TRACE, "INCOMPLETE_CANDIDATE_TRACE")
        trace = candidate.parser_trace
        if (trace.artifact_sha256 != member.artifact_sha256
                or trace.package_id != member.package_id
                or trace.execution_id != member.execution_id
                or trace.canonical_source_id != member.canonical_source_id):
            return self._candidate_failure(member, candidate, FAILED_TRACE, "TRACE_MEMBERSHIP_MISMATCH")
        mapping = policy.mapping_for(candidate.field_name)
        if mapping is None or candidate.proposed_value_type != mapping.value_type.value:
            return self._candidate_failure(member, candidate, FAILED_MAPPING, "UNKNOWN_OR_CONFLICTING_FIELD_MAPPING")

        evidence_id = self._evidence_id(property_id, candidate, member, policy)
        provenance = Provenance(
            connector_id=context.provider_id,
            provider_name=context.provider_name,
            source_name=context.source_reference,
            source_class=context.source_class,
            retrieved_at=member.artifact.retrieved_at,
            legal_basis=context.legal_basis,
            normalization_version=policy.normalization_version,
            audit_reference=candidate.candidate_id,
        )
        record = CanonicalEvidenceRecord(
            evidence_id=evidence_id, property_id=property_id,
            category=mapping.category, field_name=candidate.field_name,
            raw_value=candidate.original_lexical_value,
            normalized_value=candidate.parsed_value, units=mapping.units,
            provenance=provenance, value_type=mapping.value_type,
            created_at=member.artifact.retrieved_at,
        )
        ecm_status, canonical = self.ecm.normalize_record(record)
        if ecm_status != canonical_errors.PASS or canonical is None:
            return self._candidate_failure(member, candidate, FAILED_ECM, ecm_status)

        identity = member.artifact_identity
        epm_input = ProvenanceInput(
            evidence_id=canonical.evidence_id, property_id=canonical.property_id,
            canonical_field=canonical.field_name,
            canonical_value=canonical.normalized_value,
            original_value=canonical.raw_value,
            provider_id=context.provider_id, provider_name=context.provider_name,
            legal_basis=context.legal_basis,
            source_reference=context.source_reference,
            retrieved_at=member.artifact.retrieved_at,
            connector_version=context.connector_version,
            adapter_version=context.adapter_version,
            normalization_version=policy.normalization_version,
            artifact_sha256=trace.artifact_sha256,
            package_id=trace.package_id, execution_id=trace.execution_id,
            canonical_source_id=trace.canonical_source_id,
            parser_id=trace.parser_id, parser_version=trace.parser_version,
            schema_profile_id=trace.schema_profile_id,
            schema_profile_version=trace.schema_profile_version,
            source_location=trace.source_location,
            trace_contract_version=trace.trace_contract_version,
            candidate_id=candidate.candidate_id,
            candidate_validation_status=candidate.validation_status,
            artifact_algorithm=identity.algorithm, artifact_digest=identity.digest,
            artifact_byte_length=identity.byte_length,
            artifact_media_type=identity.media_type,
            artifact_content_uri=identity.content_uri,
            original_lexical_value=candidate.original_lexical_value,
            parsed_value=candidate.parsed_value,
            proposed_value_type=candidate.proposed_value_type,
        )
        epm_status, epm_record = self.epm.register_evidence(epm_input)
        if epm_status != provenance_errors.PASS or epm_record is None:
            return self._candidate_failure(member, candidate, FAILED_EPM, epm_status)
        if not self._trace_survived(epm_input, epm_record):
            return self._candidate_failure(member, candidate, FAILED_EPM, "TRACE_RETENTION_MISMATCH")
        return CandidateIntegrationOutcome(
            member.step_sequence, candidate.candidate_id, candidate.field_name,
            SUCCEEDED, "", canonical, epm_record,
        )

    @staticmethod
    def _evidence_id(property_id, candidate, member, policy):
        material = json.dumps({
            "identity_version": EVIDENCE_IDENTITY_VERSION,
            "property_id": property_id, "candidate_id": candidate.candidate_id,
            "canonical_source_id": member.canonical_source_id,
            "mapping_policy_version": policy.policy_version,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "EV-" + hashlib.sha256(material).hexdigest()

    @staticmethod
    def _trace_survived(submitted, returned):
        fields = (
            "artifact_sha256", "package_id", "execution_id", "canonical_source_id",
            "parser_id", "parser_version", "schema_profile_id",
            "schema_profile_version", "source_location", "trace_contract_version",
            "candidate_id", "candidate_validation_status", "artifact_algorithm",
            "artifact_digest", "artifact_byte_length", "artifact_media_type",
            "artifact_content_uri", "original_lexical_value", "parsed_value",
            "proposed_value_type",
        )
        return all(
            getattr(returned, field) == getattr(submitted, field)
            and (field == "artifact_byte_length" or bool(getattr(submitted, field)))
            for field in fields
        )

    @staticmethod
    def _failure(item, outcome, reason):
        return CandidateIntegrationOutcome(
            getattr(item.member, "step_sequence", 0), "", "", outcome,
            reason, None, None,
        )

    @staticmethod
    def _candidate_failure(member, candidate, outcome, reason):
        return CandidateIntegrationOutcome(
            member.step_sequence, candidate.candidate_id, candidate.field_name,
            outcome, reason, None, None,
        )
