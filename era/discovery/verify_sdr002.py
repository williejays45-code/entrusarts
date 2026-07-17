"""SDR-002 canonical source identity and boundary verification."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

from era.discovery.source_identity import (
    AMBIGUOUS, AMBIGUOUS_ALIAS, CANONICAL_ID_VERSION, DECLARED_ALIAS_MATCH,
    EXACT_CANONICAL_MATCH, INVALID_INPUT, INVALID_REFERENCE,
    JURISDICTION_MISMATCH, PROVIDER_MISMATCH, RECORD_TYPE_MISMATCH,
    RESOLVED, SOURCE_KIND_MISMATCH, UNKNOWN_ALIAS, UNRESOLVED,
    CanonicalSourceDescriptor, DeclaredSourceAlias, SourceIdentityRequest,
    SourceIdentityResolver,
)


NOW = datetime(2026, 7, 12, 21, 0, tzinfo=timezone.utc)
DCAD = CanonicalSourceDescriptor(
    "TX Dallas", "DCAD", "Appraisal District", "Parcel Record", ("PARCEL",),
)
TARRANT = CanonicalSourceDescriptor(
    "TX Tarrant", "TAD", "Appraisal District", "Parcel Record", ("PARCEL",),
)


def resolver(aliases):
    return SourceIdentityResolver(tuple(aliases), clock=lambda: NOW)


def request(reference, descriptor=DCAD, record_key="ACCOUNT-123"):
    return SourceIdentityRequest(reference, descriptor, "CATALOG-4", record_key)


def run_checks():
    aliases = (
        DeclaredSourceAlias("DCAD", DCAD),
        DeclaredSourceAlias("Dallas CAD", DCAD),
        DeclaredSourceAlias("Dallas Central Appraisal District", DCAD),
    )
    service = resolver(reversed(aliases))
    canonical = DCAD.canonical_source_id()
    exact = service.resolve(request(canonical))
    alias = service.resolve(request("Dallas CAD"))
    alias2 = resolver(aliases).resolve(request("Dallas CAD"))
    unknown = service.resolve(request("Dallas Appraisal Maybe"))
    fuzzy = service.resolve(request("Dallas CA"))
    invalid = service.resolve(request(""))
    changed_key = service.resolve(request("Dallas CAD", record_key="OTHER-999"))
    changed_health_descriptor = CanonicalSourceDescriptor(
        DCAD.jurisdiction, DCAD.provider_id, DCAD.source_kind, DCAD.record_type,
        ("PARCEL", "HEALTH_CHANGED", "LIFECYCLE_CHANGED"),
    )
    changed_facts = service.resolve(request("Dallas CAD", changed_health_descriptor))
    ambiguous = resolver((
        DeclaredSourceAlias("CAD", DCAD),
        DeclaredSourceAlias("CAD", TARRANT),
    )).resolve(request("CAD"))
    jurisdiction_mismatch = resolver((DeclaredSourceAlias("TAD", TARRANT),)).resolve(request("TAD"))
    provider_mismatch_target = CanonicalSourceDescriptor(
        DCAD.jurisdiction, "OTHER", DCAD.source_kind, DCAD.record_type,
    )
    provider_mismatch = resolver((DeclaredSourceAlias("OTHER", provider_mismatch_target),)).resolve(request("OTHER"))
    record_mismatch_target = CanonicalSourceDescriptor(
        DCAD.jurisdiction, DCAD.provider_id, DCAD.source_kind, "Tax Record",
    )
    record_mismatch = resolver((DeclaredSourceAlias("TAX", record_mismatch_target),)).resolve(request("TAX"))
    kind_mismatch_target = CanonicalSourceDescriptor(
        DCAD.jurisdiction, DCAD.provider_id, "Bulk Index", DCAD.record_type,
    )
    kind_mismatch = resolver((DeclaredSourceAlias("INDEX", kind_mismatch_target),)).resolve(request("INDEX"))

    checks = {
        "canonical_id_structure": canonical == "src:tx-dallas:dcad:appraisal_district:parcel_record",
        "canonical_id_lowercase_ascii": canonical == canonical.lower() and canonical.isascii(),
        "canonical_id_replayable": DCAD.canonical_source_id() == canonical,
        "canonical_version_metadata": exact.canonical_id_version == CANONICAL_ID_VERSION == "1",
        "exact_canonical_match": exact.status == RESOLVED and exact.reason_code == EXACT_CANONICAL_MATCH,
        "declared_alias_match": alias.status == RESOLVED and alias.reason_code == DECLARED_ALIAS_MATCH,
        "alias_order_irrelevant": alias == alias2,
        "unknown_alias_unresolved": unknown.status == UNRESOLVED and unknown.reason_code == UNKNOWN_ALIAS,
        "no_fuzzy_resolution": fuzzy.status == UNRESOLVED and fuzzy.canonical_source_id is None,
        "invalid_reference": invalid.status == INVALID_INPUT and invalid.reason_code == INVALID_REFERENCE,
        "ambiguous_alias_fails_closed": ambiguous.status == AMBIGUOUS and ambiguous.reason_code == AMBIGUOUS_ALIAS and ambiguous.canonical_source_id is None,
        "record_key_not_in_identity": changed_key.canonical_source_id == alias.canonical_source_id,
        "health_lifecycle_capability_noise_irrelevant": changed_facts.canonical_source_id == alias.canonical_source_id,
        "jurisdiction_mismatch": jurisdiction_mismatch.reason_code == JURISDICTION_MISMATCH,
        "provider_mismatch": provider_mismatch.reason_code == PROVIDER_MISMATCH,
        "record_type_mismatch": record_mismatch.reason_code == RECORD_TYPE_MISMATCH,
        "source_kind_mismatch": kind_mismatch.reason_code == SOURCE_KIND_MISMATCH,
        "unresolved_has_no_canonical_id": all(item.canonical_source_id is None for item in (unknown, fuzzy, ambiguous, jurisdiction_mismatch, provider_mismatch, record_mismatch, kind_mismatch)),
        "timestamp_injected": alias.evaluated_at == "2026-07-12T21:00:00+00:00",
        "semantic_replayability": alias == alias2,
        "resolver_configuration_immutable": isinstance(service.aliases, tuple),
        "no_mutable_result_state": set(service.__dict__) == {"aliases", "clock"},
    }
    try:
        alias.status = UNRESOLVED
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["resolution_immutable"] = frozen

    source = (Path(__file__).parent / "source_identity.py").read_text(encoding="utf-8").lower()
    checks["no_persistence"] = all(term not in source for term in ("sqlite", "database", "persist("))
    checks["no_acquisition"] = all(term not in source for term in ("retrieve(", "acquisitionresult", "acquisitionrequest"))
    checks["no_evidence_or_property_identity"] = all(term not in source for term in ("canonicalevidence", "property_id", "upr"))
    checks["no_planning"] = "acquisitionplan" not in source and "planner" not in source
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"SDR-002 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)

