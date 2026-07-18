"""Explicit, privacy-preserving ERA property operator command."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from era.acquisition.provider_health_authority import ReadinessObservation
from era.acquisition.supplemental_evidence import SupplementalEvidenceNormalizer
from era.app import bootstrap_collin_demo, build_app
from era.live_adapters.collin_bulk_data_adapter import CollinBulkDataAdapter
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record.property_models import PropertyIdentity


COLLIN_PROVIDER = "COLLIN_BULK_MDB"
PRIVATE_FIELDS = frozenset({
    "owner_name", "owner_mailing_address", "owner_mailing_city",
    "owner_mailing_state", "owner_mailing_zip_code", "property_address",
    "legal_description", "source_record_id", "parcel_id", "zip_code",
})
EXPECTED_FIELDS = frozenset({"city", "state", "current_appraised_value", "certified_appraised_value"})
PROVIDER_ROUTES = {"collin": {"provider_id": COLLIN_PROVIDER, "county": "Collin", "jurisdiction": "TX-COLLIN"}}


def _sha256_file(path: str, operation_control=None) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            if operation_control:
                operation_control.check()
            digest.update(block)
    return digest.hexdigest().upper()


class AccountBoundCollinAdapter:
    """Acquisition-side binding from an opaque run property ID to an operator account ID."""

    def __init__(self, adapter, account_id: str):
        self._adapter = adapter
        self._account_id = account_id

    def provider_id(self):
        return self._adapter.provider_id()

    def provider_name(self):
        return self._adapter.provider_name()

    def connector_version(self):
        return self._adapter.connector_version()

    def health_check(self):
        return True

    def set_operation_control(self, operation_control):
        setter = getattr(self._adapter, "set_operation_control", None)
        if setter:
            setter(operation_control)

    def retrieve(self, opaque_property_id):
        retrieve = self._adapter.retrieve
        if "audit_property_id" in inspect.signature(retrieve).parameters:
            return retrieve(self._account_id, audit_property_id=opaque_property_id)
        return retrieve(self._account_id)


def build_operator_pipeline(mdb_path: str, code_path: str, account_id: str):
    pipeline = build_app(
        use_mock_auth=True,
        collin_mdb_path=mdb_path,
        collin_code_list_path=code_path,
    )
    bound = AccountBoundCollinAdapter(pipeline.c.collin_bulk_data_adapter, account_id)
    pipeline.c.collin_bulk_data_adapter = bound
    pipeline.c.county_connectors[COLLIN_PROVIDER] = bound
    pipeline.c._provider_readiness_observers[COLLIN_PROVIDER] = ReadinessObservation.READY
    bootstrap_collin_demo(pipeline)
    return pipeline


def execute_operator(provider, account_id=None, environ=None, pipeline_factory=build_operator_pipeline,
                     run_id=None, utc=None, salt=None, address=None, county="Collin",
                     address_resolver_factory=CollinBulkDataAdapter,
                     supplemental_evidence=None,
                     supplemental_normalizer_factory=SupplementalEvidenceNormalizer,
                     operation_control=None):
    environ = os.environ if environ is None else environ
    if operation_control:
        operation_control.check()
    if not provider:
        raise ValueError("PROVIDER_REQUIRED")
    route = PROVIDER_ROUTES.get(str(provider).lower())
    if route is None:
        raise ValueError("UNSUPPORTED_PROVIDER;SUPPORTED_PROVIDERS=collin")
    if str(county).strip().lower() != route["county"].lower():
        raise ValueError("UNSUPPORTED_COUNTY;SUPPORTED_COUNTIES=Collin")
    has_account = bool(account_id and str(account_id).strip())
    has_address = bool(address and str(address).strip())
    if has_account == has_address:
        raise ValueError("EXACTLY_ONE_SELECTOR_REQUIRED")
    mdb_path = environ.get("ERA_COLLIN_MDB_PATH")
    code_path = environ.get("ERA_COLLIN_CODE_LIST_PATH")
    if not mdb_path or not code_path:
        raise ValueError("COLLIN_SOURCE_PATHS_REQUIRED")
    if not Path(mdb_path).is_file() or not Path(code_path).is_file():
        raise ValueError("COLLIN_SOURCE_PATH_NOT_FOUND")
    source_files = [
        {"name": Path(mdb_path).name, "sha256": _sha256_file(mdb_path, operation_control)},
        {"name": Path(code_path).name, "sha256": _sha256_file(code_path, operation_control)},
    ]
    if operation_control:
        operation_control.check()

    run_id = run_id or f"ERA-RUN-{uuid.uuid4().hex}"
    utc = utc or datetime.now(timezone.utc).isoformat()
    salt = salt or uuid.uuid4().hex
    resolution_status = "ACCOUNT_ID_SUPPLIED"
    match_count = 1
    selector_identity = {
        "account_identity": {
            "scheme": "SHA-256-RUN-SALTED",
            "hash": hashlib.sha256(f"{salt}:{account_id}".encode()).hexdigest(),
        }
    }
    if has_address:
        selector_identity = {
            "address_identity": {
                "scheme": "SHA-256-RUN-SALTED",
                "hash": hashlib.sha256(f"{salt}:{address}".encode()).hexdigest(),
            }
        }
        resolver = address_resolver_factory(mdb_path, code_path)
        resolver_control = getattr(resolver, "set_operation_control", None)
        if resolver_control:
            resolver_control(operation_control)
        resolution_status, account_id, match_count = resolver.resolve_address(address)
        if operation_control:
            operation_control.check()
        if resolution_status != "PASS":
            return {
                "run_id": run_id, "utc": utc, "provider": str(provider).lower(),
                "provider_id": route["provider_id"], "jurisdiction": route["jurisdiction"],
                **selector_identity,
                "resolution": {"status": resolution_status, "match_count": match_count},
                "source_files": source_files,
                "acquisition_status": "NOT_STARTED", "evidence_sufficiency": None,
                "pipeline_stages": [], "decision": None,
                "confidence": {"status": "NOT_ASSIGNED", "reason": "Acquisition did not produce evidence"},
                "policy_verdict": None, "export_status": None, "export_label": None,
                "limitations": ["Address resolution failed closed; no candidate identities disclosed"],
                "ok": False,
            }
    opaque_property_id = f"OP-COLLIN-{hashlib.sha256((run_id + salt).encode()).hexdigest()[:20]}"
    supplemental_package = supplemental_normalizer_factory().normalize(
        opaque_property_id, supplemental_evidence or (),
    )
    if operation_control:
        operation_control.check()
    pipeline = pipeline_factory(mdb_path, code_path, str(account_id))
    pipeline_adapter = getattr(pipeline.c, "collin_bulk_data_adapter", None)
    adapter_control = getattr(pipeline_adapter, "set_operation_control", None)
    if adapter_control:
        adapter_control(operation_control)
    if operation_control:
        operation_control.check()
    identity = PropertyIdentity(
        property_id=opaque_property_id,
        address="WITHHELD OPERATOR ACQUISITION",
        city="Collin County", state="TX", zip_code="00000", county="Collin",
        parcel_apn=None, latitude=None, longitude=None,
        property_type=PropertyType.OTHER, strategy_type=StrategyType.OTHER,
    )
    result = pipeline.run_property(
        opaque_property_id, identity, "TX", "Collin", COLLIN_PROVIDER,
        supplemental_package=(supplemental_package if supplemental_package.items else None),
        operation_control=operation_control,
    )
    if operation_control:
        operation_control.check()
    canonical = list(result.canonical_records)
    present_fields = {record.field_name for record in canonical}
    safe_facts = sorted(
        (record.field_name, str(record.normalized_value))
        for record in canonical if record.field_name not in PRIVATE_FIELDS
    )
    facts_hash = hashlib.sha256(
        json.dumps(safe_facts, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest().upper()
    decision = result.decision_record.decision.value if result.decision_record else None
    export_status = result.export_package.status.value if result.export_package else None
    pending = decision == "PENDING_MORE_EVIDENCE"
    lpa = result.stage("LPA")
    report = {
        "run_id": run_id,
        "utc": utc,
        "provider": str(provider).lower(),
        "provider_id": route["provider_id"],
        "jurisdiction": route["jurisdiction"],
        **selector_identity,
        "resolution": {"status": resolution_status, "match_count": match_count},
        "source_files": source_files,
        "acquisition_status": lpa.status if lpa else "NOT_REACHED",
        "evidence_sufficiency": {
            "normalized_field_count": len(canonical),
            "expected_fields_present": sorted(EXPECTED_FIELDS & present_fields),
            "missing_expected_fields": sorted(EXPECTED_FIELDS - present_fields),
            "sufficient_for_pipeline": bool(canonical),
            "normalized_non_personal_facts_sha256": facts_hash,
        },
        "pipeline_stages": [
            {"name": stage.name, "status": stage.status, "ok": stage.ok}
            for stage in result.stages
        ],
        "decision": decision,
        "confidence": {"status": "NOT_ASSIGNED", "reason": "ERA decision contract has no confidence field"},
        "policy_verdict": result.policy_result.verdict.value if result.policy_result else None,
        "export_status": export_status,
        "export_label": (
            "INFORMATIONAL INCOMPLETE-EVIDENCE REPORT — NOT A FINAL PROPERTY DETERMINATION"
            if pending and export_status == "EXPORTED" else None
        ),
        "limitations": [
            "Single public-record source only",
            "Owner, telephone, mailing-address, raw-row, parcel, and legal-description values withheld",
            "No confidence score exists in the established ERA decision contract",
        ],
        "ok": result.ok,
    }
    if supplemental_package.items:
        report["supplemental_evidence"] = {
            "accepted_item_count": len(supplemental_package.items),
            "accepted_record_count": len(supplemental_package.records),
            "evidence_types": sorted(item.evidence_type for item in supplemental_package.items),
            "verification_statuses": sorted(set(
                item.verification_status for item in supplemental_package.items
            )),
            "authority": "NON_OVERRIDE_UNVERIFIED",
            "conflict_count": len(result.conflict_reports),
        }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--county", default="Collin")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--account-id")
    selector.add_argument("--address")
    args = parser.parse_args(argv)
    try:
        report = execute_operator(args.provider, args.account_id, address=args.address, county=args.county)
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc).split(":", 1)[0]}, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
