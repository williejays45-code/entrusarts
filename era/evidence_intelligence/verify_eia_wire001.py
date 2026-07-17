"""EIA-WIRE-001 grouped evidence-integration verification."""

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
from types import SimpleNamespace

from era.acquisition_execution.executor import RawArtifact
from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.discovery.acquisition_package import (
    COMPLETE, INVALID, VALID, PackagedAcquisitionStep, ValidatedAcquisitionPackage,
)
from era.evidence_intelligence.contracts import EvidenceCandidate, ParserTrace
from era.evidence_intelligence.deterministic_parsing import ParseResult
from era.evidence_intelligence.integration import (
    COMPLETE as INTEGRATION_COMPLETE, FAILED, PARTIAL,
    FAILED_ECM, FAILED_EPM, FAILED_MAPPING, FAILED_MEMBERSHIP,
    FAILED_PARSING, FAILED_SOURCE_CONTEXT, FAILED_TRACE, SUCCEEDED,
    CandidateFieldMapping, CandidateMappingPolicy, EvidenceIntegrationService,
    IntegrationItem, SourceContext,
)
from era.evidence_intelligence.membership import (
    ArtifactIdentity, ValidatedArtifactMember, validated_members,
)
from era.evidence_intelligence.parser_profile import EvidenceSchemaProfile, ParserFieldRule
from era.provenance.provenance_manager import EvidenceProvenanceManager
from era.provenance import provenance_errors


SOURCE = "src:tx-dallas:dcad:appraisal_district:parcel_record"


def package(raw=b"PARCEL,VALUE\r\n001,250000\r\n", provider="DCAD", source=SOURCE,
            sequence=1, valid=True, suffix="1"):
    artifact = RawArtifact(
        raw, "text/csv", hashlib.sha256(raw).hexdigest(), source, provider,
        f"KEY-{suffix}", "2026-07-13T05:00:00+00:00", (),
    )
    step = PackagedAcquisitionStep(
        f"PLAN-{suffix}:{sequence}", sequence, source, provider, "SUCCEEDED",
        VALID if valid else INVALID, () if valid else ("INVALID",), (),
        artifact if valid else None,
    )
    package_id = hashlib.sha256(f"PKG:{suffix}:{provider}:{source}".encode()).hexdigest()
    return ValidatedAcquisitionPackage(
        COMPLETE, f"PLAN-{suffix}", f"EXEC-{suffix}", "POLICY-1", "CATALOG-1",
        (step,), 1 if valid else 0, valid, "coverage", package_id, "1",
    )


def profile():
    return EvidenceSchemaProfile(
        "DCAD-CSV", "1", "text/csv", "columns:PARCEL,VALUE", "CSV", "1",
        (
            ParserFieldRule("column:PARCEL", "parcel_id", "PRESERVE_TEXT", True),
            ParserFieldRule("column:VALUE", "total_appraised_value", "INTEGER", True),
        ),
        ("MALFORMED_BYTES", "UNKNOWN_SCHEMA", "MISSING_REQUIRED_FIELD"),
        (("CSV", "1"),),
    )


def policy(include_value=True):
    mappings = [CandidateFieldMapping(
        "parcel_id", EvidenceCategory.PARCEL, EvidenceValueType.TEXT,
    )]
    if include_value:
        mappings.append(CandidateFieldMapping(
            "total_appraised_value", EvidenceCategory.MARKET, EvidenceValueType.INTEGER,
        ))
    return CandidateMappingPolicy("EIA-FIELD-POLICY", "1", "ECM-1.0", tuple(mappings))


def context(member, **overrides):
    data = dict(
        provider_id=member.provider_id,
        canonical_source_id=member.canonical_source_id,
        provider_name="Dallas Central Appraisal District",
        legal_basis="PUBLIC_RECORD",
        source_reference="DCAD-DATA-PRODUCTS",
        connector_version="1",
        adapter_version="1",
        source_class=EvidenceSourceClass.PUBLIC_RECORD,
    )
    data.update(overrides)
    return SourceContext(**data)


def item(p=None):
    p = p or package()
    member = validated_members(p)[0]
    return IntegrationItem(member, profile(), context(member))


