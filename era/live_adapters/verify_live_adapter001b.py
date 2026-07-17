import sys
import os
import io
import zipfile
import pandas as pd
from era.live_adapters.dcad_bulk_data_adapter import DCADBulkDataAdapter, ACCOUNT_APPRL_YEAR_FIELD_MAP as FIELD_MAP
from era.live_adapters.dcad_bulk_data_models import DCADAccountMapping
from era.live_adapters import dcad_bulk_errors as errors
from era.network.mock_transport import MockHttpTransport
from era.network.network_models import HttpResponse
from era.network import network_errors as network_errors
from era.app import build_app, bootstrap_dcad_demo
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType
from era.acquisition.connector_models import RetryPolicy
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import MockTokenStore
from era.live_adapters.dcad_test_data import resolve_dcad_test_paths
APPR_PATH, INFO_PATH, USING_FULL_DCAD_DATA = resolve_dcad_test_paths()

print("LIVE-ADAPTER-001B VERIFICATION -- DCAD Data Products (2025 Certified)")
print("=" * 70)

checks = {}

URL = "https://www.dallascad.org/data-products/2025-certified.zip"  # placeholder -- never asserted real, see adapter docstring
ADMIN_TOKEN = "admin-token"

# --- Build a REAL test ZIP from REAL excerpted rows of the actual
# uploaded certified CSV -- not synthetic data. -----------------------------
real_df = pd.read_csv(APPR_PATH, dtype=str, nrows=50)
real_rows = real_df.iloc[[0, 1, 2]]
REAL_ACCOUNT_1 = str(real_rows.iloc[0]["ACCOUNT_NUM"])
REAL_TOT_VAL_1 = str(real_rows.iloc[0]["TOT_VAL"])
REAL_CITY_1 = str(real_rows.iloc[0]["CITY_JURIS_DESC"]).strip()
REAL_COUNTY_1 = str(real_rows.iloc[0]["COUNTY_JURIS_DESC"]).strip()


def build_real_zip(rows=real_rows, entry_name="ACCOUNT_APPRL_YEAR.CSV"):
    csv_bytes = rows.to_csv(index=False).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(entry_name, csv_bytes)
    return buf.getvalue()


REAL_ZIP = build_real_zip()


import tempfile
_temp_db_paths = []


def new_adapter(zip_bytes=REAL_ZIP, entry_name=None):
    transport = MockHttpTransport()
    transport.set_response(URL, HttpResponse(200, "", content=zip_bytes))
    fd, index_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(index_db_path)
    _temp_db_paths.append(index_db_path)
    kwargs = {"download_url": URL, "transport": transport, "index_db_path": index_db_path,
              "auth": AuthEngine(token_store=MockTokenStore())}
    if entry_name:
        kwargs["target_entry_name"] = entry_name
    return DCADBulkDataAdapter(**kwargs)


# --- 1. Missing account mapping blocked. ----------------------------------
adapter = new_adapter()
status, payload = adapter.retrieve("ERA-PR-NEVER-REGISTERED")
checks["missing_account_mapping_blocked"] = status == errors.ACCOUNT_MAPPING_REQUIRED and payload == {}

# --- 2. Malformed ZIP blocked cleanly (reuses NETWORK-001B's validation,
# confirmed here at the adapter level, not just the transport level). ------
bad_zip_adapter = new_adapter(zip_bytes=b"NOT-A-REAL-ZIP-FILE")
bad_zip_adapter.register_account_mapping(DCADAccountMapping("ERA-PR-BADZIP", REAL_ACCOUNT_1, "2025"), ADMIN_TOKEN)
status, payload = bad_zip_adapter.retrieve("ERA-PR-BADZIP")
checks["malformed_zip_blocked_cleanly"] = status == network_errors.TRANSPORT_INVALID_RESPONSE and payload == {}

# --- 3. Target entry not found in ZIP blocked cleanly. ---------------------
wrong_entry_zip = build_real_zip(entry_name="SOME_OTHER_TABLE.CSV")
missing_entry_adapter = new_adapter(zip_bytes=wrong_entry_zip)
missing_entry_adapter.register_account_mapping(DCADAccountMapping("ERA-PR-NOENTRY", REAL_ACCOUNT_1, "2025"), ADMIN_TOKEN)
status, payload = missing_entry_adapter.retrieve("ERA-PR-NOENTRY")
checks["zip_entry_not_found_blocked_cleanly"] = status == errors.ZIP_ENTRY_NOT_FOUND and payload == {}

