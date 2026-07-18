"""Fabricated verification for SEI-001 governed supplemental evidence intake."""

import hashlib
import json
import os
import random
import socket
import tempfile
import time
from contextlib import nullcontext
from dataclasses import asdict, replace
from pathlib import Path

from era.acquisition.provider_health_authority import ReadinessObservation
from era.acquisition.supplemental_evidence import (
    MAX_ITEMS,
    SUPPORTED_EVIDENCE_TYPES,
    SupplementalEvidenceNormalizer,
    compute_evidence_digest,
    validate_governed_package,
)
from era.api.service import AnalyzeRequest, EraPropertyApiService
from era.app import bootstrap_collin_demo, build_app
from era.live_adapters.collin_bulk_data_adapter import CollinBulkDataAdapter
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.conflict.conflict_resolver import EvidenceConflictResolver
from era.fusion.fusion_models import FusionEvidence
from era.fusion.fusion_engine import MultiSourceFusionEngine
from era.pipeline import OperationCancelled, OperationControl
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record.property_models import PropertyIdentity
from era.providers import provider_errors
from era.providers.provider_models import ProviderEvidence
from era.run_property import AccountBoundCollinAdapter, COLLIN_PROVIDER, execute_operator


OBSERVED = "2026-01-15T12:00:00Z"
TOKEN = "fabricated-sei-token-with-no-production-authority"


def evidence(kind, facts, source_class="USER_PROVIDED"):
    digest = compute_evidence_digest(kind, source_class, OBSERVED, facts)
    return {
        "evidence_type": kind,
        "source_class": source_class,
        "observation_utc": OBSERVED,
        "evidence_digest": digest,
        "verification_status": "UNVERIFIED",
        "facts": facts,
    }


LISTING = evidence("listing_financial_summary", {
    "asking_price": 480000,
    "gross_income_annual": 42000,
    "net_operating_income_annual": 23000,
    "stated_cap_rate_percent": 4.79,
    "unit_count": 2,
})
RENT_ROLL = evidence("rent_roll_summary", {
    "unit_count": 2,
    "occupied_unit_count": 2,
    "vacant_unit_count": 0,
    "gross_monthly_rent": 3500,
    "effective_monthly_rent": 3400,
})
OPERATING = evidence("operating_statement", {
    "period_start": "2025-01-01",
    "period_end": "2025-12-31",
    "gross_operating_income": 42000,
    "operating_expenses": 19000,
    "net_operating_income": 23000,
})


class FabricatedCollinAdapter:
    def __init__(self):
        self.lookups = []

    def provider_id(self): return COLLIN_PROVIDER
    def provider_name(self): return "Fabricated Collin"
    def connector_version(self): return "SEI-TEST"
    def health_check(self): return True
    def retrieve(self, account_id):
        self.lookups.append(account_id)
        return provider_errors.PASS, {
            "evidence": [
                ProviderEvidence("property_address", "100 FICTIONAL TEST WAY"),
                ProviderEvidence("city", "TESTVILLE"),
                ProviderEvidence("county", "Collin"),
                ProviderEvidence("state", "TX"),
                ProviderEvidence("current_appraised_value", "100000"),
            ],
            "provenance": {"legal_basis": "FABRICATED_PUBLIC_RECORD"},
            "source_reference": f"FABRICATED:{account_id}",
        }


def factory_for(adapter, captured):
    def factory(_mdb, _xls, account_id):
        pipeline = build_app(use_mock_auth=True)
        bound = AccountBoundCollinAdapter(adapter, account_id)
        pipeline.c.collin_bulk_data_adapter = bound
        pipeline.c.county_connectors[COLLIN_PROVIDER] = bound
        pipeline.c._provider_readiness_observers[COLLIN_PROVIDER] = ReadinessObservation.READY
        bootstrap_collin_demo(pipeline)
        captured.append(pipeline)
        return pipeline
    return factory


class FabricatedResolver(CollinBulkDataAdapter):
    def __init__(self, _mdb, _xls): pass
    def resolve_address(self, _address): return "PASS", "FABRICATED-ACCOUNT", 1


