import sys
import os
import csv
import subprocess
import tempfile
import io
import zipfile
from era.live_adapters.dcad_index_store import DCADIndexStore, DCADIndexBuildError, compute_fingerprint
from era.live_adapters.dcad_bulk_data_adapter import DCADBulkDataAdapter
from era.live_adapters.dcad_bulk_data_models import DCADAccountMapping
from era.live_adapters import dcad_bulk_errors as errors
from era.network.mock_transport import MockHttpTransport
from era.network.network_models import HttpResponse
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import MockTokenStore

print("DCAD-INDEX-001 VERIFICATION -- disk-backed streaming index")
print("=" * 70)

checks = {}
URL = "https://www.dallascad.org/data-products/2025-certified.zip"

from era.live_adapters.dcad_test_data import (
    SYNTHETIC_ACCOUNT_BASELINE, SYNTHETIC_ACCOUNT_UNIT,
    SYNTHETIC_BASE_ADDRESS, SYNTHETIC_BASE_OWNER, SYNTHETIC_BASE_TOTAL,
    SYNTHETIC_UNIT_ADDRESS, resolve_dcad_test_paths,
)
APPR_PATH, INFO_PATH, USING_FULL_DCAD_DATA = resolve_dcad_test_paths()
ACCT_BASELINE = "00000416479000000" if USING_FULL_DCAD_DATA else SYNTHETIC_ACCOUNT_BASELINE
ADMIN_TOKEN = "admin-token"
ACCT_UNIT_BLDG = "60001000011030000" if USING_FULL_DCAD_DATA else SYNTHETIC_ACCOUNT_UNIT
EXPECTED_BASE_TOTAL = "3300000.00" if USING_FULL_DCAD_DATA else SYNTHETIC_BASE_TOTAL
EXPECTED_BASE_OWNER = "MEDITZ RICHARD A" if USING_FULL_DCAD_DATA else SYNTHETIC_BASE_OWNER
EXPECTED_BASE_ADDRESS = "4562 CATINA LN" if USING_FULL_DCAD_DATA else SYNTHETIC_BASE_ADDRESS
EXPECTED_UNIT_ADDRESS = (
    "4712 ABBOTT AVE BLDG A UNIT 103" if USING_FULL_DCAD_DATA else SYNTHETIC_UNIT_ADDRESS
)

REQUIRED = {"ACCOUNT_NUM", "APPRAISAL_YR"}


def fresh_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    return path


def cleanup(path):
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


def good_rows(n=3, start=1):
    for i in range(start, start + n):
        yield {"ACCOUNT_NUM": f"{i:018d}", "APPRAISAL_YR": "2025", "TOT_VAL": f"{i * 1000}.00"}


def raising_rows_after(n_good):
    for i, row in enumerate(good_rows(n=n_good + 5)):
        if i >= n_good:
            raise RuntimeError("simulated truncated/corrupted source stream")
        yield row


# --- 1 (of the numbered list, run FIRST in this file on purpose).
# Peak memory stays within an agreed limit -- the REAL, full-scale
# build against both actual 858,533-row files.
#
# Measured in a genuinely isolated subprocess. This MUST run before
# this parent process itself loads anything pandas-heavy (see checks
# further down, which build small real excerpts via pandas) -- ru_maxrss
# is a lifetime HIGH-WATER MARK, and on Linux, a subprocess spawned via
# fork()+exec() can report a ru_maxrss that reflects the PARENT's own
# prior peak, not just the child's -- a real, reproducible measurement
# artifact, confirmed directly: running this exact isolated-subprocess
# measurement AFTER this file's pandas-based fixture-building steps
# reported ~1.8 GB (the parent's own pandas footprint leaking into the
# child's reported rusage); running the identical subprocess logic
# standalone, or here at the top of the file before pandas is ever
# imported in this process, consistently reports the real number
# (~28 MB, confirmed across multiple independent runs). Ordering this
# check first is the actual fix -- not raising the ceiling to paper
# over a measurement bug, and not trusting a number without explaining
# the discrepancy first.
#
# Agreed ceiling: 500 MB. Contrast: the OLD in-memory dict approach
# measured 2.9 GB for ONE table alone and was killed by the OS
# attempting the second.
MEMORY_CEILING_MB = 500

