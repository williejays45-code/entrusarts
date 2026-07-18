"""Focused fabricated verification for the controlled ERA FastAPI boundary."""

import asyncio
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

from era.acquisition.supplemental_evidence import EVIDENCE_SCHEMAS
from era.api.api_audit import ApiAudit
from era.api.service import create_app
from era.api.admission_store import AdmissionStore
from era.api.process_boundary import (
    MAX_FRAME_BODY_BYTES, MAX_STDERR_BYTES, OwnedProcessBoundary,
)


TOKEN = "runtime-only-fabricated-token"
RAW_ADDRESS = "999 FICTIONAL PRIVATE ROAD"
PRIVATE_OWNER = "FABRICATED PRIVATE OWNER"


def safe_report(selector="address"):
    identity = {f"{selector}_identity": {"scheme": "SHA-256-RUN-SALTED", "hash": "a" * 64}}
    return {
        "run_id": "ERA-RUN-FABRICATED", "utc": "2026-01-01T00:00:00+00:00",
        "provider": "collin", "provider_id": "COLLIN_BULK_MDB", "jurisdiction": "TX-COLLIN",
        **identity, "resolution": {"status": "PASS" if selector == "address" else "ACCOUNT_ID_SUPPLIED", "match_count": 1},
        "source_files": [{"name": "FABRICATED.mdb", "sha256": "B" * 64}],
        "acquisition_status": "PASS",
        "evidence_sufficiency": {"normalized_field_count": 5, "expected_fields_present": ["city", "state"],
            "missing_expected_fields": [], "sufficient_for_pipeline": True,
            "normalized_non_personal_facts_sha256": "C" * 64},
        "pipeline_stages": [{"name": "LPA", "status": "PASS", "ok": True}],
        "decision": "PENDING_MORE_EVIDENCE", "confidence": {"status": "NOT_ASSIGNED"},
        "policy_verdict": "EXPORT_APPROVED", "export_status": "EXPORTED",
        "export_label": "INFORMATIONAL INCOMPLETE-EVIDENCE REPORT", "limitations": ["Fabricated test"], "ok": True,
    }


def operator(provider, account_id=None, environ=None, address=None, county="Collin",
             supplemental_evidence=None):
    if provider != "collin": raise ValueError("UNSUPPORTED_PROVIDER;SUPPORTED_PROVIDERS=collin")
    if county != "Collin": raise ValueError("UNSUPPORTED_COUNTY;SUPPORTED_COUNTIES=Collin")
    if address == "NO MATCH": return {**safe_report(), "ok": False, "resolution": {"status": "COLLIN_ADDRESS_NOT_FOUND", "match_count": 0}}
    if address == "AMBIGUOUS": return {**safe_report(), "ok": False, "resolution": {"status": "COLLIN_ADDRESS_AMBIGUOUS", "match_count": 2}}
    return safe_report("account" if account_id else "address")


async def request(app, method, path, body=None, token=None, headers=None, content_length=None):
    raw = b"" if body is None else json.dumps(body).encode()
    header_items = [(b"content-type", b"application/json"), (b"content-length", str(content_length if content_length is not None else len(raw)).encode())]
    if token is not None: header_items.append((b"authorization", f"Bearer {token}".encode()))
    for key, value in (headers or {}).items(): header_items.append((key.lower().encode(), value.encode()))
    messages = []
    received = False
    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message): messages.append(message)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
             "headers": header_items, "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8081)}
    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], json.loads(payload or b"{}")


async def request_raw(app, raw, token=None, content_length=None, omit_length=False,
                      chunks=None, raw_headers=None):
    header_items = [(b"content-type", b"application/json")]
    if not omit_length:
        declared = len(raw) if content_length is None else content_length
        header_items.append((b"content-length", str(declared).encode()))
    if token is not None:
        header_items.append((b"authorization", f"Bearer {token}".encode()))
    header_items.extend(raw_headers or ())
    pending = list(chunks or [raw])
    messages = []
    receive_count = 0
    async def receive():
        nonlocal receive_count
        receive_count += 1
        if pending:
            body = pending.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(pending)}
        return {"type": "http.disconnect"}
    async def send(message): messages.append(message)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
             "scheme": "http", "path": "/v1/property/analyze", "raw_path": b"/v1/property/analyze",
             "query_string": b"", "headers": header_items, "client": ("127.0.0.1", 1),
             "server": ("127.0.0.1", 8081)}
    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], json.loads(payload or b"{}"), receive_count


