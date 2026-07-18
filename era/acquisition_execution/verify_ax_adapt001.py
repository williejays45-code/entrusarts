"""AX-ADAPT-001 genuine raw-boundary capture verification."""

import json
from pathlib import Path
import subprocess

from era.acquisition_execution.executor import (
    FAILED, SUCCEEDED, AcquisitionStepRequest, ExecutionPolicy,
)
from era.acquisition_execution.raw_capture_invoker import (
    PROVIDER_NOT_COMPOSED, RAW_BOUNDARY_UNAVAILABLE, RAW_BYTES_MISSING,
    ProviderCaptureSeam, RawCaptureAcquisitionInvoker,
    UnsupportedRawCaptureSeam,
)
from era.providers import provider_errors
from era.pipeline import OperationCancelled, OperationControl
from era.shared.audit import BaseAuditPublisher
import era.live_adapters.collin_bulk_data_adapter as collin_module
from era.live_adapters.collin_bulk_data_adapter import (
    COLLIN_CHILD_CLEANUP_FAILED,
    CollinBulkDataAdapter,
)


def request(provider_id="RAW_PROVIDER"):
    return AcquisitionStepRequest(
        "EXEC-1", "PLAN-1", "PLAN-1:1", "src:tx-test:raw:public:parcel",
        provider_id, "PARCEL", "LOOKUP-1", ExecutionPolicy(),
        "2026-07-12T23:30:00+00:00", 1,
    )


class GenuineBoundaryAdapter:
    def __init__(self, raw=b"ORIGINAL-BYTES", status=provider_errors.PASS):
        self._last_raw = None
        self.raw = raw
        self.status = status
        self.outputs = []

    def retrieve(self, lookup):
        # Test double models capture before parsing; parsed response remains separate.
        self._last_raw = self.raw
        parsed = {"evidence": ("UNCHANGED",), "source_reference": "SOURCE:1"}
        self.outputs.append(parsed)
        return self.status, parsed


class ParsedOnlyAdapter:
    def __init__(self): self._last_raw = None
    def retrieve(self, lookup):
        return provider_errors.PASS, {"evidence": ("PARSED",), "source_reference": "SOURCE:2"}


class CleanupProcess:
    def __init__(self, *, exited=False, terminate_fails=False, kill_fails=False,
                 communicate_failures=0, wait_fails=False):
        self.exited = exited
        self.terminate_fails = terminate_fails
        self.kill_fails = kill_fails
        self.communicate_failures = communicate_failures
        self.wait_fails = wait_fails
        self.returncode = 0 if exited else None

    def poll(self):
        return 0 if self.exited else None

    def terminate(self):
        if self.terminate_fails:
            raise OSError("FABRICATED_TERMINATE_FAILURE")

    def kill(self):
        if self.kill_fails:
            raise OSError("FABRICATED_KILL_FAILURE")
        self.exited = True
        self.returncode = -9

    def communicate(self, timeout=None):
        if self.communicate_failures:
            self.communicate_failures -= 1
            raise subprocess.TimeoutExpired("fabricated", timeout)
        if not self.exited:
            raise subprocess.TimeoutExpired("fabricated", timeout)
        return b"", b""

    def wait(self, timeout=None):
        if self.wait_fails:
            raise subprocess.TimeoutExpired("fabricated", timeout)
        self.exited = True
        self.returncode = -1
        return self.returncode


class CompletedButUnreapableProcess(CleanupProcess):
    """Fabricated impossible-to-reap handle after one completed delivery."""

    def __init__(self):
        super().__init__(terminate_fails=True, kill_fails=True, wait_fails=True)
        self._delivered = False

    def communicate(self, timeout=None):
        if not self._delivered:
            self._delivered = True
            return b"[]", b""
        raise subprocess.TimeoutExpired("fabricated", timeout)


