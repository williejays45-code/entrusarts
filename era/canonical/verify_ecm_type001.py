import sys
from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance, utc_now
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.canonical import canonical_errors as errors

print("ECM-TYPE-001 TYPED CANONICAL EVIDENCE VERIFICATION")
print("=" * 70)

engine = CanonicalEvidenceModel()


def provenance(**overrides):
    data = {
        "connector_id": "DCAD_BULK_DATA_2025",
        "provider_name": "DCAD Data Products - 2025 Certified Data Files",
        "source_name": "DCAD Data Products",
        "source_class": EvidenceSourceClass.PUBLIC_RECORD,
        "retrieved_at": utc_now(),
        "legal_basis": "PUBLIC_RECORD",
        "normalization_version": "ECM-TYPE-1.0",
        "audit_reference": "AUD-CAN-TYPE-001",
    }
    data.update(overrides)
    return Provenance(**data)


def record(**overrides):
    data = {
        "evidence_id": "EV-TYPE-001",
        "property_id": "ERA-PR-2026-000001",
        "category": EvidenceCategory.MARKET,
        "field_name": "total_appraised_value",
        "raw_value": "152500.00",
        "normalized_value": "152500.00",
        "units": None,
        "provenance": provenance(),
        "value_type": EvidenceValueType.CURRENCY,
    }
    data.update(overrides)
    return CanonicalEvidenceRecord(**data)


checks = {}

# --- TEXT: leakage detection applies; embedded confidence/score
# strings blocked. -----------------------------------------------------------
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="5926 Sandhurst Ln (confidence=0.95)",
))
checks["text_embedded_confidence_string_blocked"] = status == errors.NUMERIC_LEAKAGE_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="weight = 0.3187",
))
checks["text_embedded_weight_string_blocked"] = status == errors.NUMERIC_LEAKAGE_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="a plain text description with no numbers",
))
checks["text_clean_value_passes"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="occupancy rate at 85%",
))
checks["text_embedded_percent_blocked"] = status == errors.NUMERIC_LEAKAGE_DETECTED

# --- DECIMAL / CURRENCY: parsed with Decimal; legitimate values like
# 152500.00 allowed; malformed numeric strings blocked. ----------------------
status, normalized = engine.normalize_record(record(
    value_type=EvidenceValueType.CURRENCY, raw_value="152500.00", normalized_value="152500.00",
))
checks["currency_legitimate_value_allowed"] = status == errors.PASS and normalized.normalized_value == "152500.00"

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.CURRENCY, raw_value="$152,500.00", normalized_value="$152,500.00",
))
checks["currency_with_symbol_and_commas_allowed"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.CURRENCY, raw_value="not-a-number", normalized_value="not-a-number",
))
checks["currency_malformed_value_blocked"] = status == errors.MALFORMED_NUMERIC_VALUE

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.DECIMAL, raw_value="3300000.00", normalized_value="3300000.00",
))
checks["decimal_legitimate_value_allowed"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.DECIMAL, raw_value="12.34.56", normalized_value="12.34.56",
))
checks["decimal_malformed_value_blocked"] = status == errors.MALFORMED_NUMERIC_VALUE

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.DECIMAL, raw_value="0.00", normalized_value="0.00",
))
checks["decimal_zero_value_allowed"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.DECIMAL, raw_value="-45000.50", normalized_value="-45000.50",
))
checks["decimal_negative_value_allowed"] = status == errors.PASS

# --- IDENTIFIER: preserves leading zeros; never coerced to float or
# integer. ---------------------------------------------------------------------
status, normalized = engine.normalize_record(record(
    value_type=EvidenceValueType.IDENTIFIER, field_name="parcel_id",
    raw_value="00000416479000000", normalized_value="00000416479000000",
))
checks["identifier_leading_zeros_preserved"] = (
    status == errors.PASS and normalized.normalized_value == "00000416479000000"
)
checks["identifier_not_coerced_to_int_or_float"] = (
    isinstance(normalized.normalized_value, str) and normalized.normalized_value[0] == "0"
)

status, normalized = engine.normalize_record(record(
    value_type=EvidenceValueType.IDENTIFIER, field_name="parcel_id",
    raw_value="100050800B09B0000", normalized_value="100050800B09B0000",
))
checks["identifier_alphanumeric_allowed"] = status == errors.PASS and normalized.normalized_value == "100050800B09B0000"

