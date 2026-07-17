import re
from datetime import date
from decimal import Decimal, InvalidOperation
from era.canonical.canonical_audit import CanonicalAuditPublisher
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.canonical.canonical_models import CanonicalEvidenceRecord
from era.canonical import canonical_errors as errors

# TEXT-only leakage guard, unchanged from before ECM-TYPE-001. This is
# meant to catch a confidence/score/weight string smuggled into a free
# TEXT field (e.g. "5926 Sandhurst Ln (confidence=0.95)") -- it was
# never meant to reject a genuine numeric value, and until ECM-TYPE-001
# there was no way to tell the two apart. That's the actual bug
# ECM-TYPE-001 closes: not by loosening this pattern, but by only
# applying it to the type it was designed for.
NUMERIC_LEAK_PATTERNS = [
    r"\d+%",
    r"\d+\.\d+",
    r"score\s*=",
    r"weight\s*=",
    r"confidence\s*=",
]

# ECM-OFFICIAL-TEXT-001: a narrower check for OFFICIAL_TEXT -- ordinary
# decimals and percentages are expected and allowed in authoritative
# source text (a real DCAD legal line like "BLDG A UNIT 103 & 4.98% CE"
# is not leakage, it's the record). What's still blocked is explicit
# confidence/scoring vocabulary -- the actual signature of governance
# metadata being smuggled into a text field, independent of whether
# numbers happen to be present.
OFFICIAL_TEXT_LEAK_PATTERNS = [
    r"confidence\s*=",
    r"score\s*=",
    r"probability\s*=",
    r"reliability\s*=",
]

# Types exempt from the TEXT leakage guard because they are
# structurally not free text -- a controlled/typed value doesn't carry
# the "someone smuggled a confidence score into a description" risk
# the guard exists for. Not explicitly specified by ECM-TYPE-001's
# locked rules for GEO/ENUM/INTEGER/BOOLEAN; this is a documented,
# conservative default extending the same reasoning the spec gives for
# TEXT/DECIMAL/CURRENCY/IDENTIFIER/DATE to the remaining types.
# Types NOT subject to any leakage check at all -- they are
# structurally typed values, not free text, so the "someone smuggled a
# confidence score into a description" risk the check exists for
# doesn't apply. Not explicitly specified by ECM-TYPE-001's locked
# rules for GEO/ENUM/INTEGER/BOOLEAN; this is a documented,
# conservative default extending the same reasoning the spec gives for
# DECIMAL/CURRENCY/IDENTIFIER/DATE to the remaining types. TEXT and
# OFFICIAL_TEXT are handled by their own explicit branches in
# normalize_record() below, each with its own pattern list -- see
# NUMERIC_LEAK_PATTERNS and OFFICIAL_TEXT_LEAK_PATTERNS above.

_BOOLEAN_TRUE = {"true", "1", "yes", "y"}
_BOOLEAN_FALSE = {"false", "0", "no", "n"}