root = Path(os.environ.get("ERA_API_TEST_ROOT", "pytest-cache-files-era-api")); root.mkdir(parents=True, exist_ok=True)
mdb = root / "FABRICATED.mdb"; xls = root / "FABRICATED.xls"; mdb.write_bytes(b"MDB"); xls.write_bytes(b"XLS")
env = {"ERA_API_BEARER_TOKEN": TOKEN, "ERA_SERVICE_VERSION": "TEST-COMMIT",
       "ERA_COLLIN_MDB_PATH": str(mdb), "ERA_COLLIN_CODE_LIST_PATH": str(xls)}
before = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())
audit = ApiAudit(); app = create_app(env, audit=audit, worker_test_mode="fabricated")
checks = {}

status, health = asyncio.run(request(app, "GET", "/healthz"))
checks["health_response"] = status == 200 and health["status"] == "ok" and health["supported_providers"] == ["collin"]
checks["health_privacy"] = all(value not in json.dumps(health) for value in (TOKEN, str(mdb), str(xls), "ERA_COLLIN"))
body = {"provider": "collin", "county": "Collin", "address": RAW_ADDRESS, "account_id": None}
status, missing = asyncio.run(request(app, "POST", "/v1/property/analyze", body))
checks["missing_bearer"] = status == 401 and missing["error"]["code"] == "BEARER_REQUIRED"
status, invalid = asyncio.run(request(app, "POST", "/v1/property/analyze", body, "wrong"))
checks["invalid_bearer"] = status == 401
status, allowed = asyncio.run(request(app, "POST", "/v1/property/analyze", body, TOKEN, {"x-request-id": "safe-123"}))
checks["valid_authorization"] = status == 200 and allowed["correlation_id"] == "safe-123"
checks["token_never_output_or_audit"] = TOKEN not in json.dumps([health, missing, invalid, allowed, audit.events])
clean_environment_app = create_app(
    env, audit=ApiAudit(), worker_test_mode="environment_clean",
)
checks["worker_environment_excludes_era_secrets"] = asyncio.run(request(
    clean_environment_app, "POST", "/v1/property/analyze", body, TOKEN,
))[0] == 200
bad_selector = {"provider": "collin", "account_id": "A", "address": "B"}
checks["exactly_one_selector"] = asyncio.run(request(app, "POST", "/v1/property/analyze", bad_selector, TOKEN))[0] == 422
checks["address_success"] = allowed["resolution"]["status"] == "PASS"
account_body = {"provider": "collin", "account_id": "FABRICATED-ACCOUNT", "address": None}
checks["account_id_regression"] = asyncio.run(request(app, "POST", "/v1/property/analyze", account_body, TOKEN))[0] == 200
checks["unsupported_provider"] = asyncio.run(request(app, "POST", "/v1/property/analyze", {**body, "provider": "other"}, TOKEN))[1]["error"]["code"] == "UNSUPPORTED_PROVIDER"
checks["county_mismatch"] = asyncio.run(request(app, "POST", "/v1/property/analyze", {**body, "county": "Dallas"}, TOKEN))[1]["error"]["code"] == "UNSUPPORTED_COUNTY"
checks["no_match"] = asyncio.run(request(app, "POST", "/v1/property/analyze", {**body, "address": "NO MATCH"}, TOKEN))[0] == 404
checks["ambiguous_match"] = asyncio.run(request(app, "POST", "/v1/property/analyze", {**body, "address": "AMBIGUOUS"}, TOKEN))[0] == 409
checks["request_size_limit"] = asyncio.run(request(app, "POST", "/v1/property/analyze", body, TOKEN, content_length=5000))[0] == 413
checks["field_length_limit"] = asyncio.run(request(app, "POST", "/v1/property/analyze", {**body, "address": "X" * 257}, TOKEN))[0] == 422
checks["unknown_field_rejected"] = asyncio.run(request(app, "POST", "/v1/property/analyze", {**body, "extra": "x"}, TOKEN))[0] == 422
timeout_env = {**env, "ERA_API_TIMEOUT_SECONDS": "0.05"}
timeout_audit = ApiAudit()
timeout_app = create_app(
    timeout_env, audit=timeout_audit, worker_test_mode="noncooperative",
)
timeout_started = time.monotonic()
timeout_result = asyncio.run(request(timeout_app, "POST", "/v1/property/analyze", body, TOKEN))
timeout_elapsed = time.monotonic() - timeout_started
timeout_audit_count = len(timeout_audit.events)
time.sleep(.02)
checks["timeout_handling"] = timeout_result[0] == 504
checks["timeout_worker_quiescent_before_504"] = (
    timeout_elapsed < .50
)
checks["timeout_no_late_audit"] = len(timeout_audit.events) == timeout_audit_count

