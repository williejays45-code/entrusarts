import sys
import io
import os
import tempfile
import zipfile
import pandas as pd
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import MockTokenStore
from decimal import Decimal
from era.live_adapters.dcad_bulk_data_adapter import DCADBulkDataAdapter
from era.live_adapters.dcad_bulk_data_models import DCADAccountMapping
from era.live_adapters import dcad_bulk_errors as errors
from era.network.mock_transport import MockHttpTransport
from era.network.network_models import HttpResponse
from era.app import build_app, bootstrap_dcad_demo
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType

print("DCAD-JOIN-001 VERIFICATION -- Account_Apprl_Year + Account_Info")
print("=" * 70)

checks = {}
URL = "https://www.dallascad.org/data-products/2025-certified.zip"  # placeholder, never asserted real

from era.live_adapters.dcad_test_data import (
    SYNTHETIC_ACCOUNT_BASELINE, SYNTHETIC_ACCOUNT_HALF, SYNTHETIC_ACCOUNT_UNIT,
    SYNTHETIC_BASE_ADDRESS, SYNTHETIC_BASE_LEGAL, SYNTHETIC_BASE_OWNER,
    SYNTHETIC_CITY, SYNTHETIC_HALF_ADDRESS_PREFIX, SYNTHETIC_UNIT_ADDRESS,
    resolve_dcad_test_paths,
)
APPR_PATH, INFO_PATH, USING_FULL_DCAD_DATA = resolve_dcad_test_paths()

# Real accounts, confirmed directly against the actual uploaded files
# (see conversation history for the independent verification of each).
ACCT_BASELINE = "00000416479000000" if USING_FULL_DCAD_DATA else SYNTHETIC_ACCOUNT_BASELINE
ACCT_UNIT_BLDG = "60001000011030000" if USING_FULL_DCAD_DATA else SYNTHETIC_ACCOUNT_UNIT
ACCT_HALFNUM = "99131207600000000" if USING_FULL_DCAD_DATA else SYNTHETIC_ACCOUNT_HALF
ADMIN_TOKEN = "admin-token"     # real STREET_HALF_NUM="A" (and coincidentally UNIT_ID="A" too)
EXPECTED_BASE_OWNER = "MEDITZ RICHARD A" if USING_FULL_DCAD_DATA else SYNTHETIC_BASE_OWNER
EXPECTED_BASE_ADDRESS = "4562 CATINA LN" if USING_FULL_DCAD_DATA else SYNTHETIC_BASE_ADDRESS
EXPECTED_UNIT_ADDRESS = (
    "4712 ABBOTT AVE BLDG A UNIT 103" if USING_FULL_DCAD_DATA else SYNTHETIC_UNIT_ADDRESS
)
EXPECTED_HALF_PREFIX = "44A " if USING_FULL_DCAD_DATA else SYNTHETIC_HALF_ADDRESS_PREFIX
EXPECTED_CITY = "DALLAS" if USING_FULL_DCAD_DATA else SYNTHETIC_CITY
EXPECTED_BASE_LEGAL = (
    "WILSON ESTATES | BLK D/5534  LT 4 | CATINA LN & WELCH RD | "
    "VOL95069/3403 DD032995 CO-DALLAS | 5534 00D   004        1005534 00D"
    if USING_FULL_DCAD_DATA else SYNTHETIC_BASE_LEGAL
)

appr_df = pd.read_csv(APPR_PATH, dtype=str)
info_df = pd.read_csv(INFO_PATH, dtype=str)