class SlowFabricatedCollinAdapter(FabricatedCollinAdapter):
    def retrieve(self, account_id):
        time.sleep(0.03)
        return super().retrieve(account_id)


def expect_error(call, code):
    try:
        call()
    except ValueError as exc:
        return str(exc) == code
    return False


checks = {}
normalizer = SupplementalEvidenceNormalizer()
listing_package = normalizer.normalize("PROP-1", [LISTING])
checks["valid_listing_summary"] = len(listing_package.records) == 5
multi_package = normalizer.normalize("PROP-1", [RENT_ROLL, OPERATING])
checks["valid_rent_roll_and_operating"] = len(multi_package.items) == 2 and len(multi_package.records) == 10
checks["supported_types_closed"] = SUPPORTED_EVIDENCE_TYPES == {
    "listing_financial_summary", "rent_roll_summary", "operating_statement", "tax_record",
    "insurance_quote", "hoa_record", "inspection_summary", "title_lien_summary",
    "comparable_sale_summary",
}

unknown_type = dict(LISTING); unknown_type["evidence_type"] = "broker_narrative"
checks["unknown_evidence_type_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [unknown_type]), "UNSUPPORTED_EVIDENCE_TYPE"
)
unknown_field = {**LISTING, "facts": {**LISTING["facts"], "free_form_note": "anything"}}
unknown_field["evidence_digest"] = "0" * 64
checks["unknown_field_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [unknown_field]), "UNKNOWN_FACT_FIELD"
)
unknown_item_field = {**LISTING, "arbitrary": "not allowed"}
checks["unknown_item_field_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [unknown_item_field]), "UNKNOWN_EVIDENCE_FIELD"
)
pii = {**LISTING, "facts": {**LISTING["facts"], "tenant_name": "FABRICATED PRIVATE TENANT"}}
pii["evidence_digest"] = "0" * 64
checks["pii_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [pii]), "PII_FIELD_PROHIBITED"
)
checks["oversized_item_count_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [LISTING] * (MAX_ITEMS + 1)), "ITEM_COUNT_EXCEEDED"
)
bad_number = {**LISTING, "facts": {**LISTING["facts"], "asking_price": -1}}
bad_number["evidence_digest"] = "0" * 64
checks["invalid_numeric_range_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [bad_number]), "NUMERIC_RANGE_EXCEEDED"
)
long_value = {**LISTING, "facts": {**LISTING["facts"], "asking_price": "1" * 129}}
long_value["evidence_digest"] = "0" * 64
checks["field_length_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [long_value]), "FIELD_LENGTH_EXCEEDED"
)
bad_date = {**OPERATING, "facts": {**OPERATING["facts"], "period_end": "2025-99-99"}}
bad_date["evidence_digest"] = "0" * 64
checks["invalid_date_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [bad_date]), "INVALID_DATE_VALUE"
)
non_utc = {**LISTING, "observation_utc": "2026-01-15T12:00:00+01:00"}
checks["observation_must_be_utc"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [non_utc]), "INVALID_OBSERVATION_UTC"
)
checks["duplicate_evidence_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [LISTING, LISTING]), "DUPLICATE_EVIDENCE"
)
claimed_verified = {**LISTING, "verification_status": "VERIFIED"}
checks["operator_cannot_claim_verified"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [claimed_verified]), "VERIFICATION_AUTHORITY_REQUIRED"
)
digest_mismatch = {**LISTING, "evidence_digest": "F" * 64}
checks["digest_mismatch_rejected"] = expect_error(
    lambda: normalizer.normalize("PROP-1", [digest_mismatch]), "EVIDENCE_DIGEST_MISMATCH"
)
malformed_grouping = {**LISTING, "facts": {**LISTING["facts"], "asking_price": "1,2,3"}}
checks["malformed_numeric_grouping_rejected"] = expect_error(
    lambda: compute_evidence_digest(
        "listing_financial_summary", "USER_PROVIDED", OBSERVED,
        malformed_grouping["facts"],
    ), "INVALID_NUMERIC_VALUE"
)
checks["proper_numeric_grouping_accepted"] = (
    compute_evidence_digest(
        "listing_financial_summary", "USER_PROVIDED", OBSERVED,
        {**LISTING["facts"], "asking_price": "480,000.00"},
    ) == LISTING["evidence_digest"]
)
checks["numeric_boundary_whitespace_rejected"] = all(
    expect_error(
        lambda value=value: compute_evidence_digest(
            "listing_financial_summary", "USER_PROVIDED", OBSERVED,
            {**LISTING["facts"], "asking_price": value},
        ), "INVALID_NUMERIC_VALUE",
    )
    for value in (" 480000", "480000 ", "\t480000", "\n480000", "\u00a0480000")
)
checks["numeric_grammar_ascii_only"] = all(
    expect_error(
        lambda value=value: compute_evidence_digest(
            "listing_financial_summary", "USER_PROVIDED", OBSERVED,
            {**LISTING["facts"], "asking_price": value},
        ), "INVALID_NUMERIC_VALUE",
    )
    for value in (
        "١٢٣",       # Arabic-Indic
        "۱۲۳",       # extended Arabic-Indic
        "１２３",     # full-width
        "1٢3",       # mixed script
        "1,٢٣٤",     # ASCII grouping with non-ASCII digits
    )
)
checks["extreme_exponents_rejected"] = all(
    expect_error(
        lambda value=value: compute_evidence_digest(
            "listing_financial_summary", "USER_PROVIDED", OBSERVED,
            {**LISTING["facts"], "asking_price": value},
        ), expected,
    )
    for value, expected in (
        ("1e999999", "NUMERIC_PRECISION_EXCEEDED"),
        ("1e-999999", "NUMERIC_PRECISION_EXCEEDED"),
    )
)
checks["canonical_utc_grammar_enforced"] = all(
    expect_error(
        lambda observed=observed: compute_evidence_digest(
            "listing_financial_summary", "USER_PROVIDED", observed, LISTING["facts"],
        ), "INVALID_OBSERVATION_UTC",
    )
    for observed in (
        "2026-01-15T12:00:00-00:00",
        "2026-01-15T12:00:00+00:00",
        "2026-01-15T12:00:00+00:00:00",
    )
)
checks["utc_grammar_ascii_only"] = all(
    expect_error(
        lambda observed=observed: compute_evidence_digest(
            "listing_financial_summary", "USER_PROVIDED", observed, LISTING["facts"],
        ), "INVALID_OBSERVATION_UTC",
    )
    for observed in (
        "٢٠٢٦-01-15T12:00:00Z",
        "۲۰۲۶-01-15T12:00:00Z",
        "２０２６-01-15T12:00:00Z",
        "202٦-01-15T12:00:00Z",
    )
)