late_markers = [
    root / f"LATE-{boundary.upper()}-MARKER"
    for boundary in ("transaction", "persistence", "export", "policy", "audit", "shared-state")
]
revoked_audit = ApiAudit()
revoked_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.05", "ERA_API_QUIESCENCE_SECONDS": "0.10"},
    audit=revoked_audit, worker_test_mode="delayed_mutation",
    worker_test_controls={"delay": .20, "markers": [str(path) for path in late_markers]},
)
revoked_started = time.monotonic()
revoked_result = asyncio.run(request(revoked_app, "POST", "/v1/property/analyze", body, TOKEN))
revoked_elapsed = time.monotonic() - revoked_started
time.sleep(.25)
checks["noncooperative_worker_bounded_504"] = revoked_result[0] == 504 and revoked_elapsed < .50
checks["revoked_worker_cannot_commit_late"] = (
    not any(path.exists() for path in late_markers)
)
checks["timeout_admits_no_business_result"] = (
    not any(event["event_type"] == "API_ANALYZE_ALLOWED" for event in revoked_audit.events)
    and not any(path.exists() for path in late_markers)
)

delivery_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.05"}, audit=ApiAudit(),
    worker_test_mode="delayed_delivery", worker_test_controls={"delay": .20},
)
checks["timeout_during_result_delivery"] = asyncio.run(request(
    delivery_app, "POST", "/v1/property/analyze", body, TOKEN,
))[0] == 504

validation_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.50"}, audit=ApiAudit(),
    worker_test_mode="fabricated", validation_delay_seconds=1.0,
)
validation_started = time.monotonic()
validation_result = asyncio.run(request(
    validation_app, "POST", "/v1/property/analyze", body, TOKEN,
))
checks["slow_candidate_validation_isolated"] = (
    validation_result[0] == 504 and time.monotonic() - validation_started < .90
)

admission_audit = ApiAudit()
admission_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.50"}, audit=admission_audit,
    worker_test_mode="fabricated", admission_delay_seconds=1.0,
)
admission_result = asyncio.run(request(
    admission_app, "POST", "/v1/property/analyze", body, TOKEN,
))
checks["timeout_immediately_before_parent_admission"] = (
    admission_result[0] == 504
    and not any(event["event_type"] == "API_ANALYZE_ALLOWED" for event in admission_audit.events)
)

crash_app = create_app(env, audit=ApiAudit(), worker_test_mode="crash")
malformed_app = create_app(env, audit=ApiAudit(), worker_test_mode="malformed_ipc")
checks["worker_crash_fails_closed"] = asyncio.run(request(
    crash_app, "POST", "/v1/property/analyze", body, TOKEN,
))[0] == 500
checks["malformed_ipc_fails_closed"] = asyncio.run(request(
    malformed_app, "POST", "/v1/property/analyze", body, TOKEN,
))[0] == 500

nested_pid_marker = root / "NESTED-PID"
nested_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.50"}, audit=ApiAudit(),
    worker_test_mode="nested_child", worker_test_controls={"pid_marker": str(nested_pid_marker)},
)
nested_result = asyncio.run(request(
    nested_app, "POST", "/v1/property/analyze", body, TOKEN,
))
nested_stopped = False
if nested_pid_marker.exists():
    nested_pid = int(nested_pid_marker.read_text(encoding="ascii"))
    try:
        os.kill(nested_pid, 0)
    except OSError:
        nested_stopped = True
checks["owned_nested_child_terminated"] = nested_result[0] == 504 and nested_stopped

