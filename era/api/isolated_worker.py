"""Unprivileged computation/validation worker for the ERA property API.

This module owns no API audit object, persistence store, bearer token, or
publication handle.  It communicates one bounded JSON result candidate over
stdout.  The parent remains the sole admission authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time


PROTOCOL = "ERA-API-ISOLATED-001"
MAX_WORKER_REQUEST_BYTES = 64 * 1024
MAX_CANDIDATE_BYTES = 256 * 1024
FORBIDDEN_REPORT_KEYS = frozenset({
    "owner", "owner_name", "owner_identity", "owner_mailing_address",
    "mailing_address", "phone", "telephone", "account_id", "parcel_id",
    "raw_row", "raw_rows", "source_reference", "local_path", "address",
    "property_address", "situs_address",
})
SAFE_WORKER_ERRORS = frozenset({
    "PROVIDER_REQUIRED", "UNSUPPORTED_PROVIDER", "UNSUPPORTED_COUNTY",
    "EXACTLY_ONE_SELECTOR_REQUIRED", "COLLIN_SOURCE_PATHS_REQUIRED",
    "COLLIN_SOURCE_PATH_NOT_FOUND", "COLLIN_ADDRESS_NOT_FOUND",
    "COLLIN_ADDRESS_AMBIGUOUS", "COLLIN_RECORD_NOT_FOUND",
    "COLLIN_RECORD_AMBIGUOUS", "ACCESS_DRIVER_MISSING",
    "ACCESS_SOURCE_MISSING", "ACCESS_TABLE_MISSING", "ACCESS_QUERY_FAILED",
    "CODE_LIST_SOURCE_MISSING", "SUPPLEMENTAL_EVIDENCE_CONFLICT",
    "INVALID_SUPPLEMENTAL_EVIDENCE", "OPERATION_CANCELLED",
    "COLLIN_CHILD_CLEANUP_FAILED",
})


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest().upper()


def _safe_report(selector="address", *, ok=True, resolution=None):
    identity = {
        f"{selector}_identity": {
            "scheme": "SHA-256-RUN-SALTED", "hash": "a" * 64,
        }
    }
    return {
        "run_id": "ERA-RUN-FABRICATED", "utc": "2026-01-01T00:00:00+00:00",
        "provider": "collin", "provider_id": "COLLIN_BULK_MDB",
        "jurisdiction": "TX-COLLIN", **identity,
        "resolution": {
            "status": resolution or ("PASS" if selector == "address" else "ACCOUNT_ID_SUPPLIED"),
            "match_count": 1 if resolution is None else (2 if resolution.endswith("AMBIGUOUS") else 0),
        },
        "source_files": [{"name": "FABRICATED.mdb", "sha256": "B" * 64}],
        "acquisition_status": "PASS" if ok else "NOT_STARTED",
        "evidence_sufficiency": {
            "normalized_field_count": 5,
            "expected_fields_present": ["city", "state"],
            "missing_expected_fields": [], "sufficient_for_pipeline": True,
            "normalized_non_personal_facts_sha256": "C" * 64,
        } if ok else None,
        "pipeline_stages": [{"name": "LPA", "status": "PASS", "ok": True}] if ok else [],
        "decision": "PENDING_MORE_EVIDENCE" if ok else None,
        "confidence": {"status": "NOT_ASSIGNED"},
        "policy_verdict": "EXPORT_APPROVED" if ok else None,
        "export_status": "EXPORTED" if ok else None,
        "export_label": "INFORMATIONAL INCOMPLETE-EVIDENCE REPORT" if ok else None,
        "limitations": ["Fabricated test"], "ok": ok,
    }


def _compute(request):
    test_mode = request.get("test_mode")
    item = request["item"]
    controls = request.get("test_controls") or {}
    if test_mode:
        if test_mode == "fabricated":
            if item.get("provider") != "collin":
                raise ValueError("UNSUPPORTED_PROVIDER")
            if item.get("county") not in (None, "Collin"):
                raise ValueError("UNSUPPORTED_COUNTY")
            if item.get("address") == "NO MATCH":
                return _safe_report(ok=False, resolution="COLLIN_ADDRESS_NOT_FOUND")
            if item.get("address") == "AMBIGUOUS":
                return _safe_report(ok=False, resolution="COLLIN_ADDRESS_AMBIGUOUS")
            return _safe_report("account" if item.get("account_id") else "address")
        if test_mode == "environment_clean":
            if any(key.upper().startswith("ERA_") for key in os.environ):
                raise RuntimeError("WORKER_ENVIRONMENT_NOT_CLEAN")
            return _safe_report("account" if item.get("account_id") else "address")
        if test_mode == "noncooperative":
            while True:
                time.sleep(1)
        if test_mode == "delayed_mutation":
            time.sleep(float(controls.get("delay", 1)))
            markers = controls.get("markers") or [controls["marker"]]
            for marker in markers:
                with open(marker, "xb") as stream:
                    stream.write(b"FABRICATED-LATE-MUTATION")
            while True:
                time.sleep(1)
        if test_mode == "delayed_delivery":
            time.sleep(float(controls.get("delay", 1)))
            return _safe_report()
        if test_mode == "nested_child":
            child = subprocess.Popen(
                [sys.executable, "-B", "-c", "import time; time.sleep(60)"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            marker = controls.get("pid_marker")
            if marker:
                with open(marker, "x", encoding="ascii") as stream:
                    stream.write(str(child.pid))
            while True:
                time.sleep(1)
        if test_mode == "crash":
            os._exit(71)
        raise RuntimeError("WORKER_TEST_MODE_INVALID")

    from era.run_property import execute_operator
    environ = {
        key: value for key, value in request.get("operator_environment", {}).items()
        if key in {"ERA_COLLIN_MDB_PATH", "ERA_COLLIN_CODE_LIST_PATH"}
    }
    return execute_operator(
        item.get("provider"), item.get("account_id"), environ=environ,
        address=item.get("address"), county=item.get("county") or "Collin",
        supplemental_evidence=item.get("supplemental_evidence") or (),
    )


def _walk_report(value, selectors, source_paths):
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_REPORT_KEYS:
                raise ValueError("CANDIDATE_PRIVACY_VIOLATION")
            _walk_report(child, selectors, source_paths)
    elif isinstance(value, list):
        for child in value:
            _walk_report(child, selectors, source_paths)
    elif isinstance(value, str):
        if value in selectors or any(path and path in value for path in source_paths):
            raise ValueError("CANDIDATE_PRIVACY_VIOLATION")


def _validate(request):
    delay = float(request.get("validation_delay_seconds", 0))
    if delay:
        time.sleep(delay)
    candidate = request.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("CANDIDATE_INVALID")
    required = {
        "run_id", "provider", "jurisdiction", "resolution", "source_files",
        "acquisition_status", "pipeline_stages", "decision", "confidence",
        "policy_verdict", "export_status", "limitations", "ok",
    }
    if not required.issubset(candidate):
        raise ValueError("CANDIDATE_INVALID")
    if candidate.get("provider") != "collin" or candidate.get("jurisdiction") != "TX-COLLIN":
        raise ValueError("CANDIDATE_INVALID")
    selectors = frozenset(str(value) for value in request.get("selectors", ()) if value)
    source_paths = frozenset(str(value) for value in request.get("source_paths", ()) if value)
    _walk_report(candidate, selectors, source_paths)
    encoded = _canonical(candidate)
    if len(encoded) > MAX_CANDIDATE_BYTES:
        raise ValueError("CANDIDATE_TOO_LARGE")
    supplied_digest = request.get("candidate_digest")
    if supplied_digest != hashlib.sha256(encoded).hexdigest().upper():
        raise ValueError("CANDIDATE_DIGEST_INVALID")
    return candidate


def _safe_code(exc):
    code = str(exc).split(";", 1)[0].split(":", 1)[0]
    return code if code in SAFE_WORKER_ERRORS else "WORKER_COMPUTATION_FAILED"


def _emit(response):
    encoded = _canonical(response)
    if len(encoded) > MAX_CANDIDATE_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    sys.stdout.buffer.write(str(len(encoded)).encode("ascii") + b"\n" + encoded)


def main():
    raw = sys.stdin.buffer.read(MAX_WORKER_REQUEST_BYTES + 1)
    if len(raw) > MAX_WORKER_REQUEST_BYTES:
        raise SystemExit(65)
    try:
        request = json.loads(raw.decode("utf-8"))
        if request.get("protocol") != PROTOCOL:
            raise ValueError("PROTOCOL_INVALID")
        if request.get("test_mode") == "malformed_ipc":
            sys.stdout.buffer.write(b"not-json")
            return 0
        if request.get("kind") == "COMPUTE":
            try:
                candidate = _compute(request)
            except (ValueError, RuntimeError) as exc:
                response = {
                    "protocol": PROTOCOL, "status": "ERROR",
                    "reason_code": _safe_code(exc),
                }
            else:
                response = {
                    "protocol": PROTOCOL, "status": "CANDIDATE",
                    "candidate": candidate,
                }
        elif request.get("kind") == "VALIDATE":
            validated = _validate(request)
            response = {
                "protocol": PROTOCOL, "status": "CANDIDATE",
                "candidate": validated,
            }
        else:
            raise ValueError("REQUEST_KIND_INVALID")
        _emit(response)
        return 0
    except Exception:
        response = {
            "protocol": PROTOCOL, "status": "ERROR",
            "reason_code": "WORKER_PROTOCOL_FAILED",
        }
        _emit(response)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