def build_zip(appr_accounts, info_accounts, extra_appr_rows=None, extra_info_rows=None,
              duplicate_info_account=None):
    appr_subset = appr_df[appr_df["ACCOUNT_NUM"].isin(appr_accounts)].copy()
    info_subset = info_df[info_df["ACCOUNT_NUM"].isin(info_accounts)].copy()
    if extra_appr_rows:
        appr_subset = pd.concat([appr_subset, pd.DataFrame(extra_appr_rows)], ignore_index=True)
    if extra_info_rows:
        info_subset = pd.concat([info_subset, pd.DataFrame(extra_info_rows)], ignore_index=True)
    if duplicate_info_account:
        dup_row = info_df[info_df["ACCOUNT_NUM"] == duplicate_info_account]
        info_subset = pd.concat([info_subset, dup_row], ignore_index=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ACCOUNT_APPRL_YEAR.CSV", appr_subset.to_csv(index=False))
        z.writestr("ACCOUNT_INFO.CSV", info_subset.to_csv(index=False))
    return buf.getvalue()


import tempfile
_temp_db_paths = []


def new_joined_adapter(zip_bytes):
    transport = MockHttpTransport()
    transport.set_response(URL, HttpResponse(200, "", content=zip_bytes))
    fd, index_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(index_db_path)
    _temp_db_paths.append(index_db_path)
    return DCADBulkDataAdapter(download_url=URL, transport=transport, join_account_info=True, index_db_path=index_db_path, auth=AuthEngine(token_store=MockTokenStore()))


# --- 1. Exact join succeeds (real data, all three real edge-case
# accounts in one dataset). --------------------------------------------------
main_accounts = [ACCT_BASELINE, ACCT_UNIT_BLDG, ACCT_HALFNUM]
main_zip = build_zip(main_accounts, main_accounts)
adapter = new_joined_adapter(main_zip)
adapter.register_account_mapping(DCADAccountMapping("P-BASELINE", ACCT_BASELINE, "2025"), ADMIN_TOKEN)
status, payload = adapter.retrieve("P-BASELINE")
checks["exact_join_succeeds"] = status == "PASS"
evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["joined_evidence_includes_both_tables_data"] = (
    "total_appraised_value" in evidence and "property_address" in evidence
)

# --- 2. Wrong appraisal year does not join. ----------------------------------
wrong_year_adapter = new_joined_adapter(main_zip)
wrong_year_adapter.register_account_mapping(DCADAccountMapping("P-WRONGYEAR", ACCT_BASELINE, "2024"), ADMIN_TOKEN)
status, payload = wrong_year_adapter.retrieve("P-WRONGYEAR")
checks["wrong_appraisal_year_does_not_join"] = status == errors.ACCOUNT_NOT_FOUND and payload == {}

# --- 3. Leading-zero ACCOUNT_NUM survives (through the join, not just
# single-table retrieval -- confirms parcel_id from Account_Apprl_Year
# and the join key itself both preserve it end to end). ----------------------
checks["leading_zero_account_num_survives_join"] = evidence.get("parcel_id") == ACCT_BASELINE
checks["leading_zero_preserved_as_string_type"] = isinstance(evidence.get("parcel_id"), str)

# --- 4. Owner fields preserved. -----------------------------------------------
checks["owner_name_preserved_selected_data"] = evidence.get("owner_name") == EXPECTED_BASE_OWNER

# Dual-owner path: real data has ZERO rows with OWNER_NAME2 populated
# (confirmed directly against the full 858,533-row file). Tested here
# against a synthetic row for that reason -- flagged as such, not
# presented as a real DCAD record.
synthetic_dual_owner_info = {
    "ACCOUNT_NUM": "99999999999999999", "APPRAISAL_YR": "2025", "DIVISION_CD": "RES",
    "OWNER_NAME1": "SMITH JOHN", "OWNER_NAME2": "SMITH JANE",
    "STREET_NUM": "100", "FULL_STREET_NAME": "SYNTHETIC ST", "PROPERTY_CITY": "DALLAS",
    "PROPERTY_ZIPCODE": "752010000", "GIS_PARCEL_ID": "99999999999999999",
}
synthetic_dual_owner_appr = {
    "ACCOUNT_NUM": "99999999999999999", "APPRAISAL_YR": "2025",
    "TOT_VAL": "100000.00", "LAND_VAL": "50000.00", "IMPR_VAL": "50000.00",
    "CITY_JURIS_DESC": "DALLAS", "COUNTY_JURIS_DESC": "DALLAS COUNTY",
    "GIS_PARCEL_ID": "99999999999999999",
}
dual_zip = build_zip([], [], extra_appr_rows=[synthetic_dual_owner_appr],
                      extra_info_rows=[synthetic_dual_owner_info])
dual_adapter = new_joined_adapter(dual_zip)
dual_adapter.register_account_mapping(DCADAccountMapping("P-DUAL", "99999999999999999", "2025"), ADMIN_TOKEN)
status, payload = dual_adapter.retrieve("P-DUAL")
dual_evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["dual_owner_synthetic_case_combined_correctly"] = (
    dual_evidence.get("owner_name") == "SMITH JOHN; SMITH JANE"
)

# --- 5. Situs address assembled correctly (real data, baseline case). -------
checks["situs_address_assembled_baseline"] = evidence.get("property_address") == EXPECTED_BASE_ADDRESS

# --- 6. Unit/building components handled (real data). -----------------------
unit_adapter = new_joined_adapter(main_zip)
unit_adapter.register_account_mapping(DCADAccountMapping("P-UNIT", ACCT_UNIT_BLDG, "2025"), ADMIN_TOKEN)
status, payload = unit_adapter.retrieve("P-UNIT")
unit_evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["unit_and_building_components_in_address"] = (
    unit_evidence.get("property_address") == EXPECTED_UNIT_ADDRESS
)

halfnum_adapter = new_joined_adapter(main_zip)
halfnum_adapter.register_account_mapping(DCADAccountMapping("P-HALF", ACCT_HALFNUM, "2025"), ADMIN_TOKEN)
status, payload = halfnum_adapter.retrieve("P-HALF")
halfnum_evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["half_number_directly_appended_to_street_num"] = (
    halfnum_evidence.get("property_address", "").startswith(EXPECTED_HALF_PREFIX)
)

# --- 7. Legal lines combined without blanks. ---------------------------------
checks["legal_lines_combined_baseline"] = evidence.get("legal_description") == EXPECTED_BASE_LEGAL
checks["legal_description_has_no_empty_segments"] = (
    "||" not in evidence.get("legal_description", "") and
    not evidence.get("legal_description", "").startswith("|") and
    not evidence.get("legal_description", "").endswith("|")
)
# Account with genuinely blank LEGAL1-5 (real data, confirmed directly)
# correctly produces NO legal_description evidence at all, rather than
# an empty string.
checks["fully_blank_legal_lines_produce_no_evidence"] = "legal_description" not in halfnum_evidence

# --- 8. Valuation fields remain typed CURRENCY; parcel remains
# IDENTIFIER -- verified all the way through canonicalization, not just
# that the adapter returns strings. ------------------------------------------
from era.canonical.canonical_engine import CanonicalEvidenceModel
from era.canonical.canonical_models import CanonicalEvidenceRecord, Provenance
from era.canonical.canonical_enums import EvidenceCategory, EvidenceSourceClass, EvidenceValueType
from era.pipeline import FIELD_VALUE_TYPE

checks["total_value_mapped_to_currency_type"] = FIELD_VALUE_TYPE["total_appraised_value"] == EvidenceValueType.CURRENCY
checks["land_value_mapped_to_currency_type"] = FIELD_VALUE_TYPE["land_value"] == EvidenceValueType.CURRENCY
checks["improvement_value_mapped_to_currency_type"] = FIELD_VALUE_TYPE["improvement_value"] == EvidenceValueType.CURRENCY
checks["parcel_id_mapped_to_identifier_type"] = FIELD_VALUE_TYPE["parcel_id"] == EvidenceValueType.IDENTIFIER

ecm = CanonicalEvidenceModel()
prov = Provenance(
    connector_id="DCAD_BULK_DATA_2025", provider_name="DCAD", source_name="DCAD Data Products",
    source_class=EvidenceSourceClass.PUBLIC_RECORD, retrieved_at="2026-01-01T00:00:00+00:00",
    legal_basis="PUBLIC_RECORD", normalization_version="ECM-1.0", audit_reference="AUD-JOIN-001",
)
value_status, value_normalized = ecm.normalize_record(CanonicalEvidenceRecord(
    evidence_id="EV-1", property_id="P1", category=EvidenceCategory.MARKET, field_name="total_appraised_value",
    raw_value=evidence["total_appraised_value"], normalized_value=evidence["total_appraised_value"],
    units=None, provenance=prov, value_type=EvidenceValueType.CURRENCY,
))
checks["real_currency_value_passes_ecm"] = value_status == "PASS"

parcel_status, parcel_normalized = ecm.normalize_record(CanonicalEvidenceRecord(
    evidence_id="EV-2", property_id="P1", category=EvidenceCategory.PARCEL, field_name="parcel_id",
    raw_value=evidence["parcel_id"], normalized_value=evidence["parcel_id"],
    units=None, provenance=prov, value_type=EvidenceValueType.IDENTIFIER,
))
checks["real_identifier_value_passes_ecm_leading_zeros_intact"] = (
    parcel_status == "PASS" and parcel_normalized.normalized_value == ACCT_BASELINE
)

# --- 9. Unmatched central record degrades honestly: Account_Apprl_Year
# has the account, Account_Info does not -- real per-row data, an
# intentionally incomplete join, not fabricated field values. ---------------
unmatched_zip = build_zip([ACCT_BASELINE], [])  # info table has zero accounts
unmatched_adapter = new_joined_adapter(unmatched_zip)
unmatched_adapter.register_account_mapping(DCADAccountMapping("P-UNMATCHED", ACCT_BASELINE, "2025"), ADMIN_TOKEN)
status, payload = unmatched_adapter.retrieve("P-UNMATCHED")
unmatched_evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["unmatched_central_record_still_succeeds"] = status == "PASS"
checks["unmatched_record_has_appraisal_data"] = "total_appraised_value" in unmatched_evidence
checks["unmatched_record_has_no_situs_address"] = "property_address" not in unmatched_evidence
checks["unmatched_record_falls_back_to_juris_city"] = unmatched_evidence.get("city") == EXPECTED_CITY
checks["unmatched_event_recorded_in_audit"] = any(
    e["event_type"] == "DCAD_ACCOUNT_INFO_UNMATCHED" for e in unmatched_adapter.audit.events
)

# --- 10. Duplicate join rows are detected. Real data has zero duplicate
# keys (confirmed directly); tested here via a deliberately duplicated
# real row. -------------------------------------------------------------------
dup_zip = build_zip(main_accounts, main_accounts, duplicate_info_account=ACCT_BASELINE)
dup_adapter = new_joined_adapter(dup_zip)
dup_adapter.register_account_mapping(DCADAccountMapping("P-DUP", ACCT_BASELINE, "2025"), ADMIN_TOKEN)
status, payload = dup_adapter.retrieve("P-DUP")
checks["duplicate_join_row_does_not_crash_retrieval"] = status == "PASS"
checks["duplicate_join_key_counted"] = dup_adapter.get_duplicate_join_key_counts()["account_info"] == 1
checks["duplicate_join_key_recorded_in_audit"] = any(
    e["event_type"] == "DCAD_DUPLICATE_JOIN_KEYS_DETECTED" for e in dup_adapter.audit.events
)

# --- 10b. Regression: a partial index-build failure (appraisal table
# indexes successfully, account_info fails) must not leave the adapter
# in a state where a SECOND retrieve() call crashes. Found during a
# fresh review after DCAD-JOIN-001 first landed -- appraisal_index was
# being committed before account_info indexing was attempted, so a
# failed join left appraisal_index set but info_index still None; the
# next retrieve() call's "already indexed?" guard only checked
# appraisal_index, skipped re-fetching, and crashed calling .get() on
# None. Fixed by only committing either index once the ENTIRE fetch
# (both tables, when joining) succeeds. ---------------------------------------
partial_fail_zip_buf = io.BytesIO()
with zipfile.ZipFile(partial_fail_zip_buf, "w") as z:
    z.writestr("ACCOUNT_APPRL_YEAR.CSV", appr_df[appr_df["ACCOUNT_NUM"] == ACCT_BASELINE].to_csv(index=False))
    z.writestr("ACCOUNT_INFO.CSV", "WRONG,COLUMNS,HERE\n1,2,3\n")
partial_fail_transport = MockHttpTransport()
partial_fail_transport.set_response(URL, HttpResponse(200, "", content=partial_fail_zip_buf.getvalue()))
_partial_fail_index_fd, _partial_fail_index_path = tempfile.mkstemp(suffix=".db")
os.close(_partial_fail_index_fd)
os.remove(_partial_fail_index_path)
partial_fail_adapter = DCADBulkDataAdapter(download_url=URL, transport=partial_fail_transport, join_account_info=True,
                                            index_db_path=_partial_fail_index_path,
                                            auth=AuthEngine(token_store=MockTokenStore()))
partial_fail_adapter.register_account_mapping(DCADAccountMapping("P-PARTIAL", ACCT_BASELINE, "2025"), ADMIN_TOKEN)

first_status, _ = partial_fail_adapter.retrieve("P-PARTIAL")
checks["partial_index_failure_first_call_fails_cleanly"] = first_status == errors.MALFORMED_CSV_HEADER
checks["partial_index_failure_does_not_commit_appraisal_index"] = not partial_fail_adapter._index_store.is_ready()

second_call_raised = False
try:
    second_status, _ = partial_fail_adapter.retrieve("P-PARTIAL")
except Exception:
    second_call_raised = True
checks["partial_index_failure_second_call_does_not_crash"] = not second_call_raised
checks["partial_index_failure_second_call_fails_cleanly_again"] = (
    not second_call_raised and second_status == errors.MALFORMED_CSV_HEADER
)

# And confirm real recovery: fix the underlying data, retry succeeds.
recovered_buf = io.BytesIO()
with zipfile.ZipFile(recovered_buf, "w") as z:
    z.writestr("ACCOUNT_APPRL_YEAR.CSV", appr_df[appr_df["ACCOUNT_NUM"] == ACCT_BASELINE].to_csv(index=False))
    z.writestr("ACCOUNT_INFO.CSV", info_df[info_df["ACCOUNT_NUM"] == ACCT_BASELINE].to_csv(index=False))
partial_fail_transport.set_response(URL, HttpResponse(200, "", content=recovered_buf.getvalue()))
third_status, third_payload = partial_fail_adapter.retrieve("P-PARTIAL")
checks["partial_index_failure_recovers_once_data_is_fixed"] = third_status == "PASS"
checks["partial_index_failure_recovery_has_real_evidence"] = any(
    e.field_name == "property_address" for e in third_payload.get("evidence", [])
)

# --- 11. Full pipeline reaches decision/policy/export, and the
# INSUFFICIENT_EVIDENCE result from Phase 1 is now resolved for an
# account where Account_Info supplies a real situs address. ------------------
pipeline_zip = build_zip([ACCT_BASELINE], [ACCT_BASELINE])
_pipeline_index_fd, _pipeline_index_path = tempfile.mkstemp(suffix=".db")
os.close(_pipeline_index_fd)
os.remove(_pipeline_index_path)
pipeline_app = build_app(dcad_download_url=URL, dcad_join_account_info=True, dcad_index_db_path=_pipeline_index_path, token_store=MockTokenStore())
bootstrap_dcad_demo(pipeline_app)
pipeline_app.c.dcad_bulk_data_adapter._transport = MockHttpTransport()
pipeline_app.c.dcad_bulk_data_adapter._transport.set_response(URL, HttpResponse(200, "", content=pipeline_zip))
pipeline_app.c.dcad_bulk_data_adapter.register_account_mapping(
    DCADAccountMapping("ERA-PR-2026-DCAD-JOIN-001", ACCT_BASELINE, "2025"), ADMIN_TOKEN
)
identity = PropertyIdentity(
    property_id="ERA-PR-2026-DCAD-JOIN-001", address="4562 CATINA LN", city="Dallas", state="TX",
    zip_code="75229", county="Dallas", parcel_apn=ACCT_BASELINE, latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)
result = pipeline_app.run_property(
    property_id=identity.property_id, identity=identity,
    state="TX", county="Dallas", provider_id="DCAD_BULK_DATA_2025",
)
checks["full_pipeline_reaches_decision"] = result.decision_record is not None
checks["full_pipeline_reaches_policy"] = result.policy_result is not None
checks["insufficient_evidence_resolved_with_real_situs_address"] = (
    result.decision_record is not None and result.decision_record.decision.value != "INSUFFICIENT_EVIDENCE"
)
checks["full_pipeline_reaches_export"] = result.export_package is not None

# --- 12. Restart persistence survives. ----------------------------------------
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)
try:
    _persist_index_fd, _persist_index_path = tempfile.mkstemp(suffix=".db")
    os.close(_persist_index_fd)
    os.remove(_persist_index_path)
    persist_app = build_app(persistence_path=db_path, dcad_download_url=URL, dcad_join_account_info=True,
                             dcad_index_db_path=_persist_index_path, token_store=MockTokenStore())
    bootstrap_dcad_demo(persist_app)
    persist_app.c.dcad_bulk_data_adapter._transport = MockHttpTransport()
    persist_app.c.dcad_bulk_data_adapter._transport.set_response(URL, HttpResponse(200, "", content=pipeline_zip))
    persist_app.c.dcad_bulk_data_adapter.register_account_mapping(
        DCADAccountMapping("ERA-PR-2026-DCAD-PERSIST", ACCT_BASELINE, "2025"), ADMIN_TOKEN
    )
    persist_identity = PropertyIdentity(
        property_id="ERA-PR-2026-DCAD-PERSIST", address="4562 CATINA LN", city="Dallas", state="TX",
        zip_code="75229", county="Dallas", parcel_apn=ACCT_BASELINE, latitude=None, longitude=None,
        property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
    )
    persist_result = persist_app.run_property(
        property_id=persist_identity.property_id, identity=persist_identity,
        state="TX", county="Dallas", provider_id="DCAD_BULK_DATA_2025",
    )
    checks["persist_run_succeeded_before_restart"] = persist_result.ok
    del persist_app

    reopened = build_app(persistence_path=db_path)
    checks["restart_upr_survived"] = "ERA-PR-2026-DCAD-PERSIST" in reopened.c.upr.records
    checks["restart_epm_survived"] = any(
        r.property_id == "ERA-PR-2026-DCAD-PERSIST" for r in reopened.c.epm.records.values()
    )
    checks["restart_dec_survived"] = reopened.c.dec.get_decision("ERA-PR-2026-DCAD-PERSIST") is not None
    checks["restart_pol_survived"] = reopened.c.pol.get_result("ERA-PR-2026-DCAD-PERSIST") is not None
    checks["restart_exp_survived"] = reopened.c.exp.get_export("ERA-PR-2026-DCAD-PERSIST") is not None