public_listing = evidence("listing_financial_summary", LISTING["facts"], "PUBLIC_RECORD")
public_package = normalizer.normalize("PROP-2", [public_listing])
public_record = public_package.records[0]
checks["provenance_preserved_unverified"] = (
    public_record.provenance.source_class.value == "PUBLIC_RECORD"
    and public_record.provenance.verification_status == "UNVERIFIED"
    and public_record.provenance.evidence_digest == public_listing["evidence_digest"]
)
audit_text = json.dumps(normalizer.audit.events, sort_keys=True)
checks["audit_privacy_safe"] = all(value not in audit_text for value in (
    "480000", "FABRICATED PRIVATE TENANT", public_listing["evidence_digest"],
))


def fusion_for(package):
    return [
        FusionEvidence(
            evidence_id=record.evidence_id,
            property_id=record.property_id,
            field_name=record.field_name,
            normalized_value=record.normalized_value,
            provider_id=record.provenance.connector_id,
            source_reference=record.provenance.source_name,
            value_type=record.value_type.value,
            units=record.units or "",
            evidence_type=record.evidence_type,
            observation_utc=record.provenance.retrieved_at,
            applicable_period=record.applicable_period,
            item_identity=record.item_identity,
            semantic_comparison_key=record.semantic_comparison_key,
        )
        for record in package.records
    ]