class ClosureFailureBoundary:
    def run(self, *_args, **_kwargs):
        return type("ClosedResult", (), {
            "outcome": "CLOSURE_FAILED", "stdout": b"", "exit_code": None,
            "tree_closed": False, "elapsed_seconds": 0.0,
        })()

closure_audit = ApiAudit()
closure_app = create_app(
    env, audit=closure_audit, worker_test_mode="fabricated",
    process_boundary_factory=ClosureFailureBoundary,
)
closure_result = asyncio.run(request(
    closure_app, "POST", "/v1/property/analyze", body, TOKEN,
))
closure_text = json.dumps([closure_result, closure_audit.events], sort_keys=True)
checks["unconfirmed_closure_returns_closed_internal_failure"] = (
    closure_result[0] == 500
    and closure_result[1]["error"]["code"] == "ISOLATED_EXECUTION_FAILED"
    and RAW_ADDRESS not in closure_text and TOKEN not in closure_text
)
checks["structured_errors"] = set(missing["error"]) == {"code", "message", "correlation_id"}
checks["pii_response_redaction"] = RAW_ADDRESS not in json.dumps(allowed) and PRIVATE_OWNER not in json.dumps(allowed) and "FABRICATED-ACCOUNT" not in json.dumps(allowed)
checks["audit_allow_event"] = any(e["event_type"] == "API_ANALYZE_ALLOWED" for e in audit.events)
checks["audit_deny_event"] = any(e["event_type"] == "API_ANALYZE_DENIED" for e in audit.events)
original = socket.create_connection; socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError("NETWORK_FORBIDDEN"))
try: checks["no_network_contact"] = asyncio.run(request(app, "POST", "/v1/property/analyze", body, TOKEN))[0] == 200
finally: socket.create_connection = original
after = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())
checks["source_immutability"] = before == after
again = asyncio.run(request(app, "POST", "/v1/property/analyze", body, TOKEN))[1]
checks["deterministic_business_result"] = allowed["decision"] == again["decision"] and allowed["evidence_sufficiency"] == again["evidence_sufficiency"]
invalid_cid = asyncio.run(request(app, "POST", "/v1/property/analyze", body, TOKEN, {"x-request-id": "bad id with spaces"}))[1]["correlation_id"]
checks["safe_correlation_ids"] = invalid_cid.startswith("era-") and " " not in invalid_cid

duplicate_marker = "FABRICATED-REJECTED-VALUE"
duplicate_payloads = [
    b'{"provider":"collin","provider":"collin","account_id":"FAB"}',
    (
        '{"provider":"collin","account_id":"FAB","supplemental_evidence":[{'
        '"evidence_type":"listing_financial_summary",'
        '"evidence_type":"listing_financial_summary",'
        '"source_class":"USER_PROVIDED","observation_utc":"2026-01-01T00:00:00Z",'
        '"evidence_digest":"' + ('0' * 64) + '","verification_status":"UNVERIFIED",'
        '"facts":{"asking_price":1}}]}'
    ).encode(),
    (
        '{"provider":"collin","account_id":"FAB","supplemental_evidence":[{'
        '"evidence_type":"listing_financial_summary","source_class":"USER_PROVIDED",'
        '"observation_utc":"2026-01-01T00:00:00Z","evidence_digest":"' + ('0' * 64) + '",'
        '"verification_status":"UNVERIFIED","facts":{"asking_price":"' + duplicate_marker + '",'
        '"asking_price":1}}]}'
    ).encode(),
]
duplicate_results = [
    asyncio.run(request_raw(app, payload, TOKEN)) for payload in duplicate_payloads
]
checks["duplicate_json_keys_rejected_at_every_depth"] = all(
    status == 422 and response["error"]["code"] == "INVALID_REQUEST"
    for status, response, _count in duplicate_results
)
checks["duplicate_rejected_values_not_disclosed"] = duplicate_marker not in json.dumps(
    [response for _status, response, _count in duplicate_results] + audit.events,
    sort_keys=True,
)