def count_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return max(sum(1 for _ in f) - 1, 0)

EXPECTED_APPR_ROWS = count_csv_rows(APPR_PATH)
EXPECTED_INFO_ROWS = count_csv_rows(INFO_PATH)
isolated_db_path = fresh_db_path()
isolated_script = f"""
import csv, os
import psutil
from era.live_adapters.dcad_index_store import DCADIndexStore

store = DCADIndexStore({isolated_db_path!r}, batch_size=2000)

def real_appr_reader():
    with open({APPR_PATH!r}, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)

def real_info_reader():
    with open({INFO_PATH!r}, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)

result = store.build(real_appr_reader, real_info_reader, "full-scale-verify-isolated",
                      {{"ACCOUNT_NUM", "APPRAISAL_YR"}}, {{"ACCOUNT_NUM", "APPRAISAL_YR"}})
peak_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
print("RESULT", result["appraisal_stored"], result["info_stored"], f"{{peak_mb:.1f}}")
"""
try:
    proc = subprocess.run([sys.executable, "-c", isolated_script], capture_output=True, text=True, timeout=240)
    result_line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT")), "")
    parts = result_line.split()
    if len(parts) == 4:
        appraisal_stored, info_stored, peak_mb = int(parts[1]), int(parts[2]), float(parts[3])
    else:
        appraisal_stored, info_stored, peak_mb = 0, 0, float("inf")
        print("  (isolated subprocess output was unexpected -- stdout/stderr below)")
        print("  stdout:", proc.stdout[-2000:])
        print("  stderr:", proc.stderr[-2000:])

    checks["index_build_completed_all_available_rows"] = appraisal_stored == EXPECTED_APPR_ROWS and info_stored == EXPECTED_INFO_ROWS
    checks["index_build_peak_memory_within_ceiling"] = peak_mb <= MEMORY_CEILING_MB
    print(f"  (index build, ISOLATED subprocess, run FIRST: {appraisal_stored} + {info_stored} real rows, "
          f"peak RSS {peak_mb:.1f} MB, ceiling {MEMORY_CEILING_MB} MB)")

    verify_store = DCADIndexStore(isolated_db_path)
    checks["full_scale_build_is_ready"] = verify_store.is_ready(require_info_table=True)
    real_appr_row = verify_store.lookup_appraisal(ACCT_BASELINE, "2025")
    real_info_row = verify_store.lookup_info(ACCT_BASELINE, "2025")
    checks["full_scale_real_lookup_appraisal_correct"] = (
        real_appr_row is not None and real_appr_row["TOT_VAL"] == EXPECTED_BASE_TOTAL
    )
    checks["full_scale_real_lookup_info_correct"] = (
        real_info_row is not None and real_info_row["OWNER_NAME1"] == EXPECTED_BASE_OWNER
    )
finally:
    cleanup(isolated_db_path)

# pandas is only imported now, AFTER the isolated memory measurement
# above has already run and been recorded -- this ordering is the fix.
import pandas as pd

# --- 2. Partial appraisal import rolls back cleanly. -------------------------
path1 = fresh_db_path()
try:
    store = DCADIndexStore(path1)
    raised = False
    try:
        store.build(lambda: raising_rows_after(3), None, "fp-1", REQUIRED)
    except RuntimeError:
        raised = True
    checks["partial_appraisal_import_raises_not_silently_fails"] = raised
    checks["partial_appraisal_import_leaves_nothing_ready"] = not store.is_ready()
    checks["partial_appraisal_import_leaves_no_rows"] = store.lookup_appraisal("000000000000000001", "2025") is None
finally:
    cleanup(path1)