# An identifier that LOOKS like it would trip the TEXT leakage regex
# (e.g. contains what looks like a decimal) must still pass, since
# IDENTIFIER is exempt from that check entirely -- it's not free text.
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.IDENTIFIER, field_name="parcel_id",
    raw_value="123.456", normalized_value="123.456",
))
checks["identifier_exempt_from_text_leakage_check"] = status == errors.PASS

# --- DATE: validated structurally; normalized without inventing
# timezone information. ---------------------------------------------------------
status, normalized = engine.normalize_record(record(
    value_type=EvidenceValueType.DATE, field_name="appraisal_date",
    raw_value="2025-01-01", normalized_value="2025-01-01",
))
checks["date_valid_iso_date_allowed"] = status == errors.PASS
checks["date_normalized_value_is_canonical_form"] = normalized.normalized_value == "2025-01-01"
checks["date_normalization_does_not_invent_timezone"] = (
    "T" not in normalized.normalized_value and "Z" not in normalized.normalized_value
    and "+" not in normalized.normalized_value
)

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.DATE, field_name="appraisal_date",
    raw_value="not-a-date", normalized_value="not-a-date",
))
checks["date_malformed_value_blocked"] = status == errors.MALFORMED_DATE_VALUE

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.DATE, field_name="appraisal_date",
    raw_value="2025-13-45", normalized_value="2025-13-45",
))
checks["date_invalid_calendar_date_blocked"] = status == errors.MALFORMED_DATE_VALUE

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.DATE, field_name="appraisal_date",
    raw_value="01/01/2025", normalized_value="01/01/2025",
))
checks["date_non_iso_format_blocked"] = status == errors.MALFORMED_DATE_VALUE

# --- INTEGER (default handling, not explicitly specified but built
# consistently with the locked type list). --------------------------------------
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.INTEGER, field_name="year_built",
    raw_value="1998", normalized_value="1998",
))
checks["integer_legitimate_value_allowed"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.INTEGER, field_name="year_built",
    raw_value="1998.5", normalized_value="1998.5",
))
checks["integer_decimal_value_blocked"] = status == errors.MALFORMED_INTEGER_VALUE

# --- BOOLEAN (default handling). -------------------------------------------------
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.BOOLEAN, field_name="homestead_exempt",
    raw_value="true", normalized_value="true",
))
checks["boolean_true_allowed"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.BOOLEAN, field_name="homestead_exempt",
    raw_value="maybe", normalized_value="maybe",
))
checks["boolean_malformed_value_blocked"] = status == errors.MALFORMED_BOOLEAN_VALUE

# --- Invalid value_type itself is rejected cleanly (not a Python enum
# member at all). ------------------------------------------------------------------
class NotARealEnum:
    value = "FAKE"

bad_record = record(value_type=EvidenceValueType.TEXT)
from dataclasses import replace
bad_record = replace(bad_record, value_type="TEXT")  # a plain string, not the enum member
status, _ = engine.normalize_record(bad_record)
checks["non_enum_value_type_rejected"] = status == errors.INVALID_VALUE_TYPE

# --- Backward compatibility: value_type defaults to TEXT when a caller
# doesn't specify one at all (every pre-ECM-TYPE-001 construction). ------------
legacy_record = CanonicalEvidenceRecord(
    evidence_id="EV-LEGACY", property_id="ERA-PR-2026-000001", category=EvidenceCategory.OWNERSHIP,
    field_name="owner_name", raw_value="JOHN A DOE", normalized_value="John A. Doe",
    units=None, provenance=provenance(),
)
checks["default_value_type_is_text"] = legacy_record.value_type == EvidenceValueType.TEXT
status, _ = engine.normalize_record(legacy_record)
checks["legacy_construction_still_works"] = status == errors.PASS

# --- Determinism preserved across all typed paths. --------------------------------
r1_status, r1 = engine.normalize_record(record(evidence_id="EV-DET-TYPE", value_type=EvidenceValueType.DATE,
                                                 raw_value="2025-06-15", normalized_value="2025-06-15"))
r2_status, r2 = engine.normalize_record(record(evidence_id="EV-DET-TYPE", value_type=EvidenceValueType.DATE,
                                                 raw_value="2025-06-15", normalized_value="2025-06-15"))
checks["deterministic_across_typed_path"] = (
    r1_status == r2_status == errors.PASS and r1.normalized_value == r2.normalized_value == "2025-06-15"
)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"ECM-TYPE-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
