"""Focused verification for the explicit Collin operator path."""

import hashlib
import json
import os
import socket
import tempfile
from contextlib import nullcontext
from pathlib import Path

from era.acquisition.provider_health_authority import ReadinessObservation
from era.app import bootstrap_collin_demo, build_app
from era.live_adapters.collin_bulk_data_adapter import COLLIN_RECORD_NOT_FOUND
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors
from era.run_property import (
    AccountBoundCollinAdapter, COLLIN_PROVIDER, execute_operator,
)


class FabricatedCollinAdapter:
    def __init__(self, found=True):
        self.found = found
        self.lookups = []

    def provider_id(self): return COLLIN_PROVIDER
    def provider_name(self): return "Fabricated Collin Test Provider"
    def connector_version(self): return "TEST-1"
    def health_check(self): return True
    def retrieve(self, account_id):
        self.lookups.append(account_id)
        if not self.found:
            return COLLIN_RECORD_NOT_FOUND, {}
        return provider_errors.PASS, {
            "evidence": [
                ProviderEvidence("property_address", "999 FICTIONAL TEST ROAD"),
                ProviderEvidence("city", "TESTVILLE"),
                ProviderEvidence("county", "Collin"),
                ProviderEvidence("state", "TX"),
                ProviderEvidence("owner_name", "FABRICATED PERSON ONLY"),
                ProviderEvidence("owner_mailing_address", "123 NEVER REAL LANE"),
                ProviderEvidence("current_appraised_value", "123456"),
            ],
            "provenance": {"legal_basis": "PUBLIC_RECORD"},
            "source_reference": f"FABRICATED:{account_id}",
        }


def factory_for(adapter):
    def factory(_mdb, _xls, account_id):
        pipeline = build_app(use_mock_auth=True)
        bound = AccountBoundCollinAdapter(adapter, account_id)
        pipeline.c.collin_bulk_data_adapter = bound
        pipeline.c.county_connectors[COLLIN_PROVIDER] = bound
        pipeline.c._provider_readiness_observers[COLLIN_PROVIDER] = ReadinessObservation.READY
        bootstrap_collin_demo(pipeline)
        return pipeline
    return factory


checks = {}
try:
    execute_operator(None, "A", {})
    checks["missing_provider_fails_closed"] = False
except ValueError as exc:
    checks["missing_provider_fails_closed"] = str(exc) == "PROVIDER_REQUIRED"
try:
    execute_operator("collin", None, {})
    checks["missing_account_id_fails_closed"] = False
except ValueError as exc:
    checks["missing_account_id_fails_closed"] = str(exc) == "ACCOUNT_ID_REQUIRED"
try:
    execute_operator("collin", "A", {})
    checks["missing_environment_paths_fail_closed"] = False
except ValueError as exc:
    checks["missing_environment_paths_fail_closed"] = str(exc) == "COLLIN_SOURCE_PATHS_REQUIRED"

configured_root = os.environ.get("ERA_OPERATOR_TEST_TMP")
root_context = nullcontext(configured_root) if configured_root else tempfile.TemporaryDirectory(prefix="era-operator-")
with root_context as root:
    root = Path(root)
    mdb = root / "FABRICATED_SOURCE.mdb"
    xls = root / "FABRICATED_CODES.xls"
    mdb.write_bytes(b"FABRICATED MDB TEST BYTES")
    xls.write_bytes(b"FABRICATED XLS TEST BYTES")
    env = {"ERA_COLLIN_MDB_PATH": str(mdb), "ERA_COLLIN_CODE_LIST_PATH": str(xls)}
    before = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())

    missing = FabricatedCollinAdapter(found=False)
    missing_report = execute_operator(
        "collin", "SYNTH-NOT-FOUND", env, factory_for(missing),
        run_id="RUN-MISSING", utc="2026-01-01T00:00:00+00:00", salt="missing-salt",
    )
    checks["account_not_found_reported"] = missing_report["acquisition_status"] == COLLIN_RECORD_NOT_FOUND

    adapter = FabricatedCollinAdapter()
    kwargs = dict(
        provider="collin", account_id="SYNTH-ACCOUNT-001", environ=env,
        pipeline_factory=factory_for(adapter), run_id="RUN-FIXED",
        utc="2026-01-01T00:00:00+00:00", salt="fixed-test-salt",
    )
    original_create_connection = socket.create_connection
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError("NETWORK_FORBIDDEN"))
    try:
        first = execute_operator(**kwargs)
        second = execute_operator(**kwargs)
        checks["no_network_access"] = True
    except AssertionError:
        checks["no_network_access"] = False
        raise
    finally:
        socket.create_connection = original_create_connection

    checks["source_hash_provenance_captured"] = {
        item["sha256"] for item in first["source_files"]
    } == {value.upper() for value in before}
    checks["successful_normalized_collin_acquisition"] = first["acquisition_status"] == "PASS" and first["ok"]
    checks["acquisition_reasoning_boundary_preserved"] = (
        adapter.lookups == ["SYNTH-ACCOUNT-001", "SYNTH-ACCOUNT-001"]
        and any(stage["name"] == "ECM" and stage["ok"] for stage in first["pipeline_stages"])
    )
    serialized = json.dumps(first, sort_keys=True)
    checks["pii_redacted"] = all(value not in serialized for value in (
        "FABRICATED PERSON ONLY", "123 NEVER REAL LANE", "999 FICTIONAL TEST ROAD",
        "SYNTH-ACCOUNT-001",
    ))
    checks["pending_export_labeled_informational"] = (
        first["decision"] == "PENDING_MORE_EVIDENCE"
        and first["export_label"].startswith("INFORMATIONAL INCOMPLETE-EVIDENCE REPORT")
    )
    checks["deterministic_repeated_execution"] = first == second
    after = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())
    checks["source_database_not_mutated"] = before == after
    checks["no_source_records_persisted"] = not list(root.glob("*.db"))

for name, passed in checks.items():
    print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values())
print(f"COLLIN OPERATOR CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