numeric_fields = [
    (kind, field_name)
    for kind, schema in EVIDENCE_SCHEMAS.items()
    for field_name, rule in schema["fields"].items()
    if rule["kind"] in {"number", "integer"}
]
boolean_statuses = []
for kind, field_name in numeric_fields:
    boolean_body = {
        "provider": "collin", "account_id": "FAB",
        "supplemental_evidence": [{
            "evidence_type": kind, "source_class": "USER_PROVIDED",
            "observation_utc": "2026-01-01T00:00:00Z",
            "evidence_digest": "0" * 64, "verification_status": "UNVERIFIED",
            "facts": {field_name: True},
        }],
    }
    boolean_statuses.append(
        asyncio.run(request(app, "POST", "/v1/property/analyze", boolean_body, TOKEN))[0]
    )
checks["booleans_rejected_in_every_numeric_field"] = (
    len(boolean_statuses) == len(numeric_fields) and all(status == 422 for status in boolean_statuses)
)

missing_length = asyncio.run(request_raw(app, json.dumps(body).encode(), TOKEN, omit_length=True))
false_length = asyncio.run(request_raw(app, json.dumps(body).encode(), TOKEN, content_length="false"))
underreported = asyncio.run(request_raw(app, b" " * 5000, TOKEN, content_length=10))
incremental = asyncio.run(request_raw(
    app, b"", TOKEN, content_length=10,
    chunks=[b" " * 4096, b"X", b"SHOULD-NOT-BE-READ"],
))
checks["content_length_absent_fails_closed"] = missing_length[0] == 411
checks["content_length_false_fails_closed"] = false_length[0] == 400
checks["content_length_underreported_fails_closed"] = underreported[0] == 413
checks["incremental_limit_stops_at_byte_4097"] = incremental[0] == 413 and incremental[2] == 2

framing_payload = json.dumps(body).encode()
duplicate_equal = asyncio.run(request_raw(
    app, framing_payload, TOKEN, omit_length=True,
    raw_headers=[(b"content-length", str(len(framing_payload)).encode()),
                 (b"content-length", str(len(framing_payload)).encode())],
))
duplicate_conflicting = asyncio.run(request_raw(
    app, framing_payload, TOKEN, omit_length=True,
    raw_headers=[(b"content-length", b"10"), (b"content-length", b"5000")],
))
malformed_lengths = ["+10", "-1", "1,0", "01", " 10", "10 "]
malformed_results = [
    asyncio.run(request_raw(app, framing_payload, TOKEN, content_length=value))[0]
    for value in malformed_lengths
]
checks["duplicate_content_length_rejected"] = (
    duplicate_equal[0] == 400 and duplicate_conflicting[0] == 400
    and duplicate_equal[2] == 0 and duplicate_conflicting[2] == 0
)
checks["malformed_content_length_rejected_before_body"] = all(
    status == 400 for status in malformed_results
)

whitespace_statuses = []
for whitespace_value in (" 1000", "1000 ", "\t1000", "\n1000", "\u00a01000"):
    whitespace_body = {
        "provider": "collin", "account_id": "FAB",
        "supplemental_evidence": [{
            "evidence_type": "listing_financial_summary",
            "source_class": "USER_PROVIDED",
            "observation_utc": "2026-01-01T00:00:00Z",
            "evidence_digest": "0" * 64,
            "verification_status": "UNVERIFIED",
            "facts": {"asking_price": whitespace_value},
        }],
    }
    whitespace_statuses.append(
        asyncio.run(request(app, "POST", "/v1/property/analyze", whitespace_body, TOKEN))[0]
    )
checks["numeric_boundary_whitespace_rejected"] = all(
    status == 422 for status in whitespace_statuses
)

# API-ISO-001-R4: deadline governs PREPARED -> ADMITTED, not transport.
durable_store = AdmissionStore(str(root / "R4-ADMISSION.db"))
pre_admission_audit = ApiAudit()
pre_admission_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.50"}, audit=pre_admission_audit,
    worker_test_mode="fabricated", admission_delay_seconds=.60,
    admission_store=durable_store,
)
pre_admission_result = asyncio.run(request(
    pre_admission_app, "POST", "/v1/property/analyze", body, TOKEN,
))
checks["deadline_blocks_prepared_admission_commit"] = (
    pre_admission_result[0] == 504 and durable_store.counts() == (0, 0)
    and not any(e["event_type"] == "API_ANALYZE_ALLOWED" for e in pre_admission_audit.events)
)

class SlowPostAdmissionAudit(ApiAudit):
    def publish(self, event_type, payload):
        if event_type == "API_ANALYZE_ALLOWED":
            time.sleep(.60)
        return super().publish(event_type, payload)

