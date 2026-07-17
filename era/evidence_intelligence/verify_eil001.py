"""EIL-001 focused deterministic parsing and boundary verification."""

from dataclasses import FrozenInstanceError
import hashlib
import io
import json
from pathlib import Path
import zipfile

from era.acquisition_execution.executor import RawArtifact
from era.evidence_intelligence.deterministic_parsing import (
    AMBIGUOUS_FIELD_LOCATION, INCOMPATIBLE_PROFILE, INVALID_LEXICAL_VALUE,
    MALFORMED_BYTES, MISSING_REQUIRED_FIELD, PDF_NOT_SUPPORTED,
    UNKNOWN_SCHEMA, UNSUPPORTED_MEDIA_TYPE, DeterministicArtifactParser,
)
from era.evidence_intelligence.parser_profile import EvidenceSchemaProfile, ParserFieldRule
from era.evidence_intelligence.membership import ValidatedArtifactMember
from era.discovery.acquisition_package import (
    COMPLETE, VALID, PackagedAcquisitionStep, ValidatedAcquisitionPackage,
)


def artifact(raw, media, source="src:tx-dallas:dcad:bulk:parcel"):
    return RawArtifact(
        raw, media, hashlib.sha256(raw).hexdigest(), source, "DCAD", "KEY-1",
        "2026-07-13T04:00:00+00:00", (),
    )


def member(item):
    step = PackagedAcquisitionStep(
        "PLAN-1:1", 1, item.canonical_source_id, item.provider_id,
        "SUCCEEDED", VALID, (), (), item,
    )
    package = ValidatedAcquisitionPackage(
        COMPLETE, "PLAN-1", "EXEC-1", "POLICY-1", "CATALOG-1",
        (step,), 1, True, "1/1", "a" * 64, "1",
    )
    return ValidatedArtifactMember.from_package(package, step)


def profile(parser_id, media, signature, rules, version="1"):
    return EvidenceSchemaProfile(
        f"{parser_id}-PROFILE", "1", media, signature, parser_id, version,
        tuple(rules),
        ("MALFORMED_BYTES", "UNKNOWN_SCHEMA", "MISSING_REQUIRED_FIELD"),
        ((parser_id, version),),
    )


