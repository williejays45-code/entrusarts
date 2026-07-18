"""Fabricated-data verification for deterministic Collin address routing."""

import hashlib
import json
import os
import socket
from pathlib import Path

from era.acquisition.provider_health_authority import ReadinessObservation
from era.app import bootstrap_collin_demo, build_app
from era.live_adapters.collin_bulk_data_adapter import (
    COLLIN_ADDRESS_AMBIGUOUS, COLLIN_ADDRESS_NOT_FOUND, CollinBulkDataAdapter,
    normalize_collin_address,
)
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors
from era.run_property import AccountBoundCollinAdapter, COLLIN_PROVIDER, execute_operator


class FakeAcquisition:
    def __init__(self): self.lookups = []
    def provider_id(self): return COLLIN_PROVIDER
    def provider_name(self): return "Fabricated Collin"
    def connector_version(self): return "TEST"
    def health_check(self): return True
    def retrieve(self, account):
        self.lookups.append(account)
        return provider_errors.PASS, {
            "evidence": [
                ProviderEvidence("property_address", "100 N MAIN ST UNIT 2 PLANO TX 75001"),
                ProviderEvidence("city", "PLANO"), ProviderEvidence("county", "Collin"),
                ProviderEvidence("state", "TX"),
                ProviderEvidence("owner_name", "FABRICATED PRIVATE PERSON"),
                ProviderEvidence("current_appraised_value", "100000"),
            ],
            "provenance": {"legal_basis": "PUBLIC_RECORD"},
            "source_reference": f"FABRICATED:{account}",
        }


def pipeline_factory_for(acquisition):
    def factory(_mdb, _xls, account):
        pipeline = build_app(use_mock_auth=True)
        bound = AccountBoundCollinAdapter(acquisition, account)
        pipeline.c.collin_bulk_data_adapter = bound
        pipeline.c.county_connectors[COLLIN_PROVIDER] = bound
        pipeline.c._provider_readiness_observers[COLLIN_PROVIDER] = ReadinessObservation.READY
        bootstrap_collin_demo(pipeline)
        return pipeline
    return factory


class FakeResolver(CollinBulkDataAdapter):
    def __init__(self, _mdb, _xls, rows):
        super().__init__(_mdb, _xls)
        self.rows = rows
    def _query_address_candidates(self, _street_number): return list(self.rows)


root = Path(os.environ.get("ERA_OPERATOR_ADDRESS_TEST_ROOT", "pytest-cache-files-era-address"))
root.mkdir(parents=True, exist_ok=True)
mdb = root / "FABRICATED.mdb"; xls = root / "FABRICATED.xls"
mdb.write_bytes(b"FABRICATED ADDRESS MDB"); xls.write_bytes(b"FABRICATED ADDRESS XLS")
env = {"ERA_COLLIN_MDB_PATH": str(mdb), "ERA_COLLIN_CODE_LIST_PATH": str(xls)}
before = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())
checks = {}

try: execute_operator("collin", None, env)
except ValueError as exc: checks["exactly_one_selector_required"] = str(exc) == "EXACTLY_ONE_SELECTOR_REQUIRED"
try: execute_operator("collin", "A", env, address="100 MAIN ST")
except ValueError as exc: checks["selectors_mutually_exclusive"] = str(exc) == "EXACTLY_ONE_SELECTOR_REQUIRED"
try: execute_operator("unknown", "A", env)
except ValueError as exc: checks["unsupported_provider_fails_closed"] = "SUPPORTED_PROVIDERS=collin" in str(exc)

single_rows = [{"prop_id": "SYNTH-ACCOUNT", "situs_display": "100 N MAIN ST UNIT 2 PLANO TX 75001"}]
resolver = lambda m, x: FakeResolver(m, x, single_rows)
checks["exact_address_match"] = FakeResolver(str(mdb), str(xls), single_rows).resolve_address(single_rows[0]["situs_display"])[0] == "PASS"
checks["case_whitespace_normalization"] = normalize_collin_address("  100 n main st   unit 2 plano tx 75001 ") == normalize_collin_address(single_rows[0]["situs_display"])
checks["direction_suffix_zip_normalization"] = normalize_collin_address("100 North Main Street #2, Plano, TX 75001-0000") == normalize_collin_address(single_rows[0]["situs_display"])
checks["unit_specific_match"] = FakeResolver(str(mdb), str(xls), single_rows).resolve_address("100 N MAIN ST APT 2 PLANO TX 75001")[2] == 1
checks["unit_mismatch_fails"] = FakeResolver(str(mdb), str(xls), single_rows).resolve_address("100 N MAIN ST UNIT 3 PLANO TX 75001")[0] == COLLIN_ADDRESS_NOT_FOUND
checks["no_match_fails"] = FakeResolver(str(mdb), str(xls), single_rows).resolve_address("999 OTHER RD PLANO TX 75001")[0] == COLLIN_ADDRESS_NOT_FOUND
ambiguous_rows = single_rows + [{"prop_id": "SYNTH-OTHER", "situs_display": single_rows[0]["situs_display"]}]
ambiguous = FakeResolver(str(mdb), str(xls), ambiguous_rows).resolve_address(single_rows[0]["situs_display"])
checks["ambiguous_match_count_only"] = ambiguous[0] == COLLIN_ADDRESS_AMBIGUOUS and ambiguous[1] is None and ambiguous[2] == 2

acquisition = FakeAcquisition()
kwargs = dict(provider="collin", address="100 North Main Street #2, Plano TX 75001-0000", environ=env,
              pipeline_factory=pipeline_factory_for(acquisition), address_resolver_factory=resolver,
              run_id="ADDRESS-RUN", utc="2026-01-01T00:00:00+00:00", salt="ADDRESS-SALT")
original = socket.create_connection
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError("NETWORK_FORBIDDEN"))
try:
    first = execute_operator(**kwargs); second = execute_operator(**kwargs)
    checks["no_network_contact"] = True
finally: socket.create_connection = original
checks["acquisition_reasoning_separation"] = acquisition.lookups == ["SYNTH-ACCOUNT", "SYNTH-ACCOUNT"] and any(s["name"] == "ECM" for s in first["pipeline_stages"])
serialized = json.dumps(first, sort_keys=True)
checks["raw_address_redacted"] = kwargs["address"] not in serialized and "FABRICATED PRIVATE PERSON" not in serialized and "SYNTH-ACCOUNT" not in serialized
account_report = execute_operator("collin", "SYNTH-ACCOUNT", env, pipeline_factory_for(FakeAcquisition()), run_id="ACCOUNT", utc=kwargs["utc"], salt=kwargs["salt"])
checks["account_id_regression"] = account_report["ok"] and account_report["resolution"]["status"] == "ACCOUNT_ID_SUPPLIED"
checks["deterministic_repeated_resolution"] = first == second
after = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())
checks["source_database_unchanged"] = before == after

for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values())
print(f"COLLIN ADDRESS OPERATOR CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