post_store = AdmissionStore(str(root / "R4-POST-ADMISSION.db"))
post_audit = SlowPostAdmissionAudit()
post_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.50"}, audit=post_audit,
    worker_test_mode="fabricated", admission_store=post_store,
)
post_started = time.monotonic()
idempotency_headers = {"x-request-id": "r4-idempotent"}
post_result = asyncio.run(request(
    post_app, "POST", "/v1/property/analyze", body, TOKEN, idempotency_headers,
))
checks["transport_delay_after_admission_does_not_rollback"] = (
    post_result[0] == 200 and time.monotonic() - post_started > .50
    and post_store.counts() == (1, 1)
    and sum(e["event_type"] == "API_ANALYZE_ALLOWED" for e in post_audit.events) == 1
)

# Async supervision must leave the event loop responsive and cancellation-safe.
responsive_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "0.50"}, audit=ApiAudit(),
    worker_test_mode="noncooperative",
)
async def responsiveness_check():
    started = time.monotonic(); fired = []
    async def ticker():
        await asyncio.sleep(.05); fired.append(time.monotonic() - started)
    await asyncio.gather(request(responsive_app, "POST", "/v1/property/analyze", body, TOKEN), ticker())
    return fired[0]
checks["event_loop_ticker_under_150ms"] = asyncio.run(responsiveness_check()) <= .15

cancel_marker = root / "R4-CANCEL-LATE-MUTATION"
cancel_store = AdmissionStore(str(root / "R4-CANCEL-ADMISSION.db"))
cancel_app = create_app(
    {**env, "ERA_API_TIMEOUT_SECONDS": "5.0"}, audit=ApiAudit(),
    worker_test_mode="delayed_mutation",
    worker_test_controls={"delay": .30, "marker": str(cancel_marker)},
    admission_store=cancel_store,
)
async def cancellation_check():
    task = asyncio.create_task(request(cancel_app, "POST", "/v1/property/analyze", body, TOKEN))
    await asyncio.sleep(.08); task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(.35)
    return not cancel_marker.exists() and cancel_store.counts() == (0, 0)
checks["client_cancellation_closes_worker_without_late_mutation"] = asyncio.run(cancellation_check())

repeat_markers = [root / f"R4-REPEAT-CANCEL-{index}" for index in range(3)]
for marker in repeat_markers:
    marker.unlink(missing_ok=True)
async def repeated_cancellation_check():
    for marker in repeat_markers:
        repeated = create_app(
            {**env, "ERA_API_TIMEOUT_SECONDS": "5.0"}, audit=ApiAudit(),
            worker_test_mode="delayed_mutation",
            worker_test_controls={"delay": .30, "marker": str(marker)},
        )
        task = asyncio.create_task(request(repeated, "POST", "/v1/property/analyze", body, TOKEN))
        await asyncio.sleep(.06); task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await asyncio.sleep(.35)
    clean = not any(marker.exists() for marker in repeat_markers)
    for marker in repeat_markers:
        marker.unlink(missing_ok=True)
    return clean
checks["repeated_cancellation_has_no_late_mutation"] = asyncio.run(repeated_cancellation_check())

class ControllerFailureBoundary:
    def run(self, *_args, **_kwargs):
        raise RuntimeError("FABRICATED_CONTROLLER_DETAIL")
    def cancel(self, _seconds):
        return True
    def wait_closed(self, _seconds):
        return True

controller_audit = ApiAudit()
controller_app = create_app(
    env, audit=controller_audit, worker_test_mode="fabricated",
    process_boundary_factory=ControllerFailureBoundary,
)
controller_result = asyncio.run(request(
    controller_app, "POST", "/v1/property/analyze", body, TOKEN,
))
controller_text = json.dumps([controller_result, controller_audit.events], sort_keys=True)
checks["controller_failure_is_closed_and_private"] = (
    controller_result[0] == 500 and "FABRICATED_CONTROLLER_DETAIL" not in controller_text
)

