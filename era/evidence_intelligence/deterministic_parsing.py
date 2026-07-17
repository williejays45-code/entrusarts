"""EIL-001 deterministic, profile-driven artifact parsing.

This module produces evidence candidates only.  It does not call ECM/EPM,
persist data, infer fields, or interpret evidence.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import re
import zipfile

from era.evidence_intelligence.contracts import EvidenceCandidate, ParserTrace
from era.evidence_intelligence.parser_profile import PROFILE_COMPATIBLE


CSV_PARSER = "CSV"
JSON_PARSER = "JSON"
ZIP_PARSER = "ZIP"
MDB_DERIVED_PARSER = "MDB_DERIVED"
SUPPORTED_PARSERS = frozenset({CSV_PARSER, JSON_PARSER, ZIP_PARSER, MDB_DERIVED_PARSER})

UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
PDF_NOT_SUPPORTED = "PDF_NOT_SUPPORTED"
MALFORMED_BYTES = "MALFORMED_BYTES"
UNKNOWN_SCHEMA = "UNKNOWN_SCHEMA"
INCOMPATIBLE_PROFILE = "INCOMPATIBLE_PROFILE"
MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
AMBIGUOUS_FIELD_LOCATION = "AMBIGUOUS_FIELD_LOCATION"
UNDECLARED_ALIAS = "UNDECLARED_ALIAS"
INVALID_LEXICAL_VALUE = "INVALID_LEXICAL_VALUE"


@dataclass(frozen=True)
class ParseFailure:
    code: str
    detail: str
    source_location: str = ""


@dataclass(frozen=True)
class ParseResult:
    candidates: tuple[EvidenceCandidate, ...]
    failures: tuple[ParseFailure, ...]

    @property
    def succeeded(self):
        return not self.failures


class DeterministicArtifactParser:
    """Dispatch to an explicit format parser and fail closed otherwise."""

    MEDIA = {
        CSV_PARSER: frozenset({"text/csv", "application/csv"}),
        JSON_PARSER: frozenset({"application/json"}),
        ZIP_PARSER: frozenset({"application/zip"}),
        MDB_DERIVED_PARSER: frozenset({"application/vnd.era.mdb-rows+json"}),
    }

    def parse(self, member, profile) -> ParseResult:
        """Parse one factory-validated artifact member; loose pairs are rejected."""
        from era.evidence_intelligence.membership import ValidatedArtifactMember
        if not isinstance(member, ValidatedArtifactMember) or not member.is_valid():
            return ParseResult((), (ParseFailure("FAILED_MEMBERSHIP", "validated member required"),))
        package, artifact = member, member.artifact
        preflight = self._preflight(package, artifact, profile)
        if preflight:
            return ParseResult((), (preflight,))
        handlers = {
            CSV_PARSER: self._parse_csv,
            JSON_PARSER: self._parse_json,
            ZIP_PARSER: self._inspect_zip,
            MDB_DERIVED_PARSER: self._parse_mdb_derived,
        }
        try:
            values = handlers[profile.parser_id](artifact.raw_bytes, profile)
        except _ParseError as exc:
            return ParseResult((), (ParseFailure(exc.code, exc.detail, exc.location),))
        except (UnicodeDecodeError, csv.Error, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            return ParseResult((), (ParseFailure(MALFORMED_BYTES, type(exc).__name__),))

        try:
            candidates = tuple(
                self._candidate(package, artifact, profile, rule, location, lexical)
                for rule, location, lexical in values
            )
        except _ParseError as exc:
            return ParseResult((), (ParseFailure(exc.code, exc.detail, exc.location),))
        return ParseResult(candidates, ())

    def _preflight(self, package, artifact, profile):
        if not package.package_id or not package.execution_id:
            return ParseFailure(UNKNOWN_SCHEMA, "package identity is incomplete")
        if hashlib.sha256(artifact.raw_bytes).hexdigest() != artifact.sha256:
            return ParseFailure(MALFORMED_BYTES, "artifact SHA-256 mismatch")
        if artifact.media_type == "application/pdf":
            return ParseFailure(PDF_NOT_SUPPORTED, artifact.media_type)
        if profile.validate() != PROFILE_COMPATIBLE:
            return ParseFailure(INCOMPATIBLE_PROFILE, "parser/profile compatibility failed")
        if profile.parser_id not in SUPPORTED_PARSERS:
            return ParseFailure(INCOMPATIBLE_PROFILE, profile.parser_id)
        if artifact.media_type != profile.supported_media_type or artifact.media_type not in self.MEDIA[profile.parser_id]:
            return ParseFailure(UNSUPPORTED_MEDIA_TYPE, artifact.media_type)
        locations = tuple(rule.source_location for rule in profile.field_rules)
        names = tuple(rule.candidate_field_name for rule in profile.field_rules)
        if len(locations) != len(set(locations)) or len(names) != len(set(names)):
            return ParseFailure(AMBIGUOUS_FIELD_LOCATION, "duplicate profile field rule")
        return None

    def _parse_csv(self, raw, profile):
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), strict=True)
        headers = tuple(reader.fieldnames or ())
        self._require_schema(headers, profile.required_schema_or_signature)
        rules = self._column_rules(profile)
        rows = list(reader)
        return self._row_values(rows, rules, "row")

    def _parse_json(self, raw, profile):
        document = json.loads(raw.decode("utf-8"), parse_int=str, parse_float=str)
        if not isinstance(document, dict):
            raise _ParseError(UNKNOWN_SCHEMA, "JSON root must be an object")
        signature = profile.required_schema_or_signature
        if signature.startswith("keys:"):
            expected = tuple(part for part in signature[5:].split(",") if part)
            if tuple(sorted(document)) != tuple(sorted(expected)):
                raise _ParseError(UNKNOWN_SCHEMA, "JSON keys do not match profile")
        elif signature != "object":
            raise _ParseError(UNKNOWN_SCHEMA, "unknown JSON schema signature")
        values = []
        for rule in profile.normalized().field_rules:
            if not rule.source_location.startswith("json:/"):
                raise _ParseError(AMBIGUOUS_FIELD_LOCATION, rule.source_location)
            found, value = self._json_pointer(document, rule.source_location[6:])
            if not found:
                if rule.required:
                    raise _ParseError(MISSING_REQUIRED_FIELD, rule.candidate_field_name, rule.source_location)
                continue
            if isinstance(value, (dict, list)) or value is None:
                raise _ParseError(AMBIGUOUS_FIELD_LOCATION, rule.source_location, rule.source_location)
            lexical = self._json_lexical(value)
            values.append((rule, rule.source_location, lexical))
        return values

    def _inspect_zip(self, raw, profile):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = tuple(info.filename for info in archive.infolist())
            if len(names) != len(set(names)):
                raise _ParseError(AMBIGUOUS_FIELD_LOCATION, "duplicate ZIP member name")
            self._require_members(names, profile.required_schema_or_signature)
            values = []
            for rule in profile.normalized().field_rules:
                if not rule.source_location.startswith("member:"):
                    raise _ParseError(AMBIGUOUS_FIELD_LOCATION, rule.source_location)
                name = rule.source_location[7:]
                if name not in names:
                    if rule.required:
                        raise _ParseError(MISSING_REQUIRED_FIELD, name, rule.source_location)
                    continue
                values.append((rule, f"zip:/{name}", name))
            return values

    def _parse_mdb_derived(self, raw, profile):
        document = json.loads(raw.decode("utf-8"), parse_int=str, parse_float=str)
        if not isinstance(document, dict) or set(document) != {"schema", "rows"}:
            raise _ParseError(UNKNOWN_SCHEMA, "MDB-derived envelope must contain only schema and rows")
        schema, rows = document["schema"], document["rows"]
        if not isinstance(schema, list) or not all(isinstance(item, str) for item in schema):
            raise _ParseError(UNKNOWN_SCHEMA, "MDB-derived schema is invalid")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise _ParseError(MALFORMED_BYTES, "MDB-derived rows are invalid")
        self._require_schema(tuple(schema), profile.required_schema_or_signature)
        rules = self._column_rules(profile)
        return self._row_values(rows, rules, "mdb-row")

    @staticmethod
    def _column_rules(profile):
        rules = []
        for rule in profile.normalized().field_rules:
            if not rule.source_location.startswith("column:"):
                raise _ParseError(AMBIGUOUS_FIELD_LOCATION, rule.source_location)
            rules.append((rule, rule.source_location[7:]))
        return rules

    def _row_values(self, rows, rules, prefix):
        values = []
        for index, row in enumerate(rows, 1):
            for rule, column in rules:
                if column not in row or row[column] is None or row[column] == "":
                    if rule.required:
                        raise _ParseError(MISSING_REQUIRED_FIELD, column, f"{prefix}:{index}/column:{column}")
                    continue
                value = row[column]
                if not isinstance(value, (str, int, float, bool)):
                    raise _ParseError(AMBIGUOUS_FIELD_LOCATION, column)
                lexical = self._json_lexical(value) if isinstance(value, bool) else str(value)
                values.append((rule, f"{prefix}:{index}/column:{column}", lexical))
        return values

    @staticmethod
    def _require_schema(actual, signature):
        if not signature.startswith("columns:"):
            raise _ParseError(UNKNOWN_SCHEMA, "unknown column signature")
        expected = tuple(part for part in signature[8:].split(",") if part)
        if tuple(actual) != expected:
            raise _ParseError(UNKNOWN_SCHEMA, "columns do not exactly match profile")

    @staticmethod
    def _require_members(actual, signature):
        if not signature.startswith("members:"):
            raise _ParseError(UNKNOWN_SCHEMA, "unknown ZIP signature")
        expected = tuple(part for part in signature[8:].split(",") if part)
        if tuple(sorted(actual)) != tuple(sorted(expected)):
            raise _ParseError(UNKNOWN_SCHEMA, "ZIP members do not exactly match profile")

    @staticmethod
    def _json_pointer(document, pointer):
        value = document
        for encoded in pointer.split("/") if pointer else ():
            key = encoded.replace("~1", "/").replace("~0", "~")
            if not isinstance(value, dict) or key not in value:
                return False, None
            value = value[key]
        return True, value

    @staticmethod
    def _json_lexical(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _candidate(self, package, artifact, profile, rule, location, lexical):
        parsed, proposed_type = self._convert(lexical, rule.lexical_conversion)
        trace = ParserTrace(
            artifact.sha256, package.package_id, package.execution_id,
            artifact.canonical_source_id, profile.parser_id, profile.parser_version,
            profile.profile_id, profile.profile_version, location,
        )
        identity = json.dumps({
            "artifact_sha256": artifact.sha256, "package_id": package.package_id,
            "parser_id": profile.parser_id, "parser_version": profile.parser_version,
            "profile_id": profile.profile_id, "profile_version": profile.profile_version,
            "source_location": location, "field_name": rule.candidate_field_name,
            "original_lexical_value": lexical, "parsed_value": parsed,
            "proposed_value_type": proposed_type,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return EvidenceCandidate(
            hashlib.sha256(identity).hexdigest(), rule.candidate_field_name,
            lexical, parsed, proposed_type, trace, "VALID",
        )

    @staticmethod
    def _convert(value, conversion):
        if conversion == "PRESERVE_TEXT":
            return value, "TEXT"
        if conversion == "TRIM_TEXT":
            return value.strip(), "TEXT"
        if conversion == "INTEGER":
            if not re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
                raise _ParseError(INVALID_LEXICAL_VALUE, conversion)
            return value, "INTEGER"
        if conversion == "DECIMAL":
            if not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value):
                raise _ParseError(INVALID_LEXICAL_VALUE, conversion)
            try:
                Decimal(value)
            except InvalidOperation:
                raise _ParseError(INVALID_LEXICAL_VALUE, conversion)
            return value, "DECIMAL"
        if conversion == "BOOLEAN":
            if value not in ("true", "false"):
                raise _ParseError(INVALID_LEXICAL_VALUE, conversion)
            return value, "BOOLEAN"
        raise _ParseError(UNDECLARED_ALIAS, conversion)


class _ParseError(Exception):
    def __init__(self, code, detail, location=""):
        self.code, self.detail, self.location = code, detail, location
        super().__init__(code)
