"""SEI-001 governed structured, non-personal supplemental evidence intake."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from era.canonical.canonical_enums import (
    EvidenceCategory,
    EvidenceSourceClass,
    EvidenceValueType,
)
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.shared.audit import BaseAuditPublisher


CONTRACT_VERSION = "SEI-001"
PROVIDER_ID = "SEI-001-OPERATOR-SUPPLEMENTAL"
UNVERIFIED = "UNVERIFIED"
MAX_ITEMS = 8
MAX_FACTS_PER_ITEM = 12
MAX_FIELD_LENGTH = 128
MAX_NUMERIC_DIGITS = 32
MAX_NUMERIC_EXPONENT = 18
_DIGEST = re.compile(r"^[A-Fa-f0-9]{64}$")
_NUMBER = re.compile(
    r"^[+-]?(?:(?:0|[1-9][0-9]*)|(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+))"
    r"(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"
)
_UTC = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
_PII_KEY = re.compile(
    r"(?:tenant|owner|phone|telephone|bank|routing|account|parcel|mailing|address|person|name)",
    re.IGNORECASE,
)


def _rule(canonical, category, value_type, kind, minimum=None, maximum=None, values=(), units=None):
    return {
        "canonical": canonical,
        "category": category,
        "value_type": value_type,
        "kind": kind,
        "minimum": minimum,
        "maximum": maximum,
        "values": frozenset(values),
        "units": units,
    }


_CURRENCY = (Decimal("0"), Decimal("1000000000000"))
_COUNT = (Decimal("0"), Decimal("100000"))

EVIDENCE_SCHEMAS = {
    "listing_financial_summary": {
        "required": {"asking_price", "gross_income_annual", "net_operating_income_annual", "unit_count"},
        "fields": {
            "asking_price": _rule("asking_price", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "gross_income_annual": _rule("gross_income_annual", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD/YEAR"),
            "net_operating_income_annual": _rule("net_operating_income_annual", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD/YEAR"),
            "stated_cap_rate_percent": _rule("stated_cap_rate_percent", EvidenceCategory.MARKET, EvidenceValueType.DECIMAL, "number", Decimal("0"), Decimal("100"), units="PERCENT"),
            "unit_count": _rule("units", EvidenceCategory.BUILDING, EvidenceValueType.INTEGER, "integer", *_COUNT, units="COUNT"),
        },
    },
    "rent_roll_summary": {
        "required": {"unit_count", "gross_monthly_rent"},
        "fields": {
            "unit_count": _rule("units", EvidenceCategory.BUILDING, EvidenceValueType.INTEGER, "integer", *_COUNT, units="COUNT"),
            "occupied_unit_count": _rule("occupied_unit_count", EvidenceCategory.MARKET, EvidenceValueType.INTEGER, "integer", *_COUNT, units="COUNT"),
            "vacant_unit_count": _rule("vacant_unit_count", EvidenceCategory.MARKET, EvidenceValueType.INTEGER, "integer", *_COUNT, units="COUNT"),
            "gross_monthly_rent": _rule("gross_monthly_rent", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD/MONTH"),
            "effective_monthly_rent": _rule("effective_monthly_rent", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD/MONTH"),
        },
    },
    "operating_statement": {
        "required": {"period_start", "period_end", "gross_operating_income", "operating_expenses", "net_operating_income"},
        "fields": {
            "period_start": _rule("operating_period_start", EvidenceCategory.DOCUMENT, EvidenceValueType.DATE, "date"),
            "period_end": _rule("operating_period_end", EvidenceCategory.DOCUMENT, EvidenceValueType.DATE, "date"),
            "gross_operating_income": _rule("gross_operating_income", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "operating_expenses": _rule("operating_expenses", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "net_operating_income": _rule("net_operating_income", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
        },
    },
    "tax_record": {
        "required": {"tax_year", "current_assessed_value", "annual_tax_amount"},
        "fields": {
            "tax_year": _rule("tax_year", EvidenceCategory.TAX, EvidenceValueType.INTEGER, "integer", Decimal("1900"), Decimal("2100")),
            "current_appraised_value": _rule("current_appraised_value", EvidenceCategory.TAX, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "current_assessed_value": _rule("current_assessed_value", EvidenceCategory.TAX, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "annual_tax_amount": _rule("annual_tax_amount", EvidenceCategory.TAX, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD/YEAR"),
        },
    },
    "insurance_quote": {
        "required": {"annual_premium", "deductible", "coverage_amount", "quote_expiration_date"},
        "fields": {
            "annual_premium": _rule("insurance_annual_premium", EvidenceCategory.DOCUMENT, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD/YEAR"),
            "deductible": _rule("insurance_deductible", EvidenceCategory.DOCUMENT, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "coverage_amount": _rule("insurance_coverage_amount", EvidenceCategory.DOCUMENT, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "quote_expiration_date": _rule("insurance_quote_expiration_date", EvidenceCategory.DOCUMENT, EvidenceValueType.DATE, "date"),
        },
    },
    "hoa_record": {
        "required": {"periodic_dues", "billing_frequency", "effective_date"},
        "fields": {
            "periodic_dues": _rule("hoa_periodic_dues", EvidenceCategory.DOCUMENT, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "billing_frequency": _rule("hoa_billing_frequency", EvidenceCategory.DOCUMENT, EvidenceValueType.ENUM, "enum", values={"MONTHLY", "QUARTERLY", "ANNUAL"}),
            "special_assessment_amount": _rule("hoa_special_assessment_amount", EvidenceCategory.DOCUMENT, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "effective_date": _rule("hoa_effective_date", EvidenceCategory.DOCUMENT, EvidenceValueType.DATE, "date"),
        },
    },
    "inspection_summary": {
        "required": {"inspection_date", "material_issue_count", "safety_issue_count"},
        "fields": {
            "inspection_date": _rule("inspection_date", EvidenceCategory.DOCUMENT, EvidenceValueType.DATE, "date"),
            "material_issue_count": _rule("inspection_material_issue_count", EvidenceCategory.DOCUMENT, EvidenceValueType.INTEGER, "integer", *_COUNT, units="COUNT"),
            "safety_issue_count": _rule("inspection_safety_issue_count", EvidenceCategory.DOCUMENT, EvidenceValueType.INTEGER, "integer", *_COUNT, units="COUNT"),
            "estimated_repair_cost": _rule("inspection_estimated_repair_cost", EvidenceCategory.DOCUMENT, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
        },
    },
    "title_lien_summary": {
        "required": {"effective_date", "lien_count", "aggregate_lien_amount", "title_status"},
        "fields": {
            "effective_date": _rule("title_effective_date", EvidenceCategory.LEGAL, EvidenceValueType.DATE, "date"),
            "lien_count": _rule("title_lien_count", EvidenceCategory.LEGAL, EvidenceValueType.INTEGER, "integer", *_COUNT, units="COUNT"),
            "aggregate_lien_amount": _rule("title_aggregate_lien_amount", EvidenceCategory.LEGAL, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "title_status": _rule("title_status", EvidenceCategory.LEGAL, EvidenceValueType.ENUM, "enum", values={"CLEAR", "EXCEPTIONS_REPORTED", "REVIEW_REQUIRED", "UNKNOWN"}),
        },
    },
    "comparable_sale_summary": {
        "required": {"sale_date", "sale_price", "distance_miles"},
        "fields": {
            "sale_date": _rule("comparable_sale_date", EvidenceCategory.MARKET, EvidenceValueType.DATE, "date"),
            "sale_price": _rule("comparable_sale_price", EvidenceCategory.MARKET, EvidenceValueType.CURRENCY, "number", *_CURRENCY, units="USD"),
            "distance_miles": _rule("comparable_distance_miles", EvidenceCategory.MARKET, EvidenceValueType.DECIMAL, "number", Decimal("0"), Decimal("1000"), units="MILES"),
            "living_area_sqft": _rule("living_area", EvidenceCategory.BUILDING, EvidenceValueType.DECIMAL, "number", Decimal("0"), Decimal("10000000"), units="SQFT"),
        },
    },
}

SUPPORTED_EVIDENCE_TYPES = frozenset(EVIDENCE_SCHEMAS)
SUPPORTED_SOURCE_CLASSES = frozenset(item.value for item in EvidenceSourceClass)


class SupplementalEvidenceAudit(BaseAuditPublisher):
    pass


@dataclass(frozen=True)
class GovernedSupplementalItem:
    evidence_type: str
    source_class: str
    observation_utc: str
    evidence_digest: str
    verification_status: str
    normalized_facts: tuple[tuple[str, str], ...]
    canonical_fields: tuple[str, ...]
    applicable_period: str
    item_identity: str
    records: tuple[CanonicalEvidenceRecord, ...]


@dataclass(frozen=True)
class SupplementalEvidencePackage:
    contract_version: str
    property_id: str
    package_digest: str
    records: tuple[CanonicalEvidenceRecord, ...]
    items: tuple[GovernedSupplementalItem, ...]


def _canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _normalize_value(rule, value):
    if isinstance(value, bool):
        raise ValueError("INVALID_FACT_VALUE")
    kind = rule["kind"]
    if isinstance(value, str) and len(value) > MAX_FIELD_LENGTH:
        raise ValueError("FIELD_LENGTH_EXCEEDED")
    if kind in {"number", "integer"}:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("INVALID_NUMERIC_VALUE")
        # Lexical validation precedes canonicalization.  In particular, a
        # caller cannot hide ASCII or Unicode boundary whitespace by relying
        # on trimming before the governed numeric grammar runs.
        lexical = value if isinstance(value, str) else str(value)
        if not _NUMBER.fullmatch(lexical):
            raise ValueError("INVALID_NUMERIC_VALUE")
        try:
            parsed = Decimal(lexical.replace(",", ""))
        except (InvalidOperation, ValueError):
            raise ValueError("INVALID_NUMERIC_VALUE") from None
        if not parsed.is_finite():
            raise ValueError("INVALID_NUMERIC_VALUE")
        decimal_tuple = parsed.as_tuple()
        if (len(decimal_tuple.digits) > MAX_NUMERIC_DIGITS
                or abs(decimal_tuple.exponent) > MAX_NUMERIC_EXPONENT):
            raise ValueError("NUMERIC_PRECISION_EXCEEDED")
        if kind == "integer" and parsed != parsed.to_integral_value():
            raise ValueError("INVALID_INTEGER_VALUE")
        if rule["minimum"] is not None and parsed < rule["minimum"]:
            raise ValueError("NUMERIC_RANGE_EXCEEDED")
        if rule["maximum"] is not None and parsed > rule["maximum"]:
            raise ValueError("NUMERIC_RANGE_EXCEEDED")
        return str(int(parsed)) if kind == "integer" else _canonical_decimal(parsed)
    if not isinstance(value, str):
        raise ValueError("INVALID_FACT_VALUE")
    candidate = value.strip()
    if not candidate:
        raise ValueError("INVALID_FACT_VALUE")
    if kind == "date":
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            raise ValueError("INVALID_DATE_VALUE") from None
    if kind == "enum":
        normalized = candidate.upper()
        if normalized not in rule["values"]:
            raise ValueError("INVALID_ENUM_VALUE")
        return normalized
    raise ValueError("INVALID_FIELD_RULE")


def _normalize_observation(value) -> str:
    if not isinstance(value, str) or len(value) > 40 or not _UTC.fullmatch(value):
        raise ValueError("INVALID_OBSERVATION_UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError("INVALID_OBSERVATION_UTC") from None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_contract_item(item):
    if not isinstance(item, dict):
        raise ValueError("INVALID_SUPPLEMENTAL_EVIDENCE_ITEM")
    allowed = {"evidence_type", "source_class", "observation_utc", "evidence_digest", "verification_status", "facts"}
    if set(item) - allowed:
        raise ValueError("UNKNOWN_EVIDENCE_FIELD")
    if set(item) != allowed:
        raise ValueError("MISSING_EVIDENCE_FIELD")
    evidence_type = str(item["evidence_type"]).strip().lower()
    schema = EVIDENCE_SCHEMAS.get(evidence_type)
    if schema is None:
        raise ValueError("UNSUPPORTED_EVIDENCE_TYPE")
    source_class = str(item["source_class"]).strip().upper()
    if source_class not in SUPPORTED_SOURCE_CLASSES:
        raise ValueError("UNSUPPORTED_SOURCE_CLASS")
    status = str(item["verification_status"]).strip().upper()
    if status != UNVERIFIED:
        raise ValueError("VERIFICATION_AUTHORITY_REQUIRED")
    digest = str(item["evidence_digest"]).strip().upper()
    if not _DIGEST.fullmatch(digest):
        raise ValueError("INVALID_EVIDENCE_DIGEST")
    observation = _normalize_observation(item["observation_utc"])
    facts = item["facts"]
    if not isinstance(facts, dict) or not facts or len(facts) > MAX_FACTS_PER_ITEM:
        raise ValueError("INVALID_FACT_SET")
    for field in facts:
        if not isinstance(field, str) or len(field) > 64:
            raise ValueError("INVALID_FACT_FIELD")
        if _PII_KEY.search(field):
            raise ValueError("PII_FIELD_PROHIBITED")
    unknown = set(facts) - set(schema["fields"])
    if unknown:
        raise ValueError("UNKNOWN_FACT_FIELD")
    if not schema["required"].issubset(facts):
        raise ValueError("REQUIRED_FACT_MISSING")
    normalized = {
        field: _normalize_value(schema["fields"][field], facts[field])
        for field in sorted(facts)
    }
    return evidence_type, source_class, observation, digest, status, normalized, schema


def compute_evidence_digest(evidence_type, source_class, observation_utc, facts) -> str:
    placeholder = {
        "evidence_type": evidence_type,
        "source_class": source_class,
        "observation_utc": observation_utc,
        "evidence_digest": "0" * 64,
        "verification_status": UNVERIFIED,
        "facts": facts,
    }
    kind, source, observed, _digest, status, normalized, _schema = _normalize_contract_item(placeholder)
    material = {
        "contract": CONTRACT_VERSION,
        "evidence_type": kind,
        "source_class": source,
        "observation_utc": observed,
        "verification_status": status,
        "facts": normalized,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _item_identity(digest: str) -> str:
    material = f"{CONTRACT_VERSION}|{digest}".encode("ascii")
    return "SEI-ITEM-" + hashlib.sha256(material).hexdigest().upper()


def _applicable_period(kind: str, facts: dict[str, str], observed: str, item_id: str) -> str:
    if kind == "operating_statement":
        return f"{facts['period_start']}/{facts['period_end']}"
    if kind == "tax_record":
        return f"TAX-YEAR:{facts['tax_year']}"
    if kind == "insurance_quote":
        return f"QUOTE-THROUGH:{facts['quote_expiration_date']}"
    if kind == "hoa_record":
        return f"EFFECTIVE:{facts['effective_date']}"
    if kind == "inspection_summary":
        return f"INSPECTED:{facts['inspection_date']}"
    if kind == "title_lien_summary":
        return f"EFFECTIVE:{facts['effective_date']}"
    if kind == "comparable_sale_summary":
        return f"COMPARABLE:{item_id}"
    return f"OBSERVED:{observed}"


def _semantic_key(kind, input_field, rule, period, item_id) -> str:
    value_type = rule["value_type"].value
    units = rule["units"] or "NONE"
    canonical = rule["canonical"]
    if input_field == "current_appraised_value":
        return f"PROPERTY|{canonical}|{value_type}|{units}"
    if input_field == "unit_count":
        return f"PROPERTY|{canonical}|{value_type}|{units}"
    context = period
    if kind == "comparable_sale_summary":
        context = item_id
    return f"SEI|{kind}|{context}|{canonical}|{value_type}|{units}"


def _build_governed_item(property_id, kind, source, observed, digest, status, facts, schema):
    item_id = _item_identity(digest)
    period = _applicable_period(kind, facts, observed, item_id)
    records = []
    fields = []
    for input_field, value in facts.items():
        rule = schema["fields"][input_field]
        field_name = rule["canonical"]
        semantic_key = _semantic_key(kind, input_field, rule, period, item_id)
        evidence_material = f"{property_id}|{digest}|{field_name}".encode("utf-8")
        evidence_id = "SEI-" + hashlib.sha256(evidence_material).hexdigest()
        provenance = Provenance(
            connector_id=PROVIDER_ID,
            provider_name="ERA Supplemental Evidence Intake",
            source_name=f"{CONTRACT_VERSION}:{kind}",
            source_class=EvidenceSourceClass(source),
            retrieved_at=observed,
            legal_basis="OPERATOR_SUPPLIED_NON_PERSONAL_SUMMARY",
            normalization_version=CONTRACT_VERSION,
            audit_reference=f"{CONTRACT_VERSION}:{digest}",
            verification_status=status,
            evidence_digest=digest,
        )
        records.append(CanonicalEvidenceRecord(
            evidence_id=evidence_id,
            property_id=property_id,
            category=rule["category"],
            field_name=field_name,
            raw_value=value,
            normalized_value=value,
            units=rule["units"],
            provenance=provenance,
            value_type=rule["value_type"],
            evidence_type=kind,
            semantic_comparison_key=semantic_key,
            applicable_period=period,
            item_identity=item_id,
            created_at=observed,
        ))
        fields.append(field_name)
    records.sort(key=lambda record: record.evidence_id)
    return GovernedSupplementalItem(
        evidence_type=kind,
        source_class=source,
        observation_utc=observed,
        evidence_digest=digest,
        verification_status=status,
        normalized_facts=tuple(sorted(facts.items())),
        canonical_fields=tuple(sorted(fields)),
        applicable_period=period,
        item_identity=item_id,
        records=tuple(records),
    )


def _package_digest(property_id, items) -> str:
    material = {
        "contract": CONTRACT_VERSION,
        "property_id": property_id,
        "items": [
            {
                "evidence_digest": item.evidence_digest,
                "item_identity": item.item_identity,
                "applicable_period": item.applicable_period,
                "normalized_facts": item.normalized_facts,
                "semantic_keys": tuple(
                    record.semantic_comparison_key for record in item.records
                ),
            }
            for item in items
        ],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def validate_governed_package(package, property_id) -> tuple[CanonicalEvidenceRecord, ...]:
    """Independently validate the immutable acquisition package at pipeline admission."""
    if type(package) is not SupplementalEvidencePackage:
        raise ValueError("INVALID_SUPPLEMENTAL_PACKAGE_TYPE")
    if package.contract_version != CONTRACT_VERSION or package.property_id != property_id:
        raise ValueError("INVALID_SUPPLEMENTAL_PACKAGE_AUTHORITY")
    if not isinstance(package.items, tuple) or not isinstance(package.records, tuple):
        raise ValueError("INVALID_SUPPLEMENTAL_PACKAGE_SHAPE")
    if len(package.items) > MAX_ITEMS:
        raise ValueError("ITEM_COUNT_EXCEEDED")
    expected_items = []
    item_digests = []
    for item in package.items:
        if type(item) is not GovernedSupplementalItem:
            raise ValueError("INVALID_SUPPLEMENTAL_ITEM_TYPE")
        item_digests.append(item.evidence_digest)
        facts = dict(item.normalized_facts)
        raw = {
            "evidence_type": item.evidence_type,
            "source_class": item.source_class,
            "observation_utc": item.observation_utc,
            "evidence_digest": item.evidence_digest,
            "verification_status": item.verification_status,
            "facts": facts,
        }
        kind, source, observed, digest, status, normalized, schema = _normalize_contract_item(raw)
        if compute_evidence_digest(kind, source, observed, normalized) != digest:
            raise ValueError("EVIDENCE_DIGEST_MISMATCH")
        expected = _build_governed_item(
            property_id, kind, source, observed, digest, status, normalized, schema,
        )
        if item != expected:
            raise ValueError("SUPPLEMENTAL_ITEM_INTEGRITY_FAILURE")
        expected_items.append(expected)
    if len(item_digests) != len(set(item_digests)):
        raise ValueError("DUPLICATE_EVIDENCE")
    expected_items.sort(key=lambda item: item.evidence_digest)
    if tuple(expected_items) != package.items:
        raise ValueError("SUPPLEMENTAL_ITEM_ORDER_INVALID")
    expected_records = tuple(
        sorted(
            (record for item in expected_items for record in item.records),
            key=lambda record: record.evidence_id,
        )
    )
    if expected_records != package.records:
        raise ValueError("SUPPLEMENTAL_RECORD_INTEGRITY_FAILURE")
    evidence_ids = [record.evidence_id for record in package.records]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("DUPLICATE_EVIDENCE")
    if package.package_digest != _package_digest(property_id, expected_items):
        raise ValueError("SUPPLEMENTAL_PACKAGE_DIGEST_MISMATCH")
    return expected_records


class SupplementalEvidenceNormalizer:
    """Acquisition-side validation and conversion into the established canonical contract."""

    def __init__(self, audit=None):
        self.audit = audit or SupplementalEvidenceAudit()

    def normalize(self, property_id, items) -> SupplementalEvidencePackage:
        if not items:
            empty_items = ()
            return SupplementalEvidencePackage(
                CONTRACT_VERSION, property_id, _package_digest(property_id, empty_items), (), (),
            )
        if not isinstance(items, (list, tuple)) or len(items) > MAX_ITEMS:
            self.audit.publish("SEI_BLOCKED", {"reason": "ITEM_COUNT_EXCEEDED"})
            raise ValueError("ITEM_COUNT_EXCEEDED")
        governed_items = []
        digests = set()
        try:
            for item in items:
                kind, source, observed, digest, status, facts, schema = _normalize_contract_item(item)
                expected = compute_evidence_digest(kind, source, observed, facts)
                if digest != expected:
                    raise ValueError("EVIDENCE_DIGEST_MISMATCH")
                if digest in digests:
                    raise ValueError("DUPLICATE_EVIDENCE")
                digests.add(digest)
                governed = _build_governed_item(
                    property_id, kind, source, observed, digest, status, facts, schema,
                )
                governed_items.append(governed)
                self.audit.publish("SEI_EVIDENCE_ACCEPTED", {
                    "evidence_type": kind,
                    "verification_status": status,
                    "canonical_field_count": len(governed.records),
                })
        except ValueError as exc:
            self.audit.publish("SEI_BLOCKED", {"reason": str(exc)})
            raise
        governed_items.sort(key=lambda item: item.evidence_digest)
        records = tuple(sorted(
            (record for item in governed_items for record in item.records),
            key=lambda record: record.evidence_id,
        ))
        package = SupplementalEvidencePackage(
            contract_version=CONTRACT_VERSION,
            property_id=property_id,
            package_digest=_package_digest(property_id, governed_items),
            records=records,
            items=tuple(governed_items),
        )
        validate_governed_package(package, property_id)
        return package
