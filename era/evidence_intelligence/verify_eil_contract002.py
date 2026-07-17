"""EIL-CONTRACT-002 profile isolation and compatibility verification."""

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

from era.evidence_intelligence.parser_profile import (
    INVALID_PROFILE, PROFILE_COMPATIBLE, UNKNOWN_PARSER_PROFILE_COMBINATION,
    EvidenceSchemaProfile, ParserFieldRule,
)


def profile(rules=None, compatible=(("CSV", "1"),)):
    return EvidenceSchemaProfile(
        "DCAD-CSV", "1", "text/csv", "columns:ACCOUNT_NUM,APPRAISAL_YR",
        "CSV", "1",
        rules or (
            ParserFieldRule("column:GIS_PARCEL_ID", "parcel_id", "PRESERVE_TEXT", True),
            ParserFieldRule("column:TOT_VAL", "total_appraised_value", "TRIM_TEXT", False),
        ),
        ("MALFORMED_SCHEMA", "MISSING_REQUIRED_FIELD", "UNSUPPORTED_MEDIA_TYPE"),
        compatible,
    )


def run_checks():
    a = profile()
    b = profile(tuple(reversed(a.field_rules)))
    normalized_a = a.normalized()
    normalized_b = b.normalized()
    incompatible = profile(compatible=(("CSV", "2"),))
    invalid = EvidenceSchemaProfile("", "", "", "", "", "", (), (), ())
    names = {item.name for item in fields(EvidenceSchemaProfile)}
    prohibited = {
        "confidence", "ranking", "conflict_resolution", "canonical_truth",
        "inferred_defaults", "gap_filling", "investment_meaning",
        "runtime_aliases", "provider_eligibility", "reasoning_instructions",
        "canonical_category", "canonical_value_type",
    }

    checks = {
        "profile_compatible_explicitly": a.validate() == PROFILE_COMPATIBLE,
        "unknown_combination_fails_closed": incompatible.validate() == UNKNOWN_PARSER_PROFILE_COMBINATION,
        "invalid_profile_fails_closed": invalid.validate() == INVALID_PROFILE,
        "field_order_semantically_irrelevant": normalized_a == normalized_b,
        "failure_codes_sorted": normalized_a.parse_failure_codes == tuple(sorted(a.parse_failure_codes)),
        "compatibility_sorted": normalized_a.compatible_parser_versions == (("CSV", "1"),),
        "required_fields_explicit": a.required_fields == ("parcel_id",),
        "optional_fields_explicit": a.optional_fields == ("total_appraised_value",),
        "no_canonicalization_policy": not names & prohibited,
        "source_to_candidate_only": all(rule.source_location and rule.candidate_field_name for rule in a.field_rules),
        "profile_versioned": a.profile_id == "DCAD-CSV" and a.profile_version == "1",
        "parser_versioned": a.parser_id == "CSV" and a.parser_version == "1",
        "media_and_schema_explicit": a.supported_media_type == "text/csv" and bool(a.required_schema_or_signature),
        "closed_failure_codes": isinstance(a.parse_failure_codes, tuple) and all(a.parse_failure_codes),
    }
    try:
        a.profile_id = "changed"
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["profile_immutable"] = frozen

    source = (Path(__file__).parent / "parser_profile.py").read_text(encoding="utf-8").lower()
    checks["no_registry_database_persistence"] = all(term not in source for term in ("registry", "sqlite", "database", "persist("))
    checks["no_parser_implementation"] = all(term not in source for term in ("csv.dictreader", "json.loads", "zipfile", "pdf"))
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"EIL-CONTRACT-002 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)