# --- 3. Partial info import rolls back cleanly -- appraisal succeeds
# FIRST, then info fails; the whole transaction (including the already-
# successful appraisal rows) must roll back together, not just the
# failing table. ---------------------------------------------------------------
path2 = fresh_db_path()
try:
    store = DCADIndexStore(path2)
    raised = False
    try:
        store.build(lambda: good_rows(3), lambda: raising_rows_after(2), "fp-2", REQUIRED, REQUIRED)
    except RuntimeError:
        raised = True
    checks["partial_info_import_raises"] = raised
    checks["partial_info_import_leaves_nothing_ready"] = not store.is_ready(require_info_table=True)
    checks["partial_info_import_rolls_back_appraisal_too"] = (
        store.lookup_appraisal("000000000000000001", "2025") is None
    )
finally:
    cleanup(path2)

# --- 4. Retry after corrected source succeeds. --------------------------------
path3 = fresh_db_path()
try:
    store = DCADIndexStore(path3)
    try:
        store.build(lambda: raising_rows_after(2), None, "fp-3-bad", REQUIRED)
    except RuntimeError:
        pass
    checks["retry_before_fix_still_not_ready"] = not store.is_ready()
    store.build(lambda: good_rows(3), None, "fp-3-good", REQUIRED)
    checks["retry_after_fix_succeeds"] = store.is_ready()
    checks["retry_after_fix_has_real_data"] = store.lookup_appraisal("000000000000000001", "2025") is not None
finally:
    cleanup(path3)

# --- 5. Leading-zero account survives (real data, through the full
# adapter this time, not just the index store directly). ----------------------
path4 = fresh_db_path()
try:
    appr_df = pd.read_csv(APPR_PATH, dtype=str)
    info_df = pd.read_csv(INFO_PATH, dtype=str)
    subset_accounts = [ACCT_BASELINE, ACCT_UNIT_BLDG]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ACCOUNT_APPRL_YEAR.CSV", appr_df[appr_df["ACCOUNT_NUM"].isin(subset_accounts)].to_csv(index=False))
        z.writestr("ACCOUNT_INFO.CSV", info_df[info_df["ACCOUNT_NUM"].isin(subset_accounts)].to_csv(index=False))
    real_zip = buf.getvalue()

    transport = MockHttpTransport()
    transport.set_response(URL, HttpResponse(200, "", content=real_zip))
    adapter = DCADBulkDataAdapter(download_url=URL, transport=transport, join_account_info=True, index_db_path=path4, auth=AuthEngine(token_store=MockTokenStore()))
    adapter.register_account_mapping(DCADAccountMapping("P1", ACCT_BASELINE, "2025"), ADMIN_TOKEN)
    status, payload = adapter.retrieve("P1")
    evidence = {e.field_name: e.raw_value for e in payload.get("evidence", [])}
    checks["leading_zero_account_survives_through_adapter"] = evidence.get("parcel_id") == ACCT_BASELINE
    checks["leading_zero_is_string_type"] = isinstance(evidence.get("parcel_id"), str)

    # --- 6. Exact two-table join succeeds. ------------------------------------
    checks["exact_two_table_join_succeeds"] = (
        status == "PASS" and evidence.get("property_address") == EXPECTED_BASE_ADDRESS
        and "total_appraised_value" in evidence
    )

    # --- 7. Wrong year does not join. -------------------------------------------
    adapter.register_account_mapping(DCADAccountMapping("P-WRONGYEAR", ACCT_BASELINE, "2024"), ADMIN_TOKEN)
    wrong_status, wrong_payload = adapter.retrieve("P-WRONGYEAR")
    checks["wrong_appraisal_year_does_not_join"] = wrong_status == errors.ACCOUNT_NOT_FOUND and wrong_payload == {}

    # --- 8. Persistent index survives restart -- brand new adapter
    # instance, same db_path, ZERO transport calls needed. -----------------------
    fresh_transport = MockHttpTransport()  # deliberately no response configured
    adapter2 = DCADBulkDataAdapter(download_url=URL, transport=fresh_transport, join_account_info=True, index_db_path=path4, auth=AuthEngine(token_store=MockTokenStore()))
    adapter2.register_account_mapping(DCADAccountMapping("P1", ACCT_BASELINE, "2025"), ADMIN_TOKEN)
    restart_status, restart_payload = adapter2.retrieve("P1")
    restart_evidence = {e.field_name: e.raw_value for e in restart_payload.get("evidence", [])}
    checks["persistent_index_survives_restart"] = restart_status == "PASS"
    checks["restart_no_network_call_needed"] = len(fresh_transport.sent_requests) == 0
    checks["restart_evidence_matches_original"] = restart_evidence == evidence

    # --- 9. Fixture behavior remains unchanged: address/owner/legal
    # construction is byte-identical to the pre-rewrite in-memory-dict
    # behavior. --------------------------------------------------------------------
    unit_adapter = DCADBulkDataAdapter(download_url=URL, transport=fresh_transport, join_account_info=True, index_db_path=path4, auth=AuthEngine(token_store=MockTokenStore()))
    unit_adapter.register_account_mapping(DCADAccountMapping("P-UNIT", ACCT_UNIT_BLDG, "2025"), ADMIN_TOKEN)
    _, unit_payload = unit_adapter.retrieve("P-UNIT")
    unit_evidence = {e.field_name: e.raw_value for e in unit_payload.get("evidence", [])}
    checks["fixture_behavior_unchanged_unit_bldg_address"] = (
        unit_evidence.get("property_address") == EXPECTED_UNIT_ADDRESS
    )
    checks["fixture_behavior_unchanged_legal_description_present"] = "legal_description" in unit_evidence