# --- 4. Malformed CSV header blocked cleanly. -------------------------------
bad_header_buf = io.BytesIO()
with zipfile.ZipFile(bad_header_buf, "w") as z:
    z.writestr("ACCOUNT_APPRL_YEAR.CSV", "NOT,THE,RIGHT,COLUMNS\n1,2,3,4\n")
bad_header_adapter = new_adapter(zip_bytes=bad_header_buf.getvalue())
bad_header_adapter.register_account_mapping(DCADAccountMapping("ERA-PR-BADHEADER", REAL_ACCOUNT_1, "2025"), ADMIN_TOKEN)
status, payload = bad_header_adapter.retrieve("ERA-PR-BADHEADER")
checks["malformed_csv_header_blocked_cleanly"] = status == errors.MALFORMED_CSV_HEADER and payload == {}

# --- 5. Account not found in dataset blocked cleanly. -----------------------
notfound_adapter = new_adapter()
notfound_adapter.register_account_mapping(DCADAccountMapping("ERA-PR-NOTFOUND", "0000000000000NOPE", "2025"), ADMIN_TOKEN)
status, payload = notfound_adapter.retrieve("ERA-PR-NOTFOUND")
checks["account_not_found_blocked_cleanly"] = status == errors.ACCOUNT_NOT_FOUND and payload == {}

# --- 6. Read-only enforced. --------------------------------------------------
write_ok, write_reason = new_adapter().attempt_write()
checks["read_only_enforced"] = write_ok is False and write_reason == errors.READ_ONLY_ADAPTER

# --- 7. Confidence authority blocked. ----------------------------------------
conf_ok, conf_reason = new_adapter().assign_confidence()
checks["confidence_authority_blocked"] = (
    conf_ok is False and conf_reason == errors.CONFIDENCE_AUTHORITY_VIOLATION
)

# --- 8. Real data retrieval succeeds, with genuinely correct real values. ---
real_adapter = new_adapter()
real_adapter.register_account_mapping(DCADAccountMapping("ERA-PR-REAL-001", REAL_ACCOUNT_1, "2025"), ADMIN_TOKEN)
status, payload = real_adapter.retrieve("ERA-PR-REAL-001")
checks["real_data_retrieval_succeeds"] = status == "PASS"
evidence_by_field = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["real_city_value_correct"] = evidence_by_field.get("city") == REAL_CITY_1
checks["real_county_value_correct"] = evidence_by_field.get("county") == REAL_COUNTY_1
checks["real_total_value_present_and_correct"] = evidence_by_field.get("total_appraised_value") == REAL_TOT_VAL_1
checks["real_parcel_id_matches_account_num"] = evidence_by_field.get("parcel_id") == REAL_ACCOUNT_1
checks["state_constant_present"] = evidence_by_field.get("state") == "TX"
checks["source_reference_includes_account_and_year"] = (
    REAL_ACCOUNT_1 in payload["source_reference"] and "2025" in payload["source_reference"]
)

# --- 9. Honest gaps: property_address and property_type are never
# fabricated, even though they'd be needed for a full ERA identity. --------
checks["no_fabricated_property_address"] = "property_address" not in evidence_by_field
checks["no_fabricated_property_type"] = "property_type" not in evidence_by_field

# --- 10. Second retrieve() for a different account reuses the cached
# index rather than re-downloading (only one transport call total). --------
real_adapter.register_account_mapping(DCADAccountMapping(
    "ERA-PR-REAL-002", str(real_rows.iloc[1]["ACCOUNT_NUM"]), "2025"
), ADMIN_TOKEN)
real_adapter.retrieve("ERA-PR-REAL-002")
checks["dataset_indexed_once_not_per_lookup"] = len(real_adapter._transport.sent_requests) == 1

# --- Container wiring is opt-in: no URL, no adapter registered. ------------
no_url_app = build_app()
checks["no_dcad_url_means_no_adapter_registered"] = no_url_app.c.dcad_bulk_data_adapter is None
checks["no_dcad_url_means_not_in_provider_registry"] = "DCAD_BULK_DATA_2025" not in no_url_app.c.county_connectors