def zip_bytes(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in members:
            archive.writestr(name, content)
    return stream.getvalue()


def run_checks():
    parser = DeterministicArtifactParser()
    csv_profile = profile("CSV", "text/csv", "columns:PARCEL,VALUE", (
        ParserFieldRule("column:PARCEL", "parcel_id", "PRESERVE_TEXT", True),
        ParserFieldRule("column:VALUE", "appraised_value", "INTEGER", True),
    ))
    csv_artifact = artifact(b"PARCEL,VALUE\r\n001,250000\r\n", "text/csv")
    csv_result = parser.parse(member(csv_artifact), csv_profile)
    csv_replay = parser.parse(member(csv_artifact), csv_profile)

    json_profile = profile("JSON", "application/json", "keys:owner,parcel", (
        ParserFieldRule("json:/owner/name", "owner_name", "TRIM_TEXT", True),
        ParserFieldRule("json:/parcel", "parcel_id", "PRESERVE_TEXT", True),
    ))
    json_result = parser.parse(
        member(artifact(b'{"owner":{"name":" Smith "},"parcel":"001"}', "application/json")),
        json_profile,
    )

    zip_profile = profile("ZIP", "application/zip", "members:ACCOUNT.CSV,README.txt", (
        ParserFieldRule("member:ACCOUNT.CSV", "account_member", "PRESERVE_TEXT", True),
    ))
    zip_result = parser.parse(
        member(artifact(zip_bytes((("README.txt", "x"), ("ACCOUNT.CSV", "a,b"))), "application/zip")),
        zip_profile,
    )

    mdb_profile = profile("MDB_DERIVED", "application/vnd.era.mdb-rows+json", "columns:ACCOUNT,VALUE", (
        ParserFieldRule("column:ACCOUNT", "account_id", "PRESERVE_TEXT", True),
        ParserFieldRule("column:VALUE", "market_value", "DECIMAL", True),
    ))
    mdb_raw = json.dumps({"schema": ["ACCOUNT", "VALUE"], "rows": [{"ACCOUNT": "A-1", "VALUE": "10.50"}]}, separators=(",", ":")).encode()
    mdb_result = parser.parse(member(artifact(mdb_raw, "application/vnd.era.mdb-rows+json")), mdb_profile)

    missing = parser.parse(member(artifact(b"PARCEL,VALUE\r\n,1\r\n", "text/csv")), csv_profile)
    bad_schema = parser.parse(member(artifact(b"VALUE,PARCEL\r\n1,001\r\n", "text/csv")), csv_profile)
    bad_integer = parser.parse(member(artifact(b"PARCEL,VALUE\r\n001,1.0\r\n", "text/csv")), csv_profile)
    bad_json = parser.parse(member(artifact(b"{", "application/json")), json_profile)
    pdf = parser.parse(member(artifact(b"%PDF", "application/pdf")), json_profile)
    media = parser.parse(member(artifact(b"{}", "text/plain")), json_profile)
    incompatible = profile("CSV", "text/csv", "columns:PARCEL,VALUE", csv_profile.field_rules, "2")
    incompatible = EvidenceSchemaProfile(*incompatible.__dict__.values())
    # Explicitly break the compatibility declaration without changing parser identity.
    incompatible = EvidenceSchemaProfile(
        incompatible.profile_id, incompatible.profile_version, incompatible.supported_media_type,
        incompatible.required_schema_or_signature, incompatible.parser_id, incompatible.parser_version,
        incompatible.field_rules, incompatible.parse_failure_codes, (("CSV", "1"),),
    )
    incompatible_result = parser.parse(member(csv_artifact), incompatible)
    ambiguous_profile = profile("CSV", "text/csv", "columns:PARCEL,VALUE", (
        ParserFieldRule("column:PARCEL", "parcel_id", "PRESERVE_TEXT", True),
        ParserFieldRule("column:PARCEL", "parcel_copy", "PRESERVE_TEXT", True),
    ))
    ambiguous = parser.parse(member(csv_artifact), ambiguous_profile)

    checks = {
        "csv_supported": csv_result.succeeded and len(csv_result.candidates) == 2,
        "json_supported": json_result.succeeded and {
            c.field_name: c.parsed_value for c in json_result.candidates
        } == {"owner_name": "Smith", "parcel_id": "001"},
        "zip_inspection_supported": zip_result.succeeded and zip_result.candidates[0].parser_trace.source_location == "zip:/ACCOUNT.CSV",
        "zip_does_not_parse_member_content": zip_result.candidates[0].original_lexical_value == "ACCOUNT.CSV",
        "mdb_derived_supported": mdb_result.succeeded and len(mdb_result.candidates) == 2,
        "candidate_immutable": _is_frozen(csv_result.candidates[0]),
        "trace_complete": all(c.is_trace_complete() for c in csv_result.candidates + json_result.candidates + zip_result.candidates + mdb_result.candidates),
        "artifact_sha_survives": all(c.parser_trace.artifact_sha256 == csv_artifact.sha256 for c in csv_result.candidates),
        "package_execution_survive": all(c.parser_trace.package_id == "a" * 64 and c.parser_trace.execution_id == "EXEC-1" for c in csv_result.candidates),
        "profile_versions_survive": all(c.parser_trace.schema_profile_id == "CSV-PROFILE" and c.parser_trace.schema_profile_version == "1" for c in csv_result.candidates),
        "source_locations_exact": tuple(c.parser_trace.source_location for c in csv_result.candidates) == ("row:1/column:PARCEL", "row:1/column:VALUE"),
        "original_lexical_preserved": csv_result.candidates[0].original_lexical_value == "001",
        "explicit_types_only": tuple(c.proposed_value_type for c in csv_result.candidates) == ("TEXT", "INTEGER"),
        "validation_explicit": all(c.validation_status == "VALID" for c in csv_result.candidates),
        "replay_semantic_output": csv_result == csv_replay,
        "candidate_ids_sha256": all(len(c.candidate_id) == 64 for c in csv_result.candidates),
        "missing_required_fails_closed": _code(missing) == MISSING_REQUIRED_FIELD,
        "unknown_schema_fails_closed": _code(bad_schema) == UNKNOWN_SCHEMA,
        "silent_coercion_rejected": _code(bad_integer) == INVALID_LEXICAL_VALUE,
        "malformed_bytes_fail_closed": _code(bad_json) == MALFORMED_BYTES,
        "pdf_fails_closed": _code(pdf) == PDF_NOT_SUPPORTED,
        "unsupported_media_fails_closed": _code(media) == UNSUPPORTED_MEDIA_TYPE,
        "incompatible_profile_fails_closed": _code(incompatible_result) == INCOMPATIBLE_PROFILE,
        "ambiguous_profile_fails_closed": _code(ambiguous) == AMBIGUOUS_FIELD_LOCATION,
        "failures_produce_no_candidates": all(not result.candidates for result in (missing, bad_schema, bad_integer, bad_json, pdf, media, incompatible_result, ambiguous)),
        "no_direct_ecm_epm_or_persistence": _boundary_scan(),
    }
    return checks


def _code(result):
    return result.failures[0].code if result.failures else ""


def _is_frozen(candidate):
    try:
        candidate.field_name = "changed"
        return False
    except FrozenInstanceError:
        return True


def _boundary_scan():
    source = (Path(__file__).parent / "deterministic_parsing.py").read_text(encoding="utf-8").lower()
    prohibited = ("canonicalevidence", "evidenceprovenancemanager", "sqlite", "persist(", "confidence", "reasoning")
    return all(term not in source for term in prohibited)


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"EIL-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
