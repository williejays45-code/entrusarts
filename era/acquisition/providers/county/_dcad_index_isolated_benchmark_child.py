"""
DCAD-INDEX-001 operational benchmark: isolated child process.

Imports ONLY DCADIndexStore, the standard library, and psutil.
Deliberately does NOT import pandas, DCADBulkDataAdapter, any test
fixture, or the broader verification suite -- that is the entire point
of running this as a separate process with a minimal import surface.
This is what makes the memory measurement trustworthy: nothing else in
this process's lifetime can inflate ru_maxrss or a psutil RSS sample,
because nothing else ever gets imported or allocated here.

Does exactly what the contract specifies, nothing more:
  1. import DCADIndexStore
  2. open source CSVs
  3. build disk index (fresh build, or confirm-and-skip on reuse)
  4. perform two lookups
  5. exit

Communicates results back to the parent (verify_dcad_index_operational.py)
as a single line of JSON on stdout -- easy to parse, impossible to
confuse with the human-readable progress noise a shared script might
otherwise print.
"""

import sys
import os
import csv
import json
import time
import threading
import argparse

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
from era.live_adapters.dcad_index_store import DCADIndexStore, DCADIndexBuildError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fresh", "reuse"], required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--appr-path", required=True)
    parser.add_argument("--info-path", required=True)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--lookup-account", required=True)
    parser.add_argument("--lookup-year", required=True)
    parser.add_argument("--lookup-tot-val", required=True)
    parser.add_argument("--lookup-owner", required=True)
    args = parser.parse_args()

    process = psutil.Process(os.getpid())

    baseline_rss = process.memory_info().rss

    peak_rss = {"value": baseline_rss}
    stop_monitor = threading.Event()

    def monitor():
        while not stop_monitor.is_set():
            try:
                rss = process.memory_info().rss
                if rss > peak_rss["value"]:
                    peak_rss["value"] = rss
            except Exception:
                pass
            stop_monitor.wait(0.02)

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()

    store = DCADIndexStore(args.db_path, batch_size=args.batch_size)

    def appraisal_reader():
        with open(args.appr_path, newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)

    def info_reader():
        with open(args.info_path, newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)

    start = time.perf_counter()
    fingerprint = "operational-benchmark-fixed-fingerprint"

    did_rebuild = False
    if args.mode == "fresh":
        result = store.build(
            appraisal_reader, info_reader, fingerprint,
            {"ACCOUNT_NUM", "APPRAISAL_YR"}, {"ACCOUNT_NUM", "APPRAISAL_YR"},
        )
        did_rebuild = True
    else:
        # reuse: only rebuild if the on-disk index isn't already a
        # complete, matching build -- this is the real code path a
        # long-running adapter takes on every retrieve() call after the
        # first, and is exactly what should NOT re-touch the CSVs at all.
        if store.needs_rebuild(fingerprint, require_info_table=True):
            result = store.build(
                appraisal_reader, info_reader, fingerprint,
                {"ACCOUNT_NUM", "APPRAISAL_YR"}, {"ACCOUNT_NUM", "APPRAISAL_YR"},
            )
            did_rebuild = True
        else:
            meta = store.get_build_meta()
            result = {
                "appraisal_stored": meta["row_count_appraisal"],
                "info_stored": meta["row_count_info"],
            }

    elapsed = time.perf_counter() - start

    appraisal_row = store.lookup_appraisal(args.lookup_account, args.lookup_year)
    info_row = store.lookup_info(args.lookup_account, args.lookup_year)

    final_rss = process.memory_info().rss
    if final_rss > peak_rss["value"]:
        peak_rss["value"] = final_rss

    stop_monitor.set()
    monitor_thread.join(timeout=1.0)

    db_size_bytes = os.path.getsize(args.db_path) if os.path.exists(args.db_path) else 0

    output = {
        "mode": args.mode,
        "did_rebuild": did_rebuild,
        "baseline_rss_bytes": baseline_rss,
        "peak_rss_bytes": peak_rss["value"],
        "final_rss_bytes": final_rss,
        "peak_delta_bytes": peak_rss["value"] - baseline_rss,
        "elapsed_seconds": elapsed,
        "appraisal_stored": result.get("appraisal_stored"),
        "info_stored": result.get("info_stored"),
        "db_size_bytes": db_size_bytes,
        "max_observed_batch_size": store.max_observed_batch_size,
        "configured_batch_size": store.configured_batch_size,
        "lookup_appraisal_found": appraisal_row is not None,
        "lookup_appraisal_tot_val_correct": (
            appraisal_row is not None and appraisal_row.get("TOT_VAL") == args.lookup_tot_val
        ),
        "lookup_appraisal_account_num_exact_string": (
            appraisal_row is not None and appraisal_row.get("ACCOUNT_NUM") == args.lookup_account
        ),
        "lookup_info_found": info_row is not None,
        "lookup_info_owner_correct": (
            info_row is not None and info_row.get("OWNER_NAME1") == args.lookup_owner
        ),
    }
    print("BENCHMARK_RESULT_JSON:" + json.dumps(output))


if __name__ == "__main__":
    main()
