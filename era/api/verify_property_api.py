"""Focused fabricated verification for the controlled ERA FastAPI boundary."""

import asyncio
import hashlib
import json
import os
import socket
import time
from pathlib import Path

from era.api.api_audit import ApiAudit
from era.api.service import create_app


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


def operator(provider, account_id=None, environ=None, address=None, county="Collin"):
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


root = Path(os.environ.get("ERA_API_TEST_ROOT", "pytest-cache-files-era-api")); root.mkdir(parents=True, exist_ok=True)
mdb = root / "FABRICATED.mdb"; xls = root / "FABRICATED.xls"; mdb.write_bytes(b"MDB"); xls.write_bytes(b"XLS")
env = {"ERA_API_BEARER_TOKEN": TOKEN, "ERA_SERVICE_VERSION": "TEST-COMMIT",
       "ERA_COLLIN_MDB_PATH": str(mdb), "ERA_COLLIN_CODE_LIST_PATH": str(xls)}
before = (hashlib.sha256(mdb.read_bytes()).hexdigest(), hashlib.sha256(xls.read_bytes()).hexdigest())
audit = ApiAudit(); app = create_app(env, operator=operator, audit=audit)
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
def slow_operator(*args, **kwargs): time.sleep(.05); return safe_report()
timeout_env = {**env, "ERA_API_TIMEOUT_SECONDS": "0.001"}
checks["timeout_handling"] = asyncio.run(request(create_app(timeout_env, slow_operator), "POST", "/v1/property/analyze", body, TOKEN))[0] == 504
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

for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values()); print(f"ERA PROPERTY API CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
