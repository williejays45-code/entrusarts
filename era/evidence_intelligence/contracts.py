"""EIL-CONTRACT-001 immutable candidate and parser-trace contracts."""

from dataclasses import dataclass


TRACE_CONTRACT_VERSION = "1"
REQUIRED_TRACE_FIELDS = (
    "artifact_sha256", "package_id", "execution_id", "canonical_source_id",
    "parser_id", "parser_version", "schema_profile_id",
    "schema_profile_version", "source_location",
)

# Closed, reviewable disposition: no field can silently fall outside ECM/EPM/audit.
TRACE_DISPOSITION = tuple(
    (field, ("ECM", "EPM", "AUDIT")) for field in REQUIRED_TRACE_FIELDS
)


@dataclass(frozen=True)
class ParserTrace:
    artifact_sha256: str
    package_id: str
    execution_id: str
    canonical_source_id: str
    parser_id: str
    parser_version: str
    schema_profile_id: str
    schema_profile_version: str
    source_location: str
    trace_contract_version: str = TRACE_CONTRACT_VERSION

    def is_complete(self) -> bool:
        return all(getattr(self, field) for field in REQUIRED_TRACE_FIELDS)


@dataclass(frozen=True)
class EvidenceCandidate:
    candidate_id: str
    field_name: str
    original_lexical_value: str
    parsed_value: str
    proposed_value_type: str
    parser_trace: ParserTrace
    validation_status: str = "VALID"

    def is_trace_complete(self) -> bool:
        return self.parser_trace.is_complete()