class FailingEPM:
    def __init__(self):
        self.calls = 0

    def register_evidence(self, value):
        self.calls += 1
        return provenance_errors.PERSISTENCE_WRITE_FAILED, None


class IncompleteTraceParser:
    def parse(self, member, parser_profile):
        trace = ParserTrace(
            member.artifact_sha256, member.package_id, member.execution_id,
            member.canonical_source_id, "", "1", "DCAD-CSV", "1", "row:1/column:PARCEL",
        )
        return ParseResult((EvidenceCandidate(
            "CAND-BAD", "parcel_id", "001", "001", "TEXT", trace, "VALID",
        ),), ())


def run_checks():
    primary_item = item()
    service = EvidenceIntegrationService(CanonicalEvidenceModel(), EvidenceProvenanceManager())
    result = service.integrate("PROP-1", (primary_item,), policy())
    successful = tuple(outcome for outcome in result.outcomes if outcome.outcome == SUCCEEDED)
    first = successful[0]
    record = first.provenance_record
    canonical = first.canonical_record

    replay = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (primary_item,), policy())

    invalid_package = package(valid=False, suffix="invalid")
    try:
        ValidatedArtifactMember.from_package(invalid_package, invalid_package.steps[0])
        invalid_rejected = False
    except ValueError:
        invalid_rejected = True
    try:
        ValidatedArtifactMember("x", "1", "e", "s", 1, "h", "p", "c", VALID, object(), object())
        loose_rejected = False
    except TypeError:
        loose_rejected = True

    missing_mapping = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (primary_item,), policy(include_value=False))
    bad_context_item = IntegrationItem(
        primary_item.member, primary_item.profile,
        context(primary_item.member, provider_name=""),
    )
    bad_context = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (bad_context_item,), policy())
    incomplete_trace = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(), IncompleteTraceParser(),
    ).integrate("PROP-1", (primary_item,), policy())

    malformed_item = item(package(b"WRONG\r\nvalue\r\n", suffix="malformed"))
    parse_failure = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (malformed_item,), policy())

    ecm_failure_item = item(package(b"PARCEL,VALUE\r\n0.95,250000\r\n", suffix="ecm"))
    ecm_failure = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (ecm_failure_item,), policy())

    failing_epm = FailingEPM()
    epm_failure = EvidenceIntegrationService(
        CanonicalEvidenceModel(), failing_epm,
    ).integrate("PROP-1", (primary_item,), policy())

    second_package = package(
        provider="OTHER", source="src:tx-dallas:other:public:parcel_record",
        sequence=2, suffix="2",
    )
    second_member = validated_members(second_package)[0]
    second_item = IntegrationItem(second_member, profile(), context(
        second_member, provider_name="Other Public Provider",
        source_reference="OTHER-SOURCE",
    ))
    partial = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (bad_context_item, second_item), policy())

    collision = EvidenceIntegrationService(
        CanonicalEvidenceModel(), EvidenceProvenanceManager(),
    ).integrate("PROP-1", (primary_item, second_item), policy())
    parcel_ids = tuple(
        outcome.canonical_record.evidence_id for outcome in collision.outcomes
        if outcome.outcome == SUCCEEDED and outcome.field_name == "parcel_id"
    )

    try:
        CandidateMappingPolicy(
            "DUP", "1", "ECM-1", (
                CandidateFieldMapping("parcel_id", EvidenceCategory.PARCEL, EvidenceValueType.TEXT),
                CandidateFieldMapping("parcel_id", EvidenceCategory.IDENTITY, EvidenceValueType.TEXT),
            ),
        )
        duplicate_mapping_rejected = False
    except ValueError:
        duplicate_mapping_rejected = True

    trace_fields = (
        "candidate_id", "candidate_validation_status", "artifact_sha256",
        "package_id", "execution_id", "canonical_source_id", "parser_id",
        "parser_version", "schema_profile_id", "schema_profile_version",
        "source_location", "original_lexical_value", "parsed_value",
        "proposed_value_type", "artifact_algorithm", "artifact_digest",
        "artifact_byte_length", "artifact_media_type", "artifact_content_uri",
    )

    checks = {
        # Membership
        "membership_factory_required": loose_rejected,
        "invalid_package_step_rejected": invalid_rejected,
        "valid_member_bound_to_package": primary_item.member.is_valid(),
        "member_identity_agrees": primary_item.member.artifact_sha256 == primary_item.member.artifact.sha256,
        # Identity
        "artifact_identity_valid": primary_item.member.artifact_identity.is_valid(),
        "content_uri_is_identity_not_locator": primary_item.member.artifact_identity.content_uri.startswith("era-artifact:sha256:"),
        "evidence_id_deterministic": tuple(o.candidate_id for o in result.outcomes) == tuple(o.candidate_id for o in replay.outcomes),
        "canonical_identity_replayable": tuple(o.canonical_record.evidence_id for o in successful) == tuple(o.canonical_record.evidence_id for o in replay.outcomes),
        "provider_collision_safe": len(parcel_ids) == 2 and len(set(parcel_ids)) == 2,
        "timestamp_captured_not_current": canonical.created_at == primary_item.member.artifact.retrieved_at,
        # Mapping
        "closed_mapping_succeeds": result.status == INTEGRATION_COMPLETE and len(successful) == 2,
        "unknown_mapping_fails": any(o.outcome == FAILED_MAPPING for o in missing_mapping.outcomes),
        "duplicate_mapping_fails": duplicate_mapping_rejected,
        "types_match_policy": {o.field_name: o.canonical_record.value_type for o in successful} == {"parcel_id": EvidenceValueType.TEXT, "total_appraised_value": EvidenceValueType.INTEGER},
        # Trace
        "trace_survives_epm": all(getattr(record, field) not in (None, "") for field in trace_fields),
        "candidate_link_survives": record.candidate_id == first.candidate_id and record.candidate_validation_status == "VALID",
        "artifact_identity_survives": record.artifact_digest == primary_item.member.artifact_sha256 and record.artifact_content_uri == primary_item.member.artifact_identity.content_uri,
        "lexical_parsed_type_survive": record.original_lexical_value == "001" and record.parsed_value == "001" and record.proposed_value_type == "TEXT",
        "incomplete_trace_fails": incomplete_trace.outcomes[0].outcome == FAILED_TRACE,
        # Source context
        "source_context_survives": record.provider_name == "Dallas Central Appraisal District" and record.source_reference == "DCAD-DATA-PRODUCTS",
        "missing_context_fails": bad_context.outcomes[0].outcome == FAILED_SOURCE_CONTEXT,
        # Transaction
        "ecm_failure_not_accepted": ecm_failure.outcomes[0].outcome == FAILED_ECM and ecm_failure.outcomes[0].canonical_record is None,
        "epm_failure_not_accepted": epm_failure.outcomes[0].outcome == FAILED_EPM and epm_failure.outcomes[0].canonical_record is None,
        "epm_called_once_per_candidate": failing_epm.calls == 2,
        "semantic_hash_replayable": tuple(o.provenance_record.evidence_hash for o in successful) == tuple(o.provenance_record.evidence_hash for o in replay.outcomes),
        # Transparency
        "parse_failure_visible": parse_failure.status == FAILED and parse_failure.outcomes[0].outcome == FAILED_PARSING,
        "partial_status_explicit": partial.status == PARTIAL,
        "partial_exposes_all_outcomes": len(partial.outcomes) == 4 and sum(o.outcome == FAILED_SOURCE_CONTEXT for o in partial.outcomes) == 2,
        "result_immutable": _frozen(result),
        "candidate_order_deterministic": tuple(o.field_name for o in successful) == ("parcel_id", "total_appraised_value"),
        # Boundary
        "container_composition_seam": "self.evidence_integration = EvidenceIntegrationService(self.ecm, self.epm)" in (Path(__file__).parents[1] / "container.py").read_text(encoding="utf-8"),
        "no_storage_or_reasoning": _boundary_scan(),
        "historical_replay_not_claimed": not hasattr(primary_item.member.artifact_identity, "resolve"),
    }
    return checks


def _frozen(value):
    try:
        value.status = "CHANGED"
        return False
    except FrozenInstanceError:
        return True


def _boundary_scan():
    source = (Path(__file__).parent / "integration.py").read_text(encoding="utf-8").lower()
    prohibited = ("sqlite", "object_storage", "confidence", "ranking", "reasoning", "decisionengine")
    return all(term not in source for term in prohibited)


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"EIA-WIRE-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