class CanonicalEvidenceModel:
    def __init__(self, audit=None):
        self.audit = audit or CanonicalAuditPublisher()

    def attempt_write(self, target: str):
        if target in {"recommendation", "confidence", "weight", "calibration", "evidence_reliability"}:
            if target == "confidence":
                self.audit.publish("CANONICAL_BLOCKED", {
                    "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
                    "target": target,
                })
                return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.READ_ONLY_CANONICAL,
                "target": target,
            })
            return False, errors.READ_ONLY_CANONICAL
        return True, errors.PASS

    def normalize_record(self, record: CanonicalEvidenceRecord):
        if record is None:
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.CANONICAL_RECORD_REQUIRED,
            })
            return errors.CANONICAL_RECORD_REQUIRED, None
        if not isinstance(record.category, EvidenceCategory):
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.INVALID_CATEGORY,
            })
            return errors.INVALID_CATEGORY, None
        if not isinstance(record.value_type, EvidenceValueType):
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.INVALID_VALUE_TYPE,
            })
            return errors.INVALID_VALUE_TYPE, None
        if record.provenance is None:
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.PROVENANCE_REQUIRED,
            })
            return errors.PROVENANCE_REQUIRED, None
        if not isinstance(record.provenance.source_class, EvidenceSourceClass):
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.INVALID_SOURCE_CLASS,
            })
            return errors.INVALID_SOURCE_CLASS, None
        if not record.raw_value:
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.RAW_VALUE_REQUIRED,
            })
            return errors.RAW_VALUE_REQUIRED, None
        if not record.normalized_value:
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": errors.NORMALIZED_VALUE_REQUIRED,
            })
            return errors.NORMALIZED_VALUE_REQUIRED, None

        type_status, typed_record = self._validate_and_normalize_by_type(record)
        if type_status != errors.PASS:
            self.audit.publish("CANONICAL_BLOCKED", {
                "reason": type_status,
                "evidence_id": record.evidence_id,
                "value_type": record.value_type.value,
            })
            return type_status, None
        record = typed_record

        if record.value_type == EvidenceValueType.TEXT:
            if self._contains_pattern_leakage(record.normalized_value, NUMERIC_LEAK_PATTERNS):
                self.audit.publish("CANONICAL_BLOCKED", {
                    "reason": errors.NUMERIC_LEAKAGE_DETECTED,
                    "evidence_id": record.evidence_id,
                })
                return errors.NUMERIC_LEAKAGE_DETECTED, None
        elif record.value_type == EvidenceValueType.OFFICIAL_TEXT:
            if self._contains_pattern_leakage(record.normalized_value, OFFICIAL_TEXT_LEAK_PATTERNS):
                self.audit.publish("CANONICAL_BLOCKED", {
                    "reason": errors.CONFIDENCE_VOCABULARY_DETECTED,
                    "evidence_id": record.evidence_id,
                })
                return errors.CONFIDENCE_VOCABULARY_DETECTED, None
        # All other types (INTEGER/DECIMAL/CURRENCY/BOOLEAN/DATE/
        # IDENTIFIER/GEO/ENUM) are structurally typed values, not free
        # text -- no leakage check applies to them at all.

        self.audit.publish("CANONICAL_RECORD_NORMALIZED", {
            "evidence_id": record.evidence_id,
            "property_id": record.property_id,
            "category": record.category.value,
            "field_name": record.field_name,
            "value_type": record.value_type.value,
            "normalization_version": record.provenance.normalization_version,
        })
        return errors.PASS, record

    def _validate_and_normalize_by_type(self, record: CanonicalEvidenceRecord):
        """Returns (status, record). For most types the record passes
        through unchanged (status PASS, same record); DATE returns a
        record with normalized_value rewritten to canonical YYYY-MM-DD
        form. Never coerces IDENTIFIER to a numeric type -- see that
        branch specifically."""
        value_type = record.value_type
        value = record.normalized_value

        if value_type == EvidenceValueType.TEXT:
            return errors.PASS, record

        if value_type == EvidenceValueType.IDENTIFIER:
            # Never parsed as a number, in either direction -- leading
            # zeros (e.g. a DCAD ACCOUNT_NUM like "00000416479000000")
            # must survive exactly as given. The only validation here
            # is "non-empty," already checked above.
            return errors.PASS, record

        if value_type in (EvidenceValueType.DECIMAL, EvidenceValueType.CURRENCY):
            candidate = value.strip()
            if value_type == EvidenceValueType.CURRENCY:
                candidate = candidate.replace("$", "").replace(",", "").strip()
            try:
                Decimal(candidate)
            except (InvalidOperation, ValueError):
                return errors.MALFORMED_NUMERIC_VALUE, None
            return errors.PASS, record

        if value_type == EvidenceValueType.INTEGER:
            candidate = value.strip().replace(",", "")
            try:
                int(candidate)
            except ValueError:
                return errors.MALFORMED_INTEGER_VALUE, None
            return errors.PASS, record

        if value_type == EvidenceValueType.BOOLEAN:
            lowered = value.strip().lower()
            if lowered not in _BOOLEAN_TRUE and lowered not in _BOOLEAN_FALSE:
                return errors.MALFORMED_BOOLEAN_VALUE, None
            return errors.PASS, record

        if value_type == EvidenceValueType.DATE:
            try:
                parsed = date.fromisoformat(value.strip())
            except ValueError:
                return errors.MALFORMED_DATE_VALUE, None
            # Canonical calendar-date string only -- no time component,
            # no timezone suffix ever invented. A certified appraisal
            # date is a calendar date, not an instant in time; adding a
            # fabricated "T00:00:00Z" would assert precision the source
            # data never had.
            normalized = replace_normalized_value(record, parsed.isoformat())
            return errors.PASS, normalized

        if value_type in (EvidenceValueType.GEO, EvidenceValueType.ENUM):
            return errors.PASS, record

        return errors.PASS, record

    def _contains_pattern_leakage(self, text: str, patterns):
        lowered = str(text).lower()
        return any(re.search(pattern, lowered) for pattern in patterns)


def replace_normalized_value(record: CanonicalEvidenceRecord, new_value: str) -> CanonicalEvidenceRecord:
    from dataclasses import replace
    return replace(record, normalized_value=new_value)
