import sys
from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance, utc_now
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.canonical import canonical_errors as errors

print("ECM-OFFICIAL-TEXT-001 VERIFICATION")
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
        "normalization_version": "ECM-OFFICIAL-TEXT-1.0",
        "audit_reference": "AUD-OFFICIAL-TEXT-001",
    }
    data.update(overrides)
    return Provenance(**data)


def record(**overrides):
    data = {
        "evidence_id": "EV-OFFICIAL-001",
        "property_id": "ERA-PR-2026-000001",
        "category": EvidenceCategory.LEGAL,
        "field_name": "legal_description",
        "raw_value": "ANTILLES CONDOMINIUM",
        "normalized_value": "ANTILLES CONDOMINIUM",
        "units": None,
        "provenance": provenance(),
        "value_type": EvidenceValueType.OFFICIAL_TEXT,
    }
    data.update(overrides)
    return CanonicalEvidenceRecord(**data)


checks = {}

# --- TEXT: strict leakage protection remains, byte-for-byte unchanged
# from ECM-TYPE-001 -- re-confirmed here specifically to prove
# ECM-OFFICIAL-TEXT-001 didn't weaken it while adding the new type. ----------
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="occupancy rate at 85%",
))
checks["text_still_blocks_percent"] = status == errors.NUMERIC_LEAKAGE_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="5926 Sandhurst Ln (confidence=0.95)",
))
checks["text_still_blocks_confidence_equals"] = status == errors.NUMERIC_LEAKAGE_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="appraised at 152500.00",
))
checks["text_still_blocks_ordinary_decimal"] = status == errors.NUMERIC_LEAKAGE_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.TEXT, normalized_value="a plain description with no numbers",
))
checks["text_still_allows_clean_value"] = status == errors.PASS

# --- OFFICIAL_TEXT: allows ordinary decimals and percentages in
# source text. Tested against the REAL DCAD legal line that surfaced
# this collision in DCAD-JOIN-001. --------------------------------------------
status, normalized = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="BLDG A UNIT 103 & 4.98% CE", normalized_value="BLDG A UNIT 103 & 4.98% CE",
))
checks["official_text_allows_real_dcad_percent_text"] = (
    status == errors.PASS and normalized.normalized_value == "BLDG A UNIT 103 & 4.98% CE"
)

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="VOL95069/3403 DD032995 CO-DALLAS", normalized_value="VOL95069/3403 DD032995 CO-DALLAS",
))
checks["official_text_allows_ordinary_alphanumeric_legal_text"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="assessed value adjustment of 12.5 percent applied",
    normalized_value="assessed value adjustment of 12.5 percent applied",
))
checks["official_text_allows_ordinary_decimal_in_prose"] = status == errors.PASS

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="BLK D/5534  LT 4", normalized_value="BLK D/5534  LT 4",
))
checks["official_text_allows_real_dcad_legal_baseline"] = status == errors.PASS

# --- OFFICIAL_TEXT: still blocks explicit confidence vocabulary --
# confidence=, score=, probability=, reliability= -- each tested
# individually. -----------------------------------------------------------------
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="legal note (confidence=0.9)", normalized_value="legal note (confidence=0.9)",
))
checks["official_text_still_blocks_confidence_equals"] = status == errors.CONFIDENCE_VOCABULARY_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="remark (score=85)", normalized_value="remark (score=85)",
))
checks["official_text_still_blocks_score_equals"] = status == errors.CONFIDENCE_VOCABULARY_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="note (probability=0.7)", normalized_value="note (probability=0.7)",
))
checks["official_text_still_blocks_probability_equals"] = status == errors.CONFIDENCE_VOCABULARY_DETECTED

status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="note (reliability=high)", normalized_value="note (reliability=high)",
))
checks["official_text_still_blocks_reliability_equals"] = status == errors.CONFIDENCE_VOCABULARY_DETECTED

# --- OFFICIAL_TEXT does NOT block "weight=" (that's TEXT-only in the
# original list; OFFICIAL_TEXT's list is deliberately narrower --
# confidence/score/probability/reliability only, per FORGE's rule). ----------
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="load weight=500 lbs per official spec", normalized_value="load weight=500 lbs per official spec",
))
checks["official_text_does_not_block_weight_equals"] = status == errors.PASS

# --- Distinct error code from TEXT's leakage error -- an audit trail
# can tell "this was rejected for being free TEXT with a decimal" apart
# from "this was rejected for containing confidence vocabulary." ------------
checks["official_text_uses_distinct_error_code_from_text"] = (
    errors.CONFIDENCE_VOCABULARY_DETECTED != errors.NUMERIC_LEAKAGE_DETECTED
)

# --- Case insensitivity, consistent with the existing TEXT check. -----------
status, _ = engine.normalize_record(record(
    value_type=EvidenceValueType.OFFICIAL_TEXT,
    raw_value="note (CONFIDENCE=0.9)", normalized_value="note (CONFIDENCE=0.9)",
))
checks["official_text_confidence_check_case_insensitive"] = status == errors.CONFIDENCE_VOCABULARY_DETECTED

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"ECM-OFFICIAL-TEXT-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
