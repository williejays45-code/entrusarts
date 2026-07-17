"""EIL-CONTRACT-002 immutable, versioned parser schema profiles."""

from dataclasses import dataclass


PROFILE_COMPATIBLE = "PROFILE_COMPATIBLE"
UNKNOWN_PARSER_PROFILE_COMBINATION = "UNKNOWN_PARSER_PROFILE_COMBINATION"
INVALID_PROFILE = "INVALID_PROFILE"


@dataclass(frozen=True)
class ParserFieldRule:
    source_location: str
    candidate_field_name: str
    lexical_conversion: str
    required: bool


@dataclass(frozen=True)
class EvidenceSchemaProfile:
    profile_id: str
    profile_version: str
    supported_media_type: str
    required_schema_or_signature: str
    parser_id: str
    parser_version: str
    field_rules: tuple[ParserFieldRule, ...]
    parse_failure_codes: tuple[str, ...]
    compatible_parser_versions: tuple[tuple[str, str], ...]

    def normalized(self):
        return EvidenceSchemaProfile(
            self.profile_id,
            self.profile_version,
            self.supported_media_type,
            self.required_schema_or_signature,
            self.parser_id,
            self.parser_version,
            tuple(sorted(self.field_rules, key=lambda item: (
                item.source_location, item.candidate_field_name,
                item.lexical_conversion, item.required,
            ))),
            tuple(sorted(set(self.parse_failure_codes))),
            tuple(sorted(set(self.compatible_parser_versions))),
        )

    def validate(self):
        required = (
            self.profile_id, self.profile_version, self.supported_media_type,
            self.required_schema_or_signature, self.parser_id, self.parser_version,
        )
        if not all(required) or not self.field_rules or not self.parse_failure_codes:
            return INVALID_PROFILE
        pair = (self.parser_id, self.parser_version)
        if pair not in self.compatible_parser_versions:
            return UNKNOWN_PARSER_PROFILE_COMBINATION
        if any(not all((rule.source_location, rule.candidate_field_name, rule.lexical_conversion)) for rule in self.field_rules):
            return INVALID_PROFILE
        return PROFILE_COMPATIBLE

    @property
    def required_fields(self):
        return tuple(rule.candidate_field_name for rule in self.normalized().field_rules if rule.required)

    @property
    def optional_fields(self):
        return tuple(rule.candidate_field_name for rule in self.normalized().field_rules if not rule.required)