operating_2024 = evidence("operating_statement", {
    "period_start": "2024-01-01", "period_end": "2024-12-31",
    "gross_operating_income": 40000, "operating_expenses": 18000,
    "net_operating_income": 22000,
})
operating_2025 = evidence("operating_statement", {
    "period_start": "2025-01-01", "period_end": "2025-12-31",
    "gross_operating_income": 42000, "operating_expenses": 19000,
    "net_operating_income": 23000,
})
period_package = normalizer.normalize("PROP-PERIOD", [operating_2024, operating_2025])
period_status, period_reports = EvidenceConflictResolver().resolve(fusion_for(period_package))
checks["separate_operating_periods_not_conflicts"] = (
    period_status == "NO_CONFLICT" and period_reports == []
)

comparable_a = evidence("comparable_sale_summary", {
    "sale_date": "2025-01-01", "sale_price": 300000, "distance_miles": 1,
})
comparable_b = evidence("comparable_sale_summary", {
    "sale_date": "2025-02-01", "sale_price": 325000, "distance_miles": 2,
})
comparable_package = normalizer.normalize("PROP-COMP", [comparable_a, comparable_b])
comparable_status, comparable_reports = EvidenceConflictResolver().resolve(
    fusion_for(comparable_package)
)
checks["separate_comparable_sales_not_conflicts"] = (
    comparable_status == "NO_CONFLICT" and comparable_reports == []
)

same_period_a = operating_2025
same_period_b = evidence("operating_statement", {
    "period_start": "2025-01-01", "period_end": "2025-12-31",
    "gross_operating_income": 43000, "operating_expenses": 19500,
    "net_operating_income": 23500,
}, "PUBLIC_RECORD")
conflict_package = normalizer.normalize("PROP-ORDER", [same_period_a, same_period_b])
forward = fusion_for(conflict_package)
_, forward_reports = EvidenceConflictResolver().resolve(forward)
_, reverse_reports = EvidenceConflictResolver().resolve(list(reversed(forward)))
render = lambda reports: json.dumps(
    [asdict(report) for report in reports], sort_keys=True, separators=(",", ":"), default=str,
)
checks["conflict_output_order_independent"] = render(forward_reports) == render(reverse_reports)
checks["conflict_evidence_ids_sorted"] = all(
    report.evidence_ids == sorted(report.evidence_ids) for report in forward_reports
)
permuted_conflicts = []
permuted_fusions = []
for seed in range(8):
    shuffled = list(forward)
    random.Random(seed).shuffle(shuffled)
    _, reports = EvidenceConflictResolver().resolve(shuffled)
    _, fusion_package = MultiSourceFusionEngine().fuse(shuffled)
    permuted_conflicts.append(render(reports))
    permuted_fusions.append(json.dumps(
        asdict(fusion_package), sort_keys=True, separators=(",", ":"), default=str,
    ))
checks["random_permutations_conflict_byte_equivalent"] = len(set(permuted_conflicts)) == 1
checks["random_permutations_fusion_byte_equivalent"] = len(set(permuted_fusions)) == 1
checks["canonical_timestamps_derived_from_observations"] = (
    all(report.detected_at == OBSERVED for report in forward_reports)
    and json.loads(permuted_fusions[0])["created_at"] == OBSERVED
)

unit_a = forward[0]
unit_b = replace(
    unit_a, evidence_id=unit_a.evidence_id + "-OTHER-UNIT",
    normalized_value="999", units="EUR",
)
unit_status, unit_reports = EvidenceConflictResolver().resolve([unit_a, unit_b])
checks["incompatible_units_not_compared"] = unit_status == "NO_CONFLICT" and not unit_reports