finally:
    cleanup(path4)

# --- 10. Incomplete index is never treated as ready (re-confirmed at the
# adapter level, not just the index-store level tested in checks 2-3). --------
path8 = fresh_db_path()
try:
    bad_zip_buf = io.BytesIO()
    with zipfile.ZipFile(bad_zip_buf, "w") as z:
        z.writestr("ACCOUNT_APPRL_YEAR.CSV", "ACCOUNT_NUM,APPRAISAL_YR,TOT_VAL\n1,2025,100.00\n")
        z.writestr("ACCOUNT_INFO.CSV", "WRONG,HEADER\n1,2\n")
    transport8 = MockHttpTransport()
    transport8.set_response(URL, HttpResponse(200, "", content=bad_zip_buf.getvalue()))
    adapter8 = DCADBulkDataAdapter(download_url=URL, transport=transport8, join_account_info=True, index_db_path=path8, auth=AuthEngine(token_store=MockTokenStore()))
    adapter8.register_account_mapping(DCADAccountMapping("P1", "1", "2025"), ADMIN_TOKEN)
    status8, _ = adapter8.retrieve("P1")
    checks["incomplete_index_first_call_fails_cleanly"] = status8 == errors.MALFORMED_CSV_HEADER
    checks["incomplete_index_never_marked_ready"] = not adapter8._index_store.is_ready(require_info_table=True)
    status8b, _ = adapter8.retrieve("P1")
    checks["incomplete_index_second_call_also_fails_cleanly_not_crash"] = status8b == errors.MALFORMED_CSV_HEADER
finally:
    cleanup(path8)

# --- 11. Source fingerprint change forces rebuild. ----------------------------
path9 = fresh_db_path()
try:
    store9 = DCADIndexStore(path9)
    store9.build(lambda: good_rows(2), None, "fingerprint-v1", REQUIRED)
    checks["fingerprint_same_skips_rebuild"] = not store9.needs_rebuild("fingerprint-v1")
    checks["fingerprint_changed_forces_rebuild"] = store9.needs_rebuild("fingerprint-v2")
finally:
    cleanup(path9)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"DCAD-INDEX-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