# --- 11. Full real pipeline integration: rate limit + retry still apply
# (not reimplemented by this adapter), and the honest real outcome is
# INSUFFICIENT_EVIDENCE (missing property_address), not a crash and not
# a fabricated success. -------------------------------------------------------
_pipeline_index_fd, _pipeline_index_path = tempfile.mkstemp(suffix=".db")
os.close(_pipeline_index_fd)
os.remove(_pipeline_index_path)
_temp_db_paths.append(_pipeline_index_path)
pipeline_app = build_app(dcad_download_url=URL, dcad_index_db_path=_pipeline_index_path, token_store=MockTokenStore())
bootstrap_dcad_demo(pipeline_app)
pipeline_app.c.dcad_bulk_data_adapter._transport = MockHttpTransport()
pipeline_app.c.dcad_bulk_data_adapter._transport.set_response(URL, HttpResponse(200, "", content=REAL_ZIP))
pipeline_app.c.dcad_bulk_data_adapter.register_account_mapping(
    DCADAccountMapping("ERA-PR-2026-DCAD-001", REAL_ACCOUNT_1, "2025"), ADMIN_TOKEN
)
identity = PropertyIdentity(
    property_id="ERA-PR-2026-DCAD-001", address="UNKNOWN", city="Dallas", state="TX",
    zip_code="00000", county="Dallas", parcel_apn=REAL_ACCOUNT_1, latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)
result = pipeline_app.run_property(
    property_id=identity.property_id, identity=identity,
    state="TX", county="Dallas", provider_id="DCAD_BULK_DATA_2025",
)
checks["pipeline_reaches_lpa_and_ecm"] = (
    result.stage("LPA") is not None and result.stage("LPA").ok
    and result.stage("ECM") is not None and result.stage("ECM").ok
)
checks["text_fields_reach_provenance"] = any(
    pr.canonical_field in {"city", "county", "state", "parcel_id"} for pr in result.provenance_records
)
# ECM-TYPE-001 closed the numeric-leakage collision this suite
# originally documented as a known gap -- now that DCAD's value fields
# are submitted with the correct CURRENCY/IDENTIFIER value_type, they
# correctly PASS canonicalization instead of being rejected. This test
# was rewritten (not left asserting the old, now-incorrect behavior)
# to confirm the fix actually took effect at the pipeline level, not
# just inside canonical_engine.py in isolation.
checks["numeric_value_fields_now_pass_ecm_after_ecm_type_001"] = all(
    s.ok for s in result.stages
    if s.name.startswith("ECM:") and s.name.split(":")[1] in
    {"total_appraised_value", "land_value", "improvement_value"}
) and any(
    pr.canonical_field in {"total_appraised_value", "land_value", "improvement_value"}
    for pr in result.provenance_records
)
checks["value_fields_carry_correct_types"] = all(
    r.value_type.value == "CURRENCY"
    for r in result.canonical_records
    if r.field_name in {"total_appraised_value", "land_value", "improvement_value"}
) and any(
    r.value_type.value == "IDENTIFIER" for r in result.canonical_records if r.field_name == "parcel_id"
)
checks["honest_insufficient_evidence_not_fabricated_success"] = (
    result.decision_record is not None and result.decision_record.decision.value == "INSUFFICIENT_EVIDENCE"
)
checks["rate_limit_gate_applied_to_dcad_too"] = (
    result.stage("RATE_LIMIT") is not None and result.stage("RATE_LIMIT").ok
)

# --- 12. Retry wrapper still used for DCAD fetches -- a transient
# download failure recovers through the same RetryExecutor every other
# provider uses, not a DCAD-specific retry loop. -----------------------------
retry_adapter = new_adapter()
retry_adapter.register_account_mapping(DCADAccountMapping("ERA-PR-RETRY", REAL_ACCOUNT_1, "2025"), ADMIN_TOKEN)
flaky_log = {"n": 0}
real_fetch = retry_adapter._fetch_and_index
def flaky_fetch():
    flaky_log["n"] += 1
    if flaky_log["n"] < 2:
        return "PROVIDER_UNAVAILABLE"
    return real_fetch()
retry_adapter._fetch_and_index = flaky_fetch

from era.acquisition.retry_executor import RetryExecutor
from era.shared.audit import BaseAuditPublisher
executor = RetryExecutor(audit=BaseAuditPublisher())
retry_policy = RetryPolicy(max_retries=3, retry_delay_seconds=1)
status, payload = executor.run(
    "DCAD_BULK_DATA_2025", retry_policy, lambda: retry_adapter.retrieve("ERA-PR-RETRY")
)
checks["retry_wrapper_recovers_transient_dcad_fetch_failure"] = (
    status == "PASS" and flaky_log["n"] == 2
)

for _path in _temp_db_paths:
    for _suffix in ("", "-wal", "-shm"):
        if os.path.exists(_path + _suffix):
            os.remove(_path + _suffix)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"LIVE-ADAPTER-001B CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