checks["governed_package_revalidates"] = (
    validate_governed_package(listing_package, "PROP-1") == listing_package.records
)
checks["caller_record_collection_rejected"] = expect_error(
    lambda: validate_governed_package(list(listing_package.records), "PROP-1"),
    "INVALID_SUPPLEMENTAL_PACKAGE_TYPE",
)
checks["tampered_package_digest_rejected"] = expect_error(
    lambda: validate_governed_package(
        replace(listing_package, package_digest="F" * 64), "PROP-1",
    ), "SUPPLEMENTAL_PACKAGE_DIGEST_MISMATCH",
)
checks["constructed_duplicate_items_rejected"] = expect_error(
    lambda: validate_governed_package(
        replace(
            listing_package,
            items=(listing_package.items[0], listing_package.items[0]),
            records=listing_package.records + listing_package.records,
        ),
        "PROP-1",
    ),
    "DUPLICATE_EVIDENCE",
)

configured_root = os.environ.get("ERA_SEI001_TEST_ROOT")
root_context = nullcontext(configured_root) if configured_root else tempfile.TemporaryDirectory(prefix="era-sei001-")
with root_context as directory:
    root = Path(directory)
    mdb = root / "FABRICATED.mdb"
    xls = root / "FABRICATED.xls"
    mdb.write_bytes(b"FABRICATED SEI MDB")
    xls.write_bytes(b"FABRICATED SEI XLS")
    env = {"ERA_COLLIN_MDB_PATH": str(mdb), "ERA_COLLIN_CODE_LIST_PATH": str(xls)}
    before = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())

    adapter = FabricatedCollinAdapter(); pipelines = []
    common = dict(
        provider="collin", account_id="FABRICATED-ACCOUNT", environ=env,
        pipeline_factory=factory_for(adapter, pipelines), run_id="SEI-RUN",
        utc="2026-01-20T00:00:00Z", salt="SEI-SALT", supplemental_evidence=[LISTING],
    )
    original_connection = socket.create_connection
    socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("NETWORK_FORBIDDEN"))
    try:
        first = execute_operator(**common)
        second = execute_operator(**common)
        checks["no_network_contact"] = True
    finally:
        socket.create_connection = original_connection
    checks["acquisition_reasoning_separation"] = (
        adapter.lookups == ["FABRICATED-ACCOUNT", "FABRICATED-ACCOUNT"]
        and any(stage["name"] == "SEI" and stage["status"] == "UNVERIFIED_ACCEPTED"
                for stage in first["pipeline_stages"])
    )
    checks["deterministic_repeated_execution"] = first == second
    checks["unverified_does_not_force_final"] = (
        first["decision"] == "PENDING_MORE_EVIDENCE"
        and first["supplemental_evidence"]["authority"] == "NON_OVERRIDE_UNVERIFIED"
    )
    checks["no_confidence_invention"] = first["confidence"]["status"] == "NOT_ASSIGNED"
    serialized = json.dumps(first, sort_keys=True)
    checks["privacy_safe_response"] = all(value not in serialized for value in (
        "FABRICATED-ACCOUNT", "100 FICTIONAL TEST WAY", "480000", "42000", "23000",
    ))
    epm_records = [record for record in pipelines[0].c.epm.records.values()
                   if record.provider_id == "SEI-001-OPERATOR-SUPPLEMENTAL"]
    checks["epm_provenance_preserved"] = bool(epm_records) and all(
        record.verification_status == "UNVERIFIED"
        and record.source_class == "USER_PROVIDED"
        and record.submitted_evidence_digest == LISTING["evidence_digest"]
        for record in epm_records
    )

    bypass_pipeline = factory_for(FabricatedCollinAdapter(), [])(
        str(mdb), str(xls), "FABRICATED-ACCOUNT",
    )
    bypass_property = "SEI-BYPASS-PROPERTY"
    bypass_identity = PropertyIdentity(
        property_id=bypass_property,
        address="WITHHELD", city="Collin County", state="TX", zip_code="00000",
        county="Collin", parcel_apn=None, latitude=None, longitude=None,
        property_type=PropertyType.OTHER, strategy_type=StrategyType.OTHER,
    )
    valid_bypass_package = normalizer.normalize(bypass_property, [LISTING])
    base_record = valid_bypass_package.records[0]
    forged_owner = replace(
        base_record,
        evidence_id="FORGED-OWNER",
        field_name="owner_name",
        raw_value="FABRICATED PRIVATE OWNER",
        normalized_value="FABRICATED PRIVATE OWNER",
        category=EvidenceCategory.OWNERSHIP,
        value_type=EvidenceValueType.TEXT,
        semantic_comparison_key="FORGED",
    )
    forged_digest = replace(
        base_record,
        evidence_id="FORGED-DIGEST",
        provenance=replace(base_record.provenance, evidence_digest="NOT-A-SHA256"),
    )
    forged_field = replace(
        base_record, evidence_id="FORGED-FIELD", field_name="forbidden_field",
    )
    forged_inputs = (
        (forged_owner,),
        replace(valid_bypass_package, records=(forged_owner,)),
        replace(valid_bypass_package, records=(forged_digest,)),
        replace(valid_bypass_package, records=(forged_field,)),
    )
    blocked = []
    for candidate in forged_inputs:
        outcome = bypass_pipeline.run_property(
            bypass_property, bypass_identity, "TX", "Collin", COLLIN_PROVIDER,
            supplemental_package=candidate,
        )
        blocked.append(
            outcome.stage("SEI") is not None
            and outcome.stage("SEI").status == "INVALID_SUPPLEMENTAL_PACKAGE"
        )
    checks["pipeline_governed_boundary_blocks_all_forgery"] = all(blocked)
    checks["forged_records_never_reach_epm"] = not any(
        record.evidence_id.startswith("FORGED-")
        or record.original_value == "FABRICATED PRIVATE OWNER"
        for record in bypass_pipeline.c.epm.records.values()
    )

    cancelled_pipeline = factory_for(SlowFabricatedCollinAdapter(), [])(
        str(mdb), str(xls), "FABRICATED-ACCOUNT",
    )
    before_cancel = {
        "rate": dict(cancelled_pipeline.c.rate_limiter._state),
        "epm": dict(cancelled_pipeline.c.epm.records),
        "upr": dict(cancelled_pipeline.c.upr.records),
        "api_store": json.dumps(cancelled_pipeline.c.api_store, sort_keys=True),
        "audit_counts": {
            name: len(engine.audit.events)
            for name, engine in {
                **cancelled_pipeline.c.all_engines(),
                "rate_limiter": cancelled_pipeline.c.rate_limiter,
                "retry_executor": cancelled_pipeline.c.retry_executor,
            }.items()
        },
    }
    try:
        cancelled_pipeline.run_property(
            bypass_property, bypass_identity, "TX", "Collin", COLLIN_PROVIDER,
            supplemental_package=valid_bypass_package,
            operation_control=OperationControl(0.005),
        )
        checks["pipeline_cancellation_raised"] = False
    except OperationCancelled:
        checks["pipeline_cancellation_raised"] = True
    after_cancel = {
        "rate": dict(cancelled_pipeline.c.rate_limiter._state),
        "epm": dict(cancelled_pipeline.c.epm.records),
        "upr": dict(cancelled_pipeline.c.upr.records),
        "api_store": json.dumps(cancelled_pipeline.c.api_store, sort_keys=True),
        "audit_counts": {
            name: len(engine.audit.events)
            for name, engine in {
                **cancelled_pipeline.c.all_engines(),
                "rate_limiter": cancelled_pipeline.c.rate_limiter,
                "retry_executor": cancelled_pipeline.c.retry_executor,
            }.items()
        },
    }
    checks["pipeline_cancellation_restores_observable_state"] = before_cancel == after_cancel
    revoked_control = OperationControl(10)
    revoked_control.revoke()
    revoked_commits = []
    try:
        revoked_control.commit(lambda: revoked_commits.append("COMMITTED"))
        revoked_blocked = False
    except OperationCancelled:
        revoked_blocked = True
    checks["revoked_commit_authority_is_atomic"] = revoked_blocked and not revoked_commits

    conflict_tax = evidence("tax_record", {
        "tax_year": 2025,
        "current_appraised_value": 99999,
        "current_assessed_value": 99999,
        "annual_tax_amount": 2100,
    })
    conflict_report = execute_operator(
        "collin", "FABRICATED-ACCOUNT", env,
        pipeline_factory=factory_for(FabricatedCollinAdapter(), []),
        run_id="SEI-CONFLICT", utc="2026-01-20T00:00:00Z", salt="SEI-SALT",
        supplemental_evidence=[conflict_tax],
    )
    checks["certified_supplemental_conflict_routed"] = (
        conflict_report["supplemental_evidence"]["conflict_count"] == 1
        and conflict_report["decision"] == "CONFLICT_RESOLUTION_REQUIRED"
        and conflict_report["policy_verdict"] == "REQUIRES_REVIEW"
        and not conflict_report["ok"]
    )

    address_report = execute_operator(
        "collin", None, env, address="100 FICTIONAL TEST WAY",
        address_resolver_factory=FabricatedResolver,
        pipeline_factory=factory_for(FabricatedCollinAdapter(), []),
        run_id="SEI-ADDRESS", utc="2026-01-20T00:00:00Z", salt="SEI-SALT",
    )
    account_report = execute_operator(
        "collin", "FABRICATED-ACCOUNT", env,
        pipeline_factory=factory_for(FabricatedCollinAdapter(), []),
        run_id="SEI-ACCOUNT", utc="2026-01-20T00:00:00Z", salt="SEI-SALT",
    )
    checks["existing_selector_regression"] = (
        address_report["resolution"]["status"] == "PASS"
        and account_report["resolution"]["status"] == "ACCOUNT_ID_SUPPLIED"
        and address_report["ok"] and account_report["ok"]
    )

    received = []
    def api_operator(provider, account_id=None, environ=None, address=None, county="Collin",
                     supplemental_evidence=None):
        received.extend(supplemental_evidence or ())
        return {
            "ok": True, "provider": provider, "jurisdiction": "TX-COLLIN",
            "run_id": "API-SEI", "decision": "PENDING_MORE_EVIDENCE",
            "confidence": {"status": "NOT_ASSIGNED"},
        }
    service = EraPropertyApiService(
        {"ERA_API_BEARER_TOKEN": TOKEN}, operator=api_operator,
    )
    request = AnalyzeRequest(
        provider="collin", county="Collin", account_id="FABRICATED-ACCOUNT",
        supplemental_evidence=[LISTING],
    )
    api_result = service.analyze(request, f"Bearer {TOKEN}", "safe-correlation")
    checks["authenticated_api_routes_contract"] = (
        api_result["decision"] == "PENDING_MORE_EVIDENCE"
        and len(received) == 1 and received[0]["evidence_type"] == "listing_financial_summary"
    )
    api_audit = json.dumps(service.audit.events, sort_keys=True)
    checks["api_audit_privacy_safe"] = (
        "480000" not in api_audit and TOKEN not in api_audit
        and "supplemental_evidence_count" in api_audit
    )

    def conflict_api_operator(*args, **kwargs):
        return {
            "ok": False,
            "provider": "collin",
            "jurisdiction": "TX-COLLIN",
            "run_id": "API-SEI-CONFLICT",
            "resolution": {"status": "ACCOUNT_ID_SUPPLIED"},
            "acquisition_status": "PASS",
            "supplemental_evidence": {"conflict_count": 1},
        }
    conflict_service = EraPropertyApiService(
        {"ERA_API_BEARER_TOKEN": TOKEN}, operator=conflict_api_operator,
    )
    try:
        conflict_service.analyze(request, f"Bearer {TOKEN}", "safe-conflict-correlation")
        checks["api_conflict_fails_closed"] = False
    except RuntimeError as exc:
        checks["api_conflict_fails_closed"] = str(exc) == "SUPPLEMENTAL_EVIDENCE_CONFLICT"

    after = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())
    checks["fabricated_sources_unchanged"] = before == after
    checks["no_runtime_database_created"] = not list(root.glob("*.db"))


for name, passed in checks.items():
    print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values())
print(f"SEI-001 CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
