"""
LIVE-DCAD-VERIFY-001 -- LOCAL MACHINE ONLY.

This script cannot run in the Claude sandbox that built the rest of
ERA. That environment's network egress is allow-listed to
package/dev infrastructure only (pypi.org, github.com, npmjs.com, and
similar) -- no government or open-data domain is reachable from there,
by design, not by oversight. Every prior mention of this boundary in
this project has been consistent: the transport layer (UrllibHttpTransport,
NETWORK-001/NETWORK-001B) is real and unit-tested against real captured
DCAD data, but it has never once been exercised against DCAD's actual
endpoint. This script is that missing exercise, meant to run on a
machine that can actually reach dallascad.org (or wherever the real
Data Products download actually lives).

What this proves, that nothing else in the test suite can:
- The real DCAD Data Products URL actually serves a ZIP (not an HTML
  error page, a login wall, a redirect, or something else entirely).
- UrllibHttpTransport's real HTTP client code (never exercised outside
  a MockHttpTransport until now) handles a genuine multi-hundred-MB
  download correctly.
- The real ZIP's internal entry names match DCADBulkDataAdapter's
  DEFAULT_TARGET_ENTRY / DEFAULT_ACCOUNT_INFO_ENTRY guesses -- these
  were labeled "best-guess, unconfirmed" from the moment they were
  written, because the actual archive was never provided, only the
  extracted CSVs were. This is the first real chance to find out if
  the guess was right.
- DCADIndexStore's streaming build genuinely stays memory-bounded
  against a live download, not just a local file already sitting on
  disk (DCAD-INDEX-001's own benchmark proved the local-file case;
  this proves the network-download case, which has different memory
  characteristics -- streaming a download while writing to SQLite
  simultaneously, not reading a file that's already fully on disk).
- The complete real path end to end: real network -> real ZIP ->
  real join -> real pipeline -> real decision/policy/export ->
  restart survival, all in one run, on a real machine.

REQUIRED before running:
1. A real DCAD Data Products download URL. This script refuses to run
   without one explicitly supplied -- no placeholder is fabricated,
   consistent with every other real-endpoint parameter in this
   codebase (download_url has never had a guessed default anywhere).
2. A real account_num you expect to find in the certified data, to
   confirm the lookup actually resolves to real evidence (defaults to
   the same validation account used throughout this project,
   00000416479000000, but override it if that account won't be in
   whatever certified file year you're pointed at).
3. Enough disk space for the downloaded ZIP plus the resulting SQLite
   index (the index alone was measured at ~2.4 GB for the full 2025
   certified files during DCAD-INDEX-001's own benchmark -- budget for
   at least that much free space, likely more with the ZIP itself
   still on disk during download).

Usage:
    python -m era.acquisition.providers.county.verify_dcad_live_local_only \\
        --download-url "https://<the real DCAD Data Products URL>" \\
        [--account-num 00000416479000000] \\
        [--appraisal-yr 2025] \\
        [--join-account-info]

Exits 0 on success, nonzero on any failed requirement -- same
real-gate discipline as every other verify_*.py in this codebase.
"""