idempotent_before = sum(
    event["event_type"] == "API_ANALYZE_ALLOWED" for event in post_audit.events
)
idempotent_repeat = asyncio.run(request(
    post_app, "POST", "/v1/property/analyze", body, TOKEN, idempotency_headers,
))
idempotent_after = sum(
    event["event_type"] == "API_ANALYZE_ALLOWED" for event in post_audit.events
)
checks["admission_and_audit_intent_are_idempotent"] = (
    idempotent_repeat[0] == 200 and post_store.counts() == (1, 1)
    and idempotent_after == idempotent_before
)

# Exact framed IPC boundary cases.
def boundary_for(code):
    return OwnedProcessBoundary([sys.executable, "-B", "-c", code])
def run_boundary(code, timeout=1.0):
    boundary = boundary_for(code)
    result = boundary.run(b"{}", timeout, .15)
    return boundary, result
exact_code = (
    "import sys;sys.stdin.buffer.read();b=b'X'*%d;"
    "sys.stdout.buffer.write(str(len(b)).encode()+b'\\n'+b)" % MAX_FRAME_BODY_BYTES
)
exact_boundary, exact_result = run_boundary(exact_code)
checks["ipc_exact_maximum_bounded"] = (
    exact_result.outcome == "COMPLETED"
    and len(exact_result.stdout) == MAX_FRAME_BODY_BYTES
    and exact_boundary.last_retained_stdout_bytes == MAX_FRAME_BODY_BYTES
)
ipc_bad_cases = {
    "maximum_plus_one": "import sys;sys.stdin.buffer.read();b=b'X'*%d;sys.stdout.buffer.write(str(len(b)).encode()+b'\\n'+b)" % (MAX_FRAME_BODY_BYTES + 1),
    "eight_mib": "import sys;sys.stdin.buffer.read();b=b'X'*(8*1024*1024);sys.stdout.buffer.write(str(len(b)).encode()+b'\\n'+b)",
    "false_short": "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'1\\n{}')",
    "false_long": "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'10\\n{}')",
    "truncated": "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'5\\nabc')",
    "malformed": "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'+5\\nabcde')",
    "overlong": "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'1'*21+b'\\nX')",
    "trailing": "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'2\\n{}X')",
    "endless": "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'1\\nX');sys.stdout.buffer.flush();\nwhile True: sys.stdout.buffer.write(b'Y'*4096);sys.stdout.buffer.flush()",
    "stderr_oversized": "import sys;sys.stdin.buffer.read();sys.stderr.buffer.write(b'E'*%d);sys.stderr.buffer.flush();sys.stdout.buffer.write(b'2\\n{}')" % (MAX_STDERR_BYTES + 1),
    "dual_saturation": "import sys,threading;sys.stdin.buffer.read();t=threading.Thread(target=lambda:sys.stderr.buffer.write(b'E'*1000000));t.start();sys.stdout.buffer.write(b'1\\nX'+b'Y'*1000000);sys.stdout.buffer.flush();t.join()",
}
ipc_results = {name: run_boundary(code) for name, code in ipc_bad_cases.items()}
checks["ipc_invalid_frames_fail_closed"] = all(
    result.outcome in {"IPC_FAILED", "TIMEOUT"} and result.tree_closed
    for _boundary, result in ipc_results.values()
)
checks["ipc_memory_limits_enforced"] = all(
    boundary.last_retained_stdout_bytes <= MAX_FRAME_BODY_BYTES + 1
    and boundary.last_retained_stderr_bytes <= MAX_STDERR_BYTES + 1
    for boundary, _result in ipc_results.values()
)

duplicate_ipc = b'{"protocol":"ERA-API-ISOLATED-001","status":"ERROR","status":"CANDIDATE"}'
try:
    app.state.era_service._decode_worker_response(duplicate_ipc, {"CANDIDATE", "ERROR"})
    duplicate_rejected = False
except Exception:
    duplicate_rejected = True
checks["duplicate_ipc_keys_rejected"] = duplicate_rejected

unknown_ipc = b'{"protocol":"ERA-API-ISOLATED-001","status":"ERROR","reason_code":"ACCESS_QUERY_FAILED","extra":1}'
try:
    app.state.era_service._decode_worker_response(unknown_ipc, {"CANDIDATE", "ERROR"})
    unknown_rejected = False
except Exception:
    unknown_rejected = True
checks["ipc_exact_schema_rejects_unknown_fields"] = unknown_rejected

for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values()); print(f"ERA PROPERTY API CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