def run_checks():
    adapter = GenuineBoundaryAdapter()
    seam = ProviderCaptureSeam("RAW_PROVIDER", adapter, "_last_raw", "application/test")
    response = seam.acquire(request())
    response2 = seam.acquire(request())
    parsed_only = ProviderCaptureSeam(
        "RAW_PROVIDER", ParsedOnlyAdapter(), "_last_raw", "application/test"
    ).acquire(request())
    unsupported = UnsupportedRawCaptureSeam("COUNTY_DALLAS_CAD").acquire(request("COUNTY_DALLAS_CAD"))
    invoker = RawCaptureAcquisitionInvoker((seam, UnsupportedRawCaptureSeam("COUNTY_TARRANT_ASSESSOR")))
    missing = invoker.acquire(request("UNKNOWN"))

    checks = {
        "original_bytes_returned": response.outcome == SUCCEEDED and response.raw_bytes == b"ORIGINAL-BYTES",
        "media_type_projected": response.media_type == "application/test",
        "lookup_key_preserved": response.provider_local_record_key == "LOOKUP-1",
        "transport_metadata_preserved": response.provider_response_metadata == (("source_reference", "SOURCE:1"),),
        "repeat_observation_separate": response2.raw_bytes == response.raw_bytes and len(adapter.outputs) == 2,
        "parsed_output_unchanged": adapter.outputs == [
            {"evidence": ("UNCHANGED",), "source_reference": "SOURCE:1"},
            {"evidence": ("UNCHANGED",), "source_reference": "SOURCE:1"},
        ],
        "parsed_only_fails_closed": parsed_only.outcome == FAILED and parsed_only.failure_code == RAW_BYTES_MISSING,
        "stub_boundary_fails_closed": unsupported.outcome == FAILED and unsupported.failure_code == RAW_BOUNDARY_UNAVAILABLE,
        "unknown_runtime_fails_closed": missing.outcome == FAILED and missing.failure_code == PROVIDER_NOT_COMPOSED,
        "runtime_map_not_enumeration": set(invoker._seams) == {"RAW_PROVIDER", "COUNTY_TARRANT_ASSESSOR"},
    }

    era = Path(__file__).resolve().parents[1]
    dcad = (era / "live_adapters" / "dcad_bulk_data_adapter.py").read_text(encoding="utf-8")
    collin = (era / "live_adapters" / "collin_bulk_data_adapter.py").read_text(encoding="utf-8")
    invoker_source = (Path(__file__).parent / "raw_capture_invoker.py").read_text(encoding="utf-8").lower()
    checks["dcad_capture_precedes_zip_parse"] = dcad.index("self._last_raw_source_bytes = bytes(content)") < dcad.index("zipfile.ZipFile(io.BytesIO(content))")
    checks["dcad_capture_precedes_csv_parse"] = dcad.index("self._last_raw_source_bytes = bytes(content)") < dcad.index("csv.DictReader")
    checks["collin_binary_subprocess_capture"] = (
        'text=False' in collin
        and ('bytes(completed.stdout)' in collin or 'bytes(stdout)' in collin)
        and ('capture_output=True' in collin or 'stdout=subprocess.PIPE' in collin)
    )
    checks["collin_capture_precedes_json_parse"] = collin.index("self._last_raw_query_bytes = raw_output") < collin.index('json.loads(output or "[]")')
    checks["no_parsed_serializing_fallback"] = all(term not in invoker_source for term in ("json.dumps", "pickle", ".encode("))
    checks["no_persistence"] = all(term not in invoker_source for term in ("sqlite", "database", "persist("))
    checks["no_evidence_reasoning"] = all(term not in invoker_source for term in ("canonicalevidence", "decisionengine", "confidence"))

    cleanup_cases = {
        "already_exited": CleanupProcess(exited=True),
        "terminate_failure": CleanupProcess(terminate_fails=True, communicate_failures=1),
        "kill_failure": CleanupProcess(
            terminate_fails=True, kill_fails=True, communicate_failures=2,
        ),
        "communicate_failure": CleanupProcess(communicate_failures=2),
        "timeout": CleanupProcess(communicate_failures=1),
    }
    checks["collin_cleanup_all_failure_modes_reaped"] = all(
        CollinBulkDataAdapter._terminate_and_reap(process, 0.001)
        and process.poll() is not None
        for process in cleanup_cases.values()
    )
    checks["collin_cleanup_never_targets_raw_pid"] = all(
        term not in collin for term in ("os.kill", "taskkill", "Stop-Process", ".pid")
    )

    unreapable_process = CleanupProcess(
        terminate_fails=True, kill_fails=True,
        communicate_failures=20, wait_fails=True,
    )
    checks["collin_simultaneous_cleanup_failure_reported"] = (
        not CollinBulkDataAdapter._terminate_and_reap(unreapable_process, 0.001)
        and unreapable_process.poll() is None
    )

    wait_failure_process = CleanupProcess(
        terminate_fails=True, kill_fails=True,
        communicate_failures=20, wait_fails=True,
    )
    original_popen = collin_module.subprocess.Popen
    failed_cleanup_control = OperationControl(10)
    failed_cleanup_control.cancel()
    failed_cleanup_adapter = CollinBulkDataAdapter(
        "FABRICATED", "FABRICATED", operation_control=failed_cleanup_control,
    )
    failed_cleanup_adapter._powershell32 = lambda: str(Path(__file__).resolve())
    collin_module.subprocess.Popen = lambda *args, **kwargs: wait_failure_process
    try:
        try:
            failed_cleanup_adapter._run_script_bytes("FABRICATED")
            primary_preserved = False
            cleanup_reason = None
        except OperationCancelled as exc:
            primary_preserved = True
            cleanup_reason = getattr(exc, "cleanup_reason_code", None)
    finally:
        collin_module.subprocess.Popen = original_popen
    checks["collin_cleanup_failure_preserves_primary_exception"] = (
        primary_preserved and cleanup_reason == COLLIN_CHILD_CLEANUP_FAILED
    )

    completed_unreapable = CompletedButUnreapableProcess()
    completed_adapter = CollinBulkDataAdapter("FABRICATED", "FABRICATED")
    completed_adapter._powershell32 = lambda: str(Path(__file__).resolve())
    original_popen = collin_module.subprocess.Popen
    collin_module.subprocess.Popen = lambda *args, **kwargs: completed_unreapable
    try:
        try:
            completed_adapter._run_script_bytes("FABRICATED")
            explicit_cleanup_failure = False
        except RuntimeError as exc:
            explicit_cleanup_failure = str(exc) == COLLIN_CHILD_CLEANUP_FAILED
    finally:
        collin_module.subprocess.Popen = original_popen
    checks["collin_unreaped_success_candidate_fails_closed"] = explicit_cleanup_failure

    cancellation_process = CleanupProcess(communicate_failures=2)
    original_popen = collin_module.subprocess.Popen
    control = OperationControl(10)
    control.cancel()
    cancellation_adapter = CollinBulkDataAdapter("FABRICATED", "FABRICATED", operation_control=control)
    cancellation_adapter._powershell32 = lambda: str(Path(__file__).resolve())
    collin_module.subprocess.Popen = lambda *args, **kwargs: cancellation_process
    try:
        try:
            cancellation_adapter._run_script_bytes("FABRICATED")
            cancellation_preserved = False
        except OperationCancelled:
            cancellation_preserved = True
    finally:
        collin_module.subprocess.Popen = original_popen
    checks["collin_cancellation_preserved_and_child_reaped"] = (
        cancellation_preserved and cancellation_process.poll() is not None
    )

    privacy_audit = BaseAuditPublisher()
    privacy_adapter = CollinBulkDataAdapter("FABRICATED", "FABRICATED", audit=privacy_audit)
    privacy_adapter._query_rows = lambda _lookup: (_ for _ in ()).throw(
        RuntimeError("ACCESS_QUERY_FAILED: C:\\FABRICATED-PRIVATE-PATH")
    )
    privacy_adapter.retrieve("FABRICATED-RAW-ACCOUNT")
    failure_audit = json.dumps(privacy_audit.events, sort_keys=True)
    checks["collin_failure_audit_closed_and_selector_safe"] = all(
        secret not in failure_audit
        for secret in ("FABRICATED-RAW-ACCOUNT", "FABRICATED-PRIVATE-PATH")
    ) and "ACCESS_QUERY_FAILED" in failure_audit

    warning_audit = BaseAuditPublisher()
    warning_adapter = CollinBulkDataAdapter("FABRICATED", "FABRICATED", audit=warning_audit)
    warning_adapter._query_rows = lambda _lookup: [{"prop_id": "FABRICATED-INTERNAL"}]
    warning_adapter._load_code_lists = lambda: {}
    original_mapper = collin_module.map_collin_row
    collin_module.map_collin_row = lambda _row, _codes: (
        {"city": "FICTIONAL"}, ("FABRICATED-PRIVATE-CODE-VALUE",),
    )
    try:
        warning_adapter.retrieve(
            "FABRICATED-RAW-ACCOUNT", audit_property_id="OP-COLLIN-0123456789ABCDEF0123",
        )
    finally:
        collin_module.map_collin_row = original_mapper
    warning_text = json.dumps(warning_audit.events, sort_keys=True)
    checks["collin_warning_audit_closed_and_selector_safe"] = all(
        secret not in warning_text
        for secret in ("FABRICATED-RAW-ACCOUNT", "FABRICATED-PRIVATE-CODE-VALUE")
    ) and "OP-COLLIN-0123456789ABCDEF0123" in warning_text
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"AX-ADAPT-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