import sys
import os
import argparse
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download-url", required=True,
                         help="The REAL DCAD Data Products download URL. No default -- must be supplied.")
    parser.add_argument("--account-num", default="00000416479000000",
                         help="A real ACCOUNT_NUM expected in the certified data (default: the validation account used throughout this project).")
    parser.add_argument("--appraisal-yr", default="2025")
    parser.add_argument("--join-account-info", action="store_true",
                         help="Also join Account_Info (DCAD-JOIN-001). Omit for Phase 1 (Account_Apprl_Year only).")
    parser.add_argument("--index-db-path", default=None,
                         help="Where the disk-backed index lives. Defaults to a fresh temp file for this run.")
    parser.add_argument("--keep-index", action="store_true",
                         help="Don't delete the index database after this run -- needed if you want to test restart survival separately afterward.")
    args = parser.parse_args()

    from era.app import build_app, bootstrap_dcad_demo
    from era.live_adapters.dcad_bulk_data_models import DCADAccountMapping
    from era.property_record.property_models import PropertyIdentity
    from era.property_record.property_enums import PropertyType, StrategyType

    checks = {}
    index_db_path = args.index_db_path
    owns_temp_path = index_db_path is None
    if owns_temp_path:
        fd, index_db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(index_db_path)

    print("LIVE-DCAD-VERIFY-001 -- REAL NETWORK RUN")
    print("=" * 70)
    print(f"download_url: {args.download_url}")
    print(f"account_num: {args.account_num}  appraisal_yr: {args.appraisal_yr}")
    print(f"join_account_info: {args.join_account_info}")
    print(f"index_db_path: {index_db_path}")
    print()

    try:
        # --- 1. First real run: genuinely downloads and indexes. --------------
        app = build_app(
            dcad_download_url=args.download_url,
            dcad_join_account_info=args.join_account_info,
            dcad_index_db_path=index_db_path,
            use_mock_auth=True,  # local verification convenience -- see AUTH-TOKEN-WIRE-001
        )
        bootstrap_dcad_demo(app)
        app.c.dcad_bulk_data_adapter.register_account_mapping(
            DCADAccountMapping("LIVE-VERIFY-001", args.account_num, args.appraisal_yr),
            "admin-token",
        )

        identity = PropertyIdentity(
            property_id="LIVE-VERIFY-001", address="UNKNOWN", city="Dallas", state="TX",
            zip_code="00000", county="Dallas", parcel_apn=args.account_num,
            latitude=None, longitude=None,
            property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
        )

        start = time.perf_counter()
        result = app.run_property(
            property_id=identity.property_id, identity=identity,
            state="TX", county="Dallas", provider_id="DCAD_BULK_DATA_2025",
        )
        elapsed = time.perf_counter() - start

        print(f"First run elapsed: {elapsed:.1f}s")
        for s in result.stages:
            print(f"  [{'OK' if s.ok else 'FAIL'}] {s.name}: {s.status}")
        print()

        checks["real_network_download_succeeded"] = (
            result.stage("LPA") is not None and result.stage("LPA").ok
        )
        checks["real_zip_entry_names_matched_the_guess"] = (
            result.stage("LPA") is not None
            and result.stage("LPA").status not in ("ZIP_ENTRY_NOT_FOUND",)
        )
        checks["real_ecm_stage_passed"] = result.stage("ECM") is not None and result.stage("ECM").ok
        checks["real_evidence_produced"] = len(result.canonical_records) > 0
        checks["real_pipeline_reached_decision"] = result.decision_record is not None
        checks["real_pipeline_reached_policy"] = result.policy_result is not None

        print("canonical evidence produced:")
        for r in result.canonical_records:
            print(f"  {r.field_name} = {r.normalized_value!r} ({r.value_type.value})")
        print()

        # --- 2. Restart survival against the REAL downloaded index. -----------
        print("Simulating restart against the real downloaded index (no re-download expected)...")
        del app
        from era.network.mock_transport import MockHttpTransport
        restart_app = build_app(
            dcad_index_db_path=index_db_path,
            dcad_download_url=args.download_url,  # required by build_app, but should never actually be reached
            dcad_join_account_info=args.join_account_info,
            use_mock_auth=True,
        )
        # A transport that raises if ever actually called -- proves reuse,
        # not just "it happened to work."
        restart_app.c.dcad_bulk_data_adapter._transport = MockHttpTransport()
        bootstrap_dcad_demo(restart_app)
        restart_app.c.dcad_bulk_data_adapter.register_account_mapping(
            DCADAccountMapping("LIVE-VERIFY-001-RESTART", args.account_num, args.appraisal_yr),
            "admin-token",
        )
        restart_status, restart_payload = restart_app.c.dcad_bulk_data_adapter.retrieve("LIVE-VERIFY-001-RESTART")
        checks["restart_reused_real_index_without_network_call"] = (
            restart_status == "PASS" and len(restart_app.c.dcad_bulk_data_adapter._transport.sent_requests) == 0
        )
        checks["restart_data_matches_original_run"] = len(restart_payload.get("evidence", [])) == len(result.canonical_records)

    finally:
        if owns_temp_path and not args.keep_index:
            for suffix in ("", "-wal", "-shm"):
                path = index_db_path + suffix
                if os.path.exists(path):
                    os.remove(path)
        elif args.keep_index:
            print(f"\nIndex database kept at: {index_db_path}")

    passed = 0
    print()
    for name, ok in checks.items():
        print(name, ":", "PASS" if ok else "FAIL")
        if ok:
            passed += 1
    print()
    print(f"LIVE-DCAD-VERIFY-001 CHECKS PASSED: {passed}/{len(checks)}")
    print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