finally:
    for suffix in ("", "-wal", "-shm", ".audit.db", ".audit.db-wal", ".audit.db-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)
    for _p in (_pipeline_index_path, _persist_index_path):
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(_p + suffix):
                os.remove(_p + suffix)

# --- Blank-situs synthetic case (real data has zero such rows,
# confirmed directly -- tested here for code-path robustness only). ---------
synthetic_blank_situs_info = {
    "ACCOUNT_NUM": "88888888888888888", "APPRAISAL_YR": "2025", "DIVISION_CD": "RES",
    "OWNER_NAME1": "DOE JANE", "STREET_NUM": "", "FULL_STREET_NAME": "",
    "PROPERTY_CITY": "DALLAS", "PROPERTY_ZIPCODE": "752010000", "GIS_PARCEL_ID": "88888888888888888",
}
synthetic_blank_situs_appr = {
    "ACCOUNT_NUM": "88888888888888888", "APPRAISAL_YR": "2025",
    "TOT_VAL": "50000.00", "LAND_VAL": "25000.00", "IMPR_VAL": "25000.00",
    "CITY_JURIS_DESC": "DALLAS", "COUNTY_JURIS_DESC": "DALLAS COUNTY",
    "GIS_PARCEL_ID": "88888888888888888",
}
blank_zip = build_zip([], [], extra_appr_rows=[synthetic_blank_situs_appr],
                       extra_info_rows=[synthetic_blank_situs_info])
blank_adapter = new_joined_adapter(blank_zip)
blank_adapter.register_account_mapping(DCADAccountMapping("P-BLANK", "88888888888888888", "2025"), ADMIN_TOKEN)
status, payload = blank_adapter.retrieve("P-BLANK")
blank_evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["blank_situs_synthetic_case_no_address_produced"] = "property_address" not in blank_evidence
checks["blank_situs_does_not_crash_retrieval"] = status == "PASS"

# --- Phase 1 (no join) remains completely unaffected. -----------------------
phase1_zip = build_zip([ACCT_BASELINE], [ACCT_BASELINE])
phase1_transport = MockHttpTransport()
phase1_transport.set_response(URL, HttpResponse(200, "", content=phase1_zip))
_phase1_index_fd, _phase1_index_path = tempfile.mkstemp(suffix=".db")
os.close(_phase1_index_fd)
os.remove(_phase1_index_path)
phase1_adapter = DCADBulkDataAdapter(download_url=URL, transport=phase1_transport, index_db_path=_phase1_index_path,
                                      auth=AuthEngine(token_store=MockTokenStore()))  # join_account_info defaults False
phase1_adapter.register_account_mapping(DCADAccountMapping("P-PHASE1", ACCT_BASELINE, "2025"), ADMIN_TOKEN)
status, payload = phase1_adapter.retrieve("P-PHASE1")
phase1_evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
checks["phase1_still_uses_juris_city_not_property_city"] = phase1_evidence.get("city") == EXPECTED_CITY
checks["phase1_still_has_no_address"] = "property_address" not in phase1_evidence
checks["phase1_still_has_no_owner_or_legal"] = (
    "owner_name" not in phase1_evidence and "legal_description" not in phase1_evidence
)

for _p in (_partial_fail_index_path, _phase1_index_path):
    for _suffix in ("", "-wal", "-shm"):
        if os.path.exists(_p + _suffix):
            os.remove(_p + _suffix)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"DCAD-JOIN-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
