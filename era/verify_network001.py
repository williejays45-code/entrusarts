import sys
from era.network.mock_transport import MockHttpTransport
from era.network.network_client import NetworkClient
from era.network.network_models import HttpResponse
from era.network.http_transport import TransportError, HttpTransport
from era.network import network_errors as errors
from era.acquisition.retry_executor import RetryExecutor, TRANSIENT_STATUSES
from era.acquisition.connector_models import RetryPolicy
from era.shared.audit import BaseAuditPublisher

print("NETWORK-001 VERIFICATION")
print("=" * 70)

checks = {}


class FakeSleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


# --- 1. Successful response returns provider payload. ------------------
transport = MockHttpTransport()
client = NetworkClient(transport)
transport.set_response("http://county.test/api/property/1", HttpResponse(200, '{"address": "1 Main St"}'))
status, payload = client.request_json("GET", "http://county.test/api/property/1")
checks["successful_response_returns_payload"] = (
    status == errors.PASS and payload["json"] == {"address": "1 Main St"}
)
checks["successful_response_includes_status_code_and_text"] = (
    payload["status_code"] == 200 and payload["text"] == '{"address": "1 Main St"}'
)

# --- 2. Timeout maps to transient failure. ------------------------------
transport.set_error("http://county.test/timeout", "TIMEOUT", "read timed out")
status, payload = client.request("GET", "http://county.test/timeout")
checks["timeout_maps_to_transport_timeout"] = status == errors.TRANSPORT_TIMEOUT and payload is None
checks["timeout_is_in_transient_statuses"] = errors.TRANSPORT_TIMEOUT in TRANSIENT_STATUSES

# --- 3. Connection error maps to transient failure. ---------------------
transport.set_error("http://county.test/unreachable", "CONNECTION_ERROR", "connection refused")
status, payload = client.request("GET", "http://county.test/unreachable")
checks["connection_error_maps_to_transport_connection_error"] = (
    status == errors.TRANSPORT_CONNECTION_ERROR and payload is None
)
checks["connection_error_is_in_transient_statuses"] = (
    errors.TRANSPORT_CONNECTION_ERROR in TRANSIENT_STATUSES
)

# --- 4. HTTP 429 maps to rate limited. -----------------------------------
transport.set_response("http://county.test/throttled", HttpResponse(429, "Too Many Requests"))
status, payload = client.request("GET", "http://county.test/throttled")
checks["http_429_maps_to_rate_limited"] = (
    status == errors.TRANSPORT_RATE_LIMITED and payload["status_code"] == 429
)
checks["rate_limited_is_in_transient_statuses"] = errors.TRANSPORT_RATE_LIMITED in TRANSIENT_STATUSES

# --- 5. HTTP 500 maps to transient failure. -------------------------------
transport.set_response("http://county.test/broken", HttpResponse(500, "Internal Server Error"))
status, payload = client.request("GET", "http://county.test/broken")
checks["http_500_maps_to_server_error"] = (
    status == errors.TRANSPORT_SERVER_ERROR and payload["status_code"] == 500
)
checks["server_error_is_in_transient_statuses"] = errors.TRANSPORT_SERVER_ERROR in TRANSIENT_STATUSES

# --- 6. HTTP 403 maps to authorization failure and is NOT retried. -------
transport.set_response("http://county.test/forbidden", HttpResponse(403, "Forbidden"))
status, payload = client.request("GET", "http://county.test/forbidden")
checks["http_403_maps_to_unauthorized"] = (
    status == errors.TRANSPORT_UNAUTHORIZED and payload["status_code"] == 403
)
checks["unauthorized_is_not_in_transient_statuses"] = (
    errors.TRANSPORT_UNAUTHORIZED not in TRANSIENT_STATUSES
)

# --- 7. Invalid response maps cleanly (malformed JSON where JSON was
# explicitly required via request_json -- never raises). ------------------
transport.set_response("http://county.test/garbled", HttpResponse(200, "not valid json {{{"))
status, payload = client.request_json("GET", "http://county.test/garbled")
checks["invalid_json_response_maps_cleanly"] = status == errors.TRANSPORT_INVALID_RESPONSE
checks["invalid_json_response_no_exception_raised"] = True  # would have raised above already if not caught

transport.set_response("http://county.test/empty", HttpResponse(200, ""))
status, payload = client.request_json("GET", "http://county.test/empty")
checks["empty_body_json_request_maps_cleanly"] = status == errors.TRANSPORT_INVALID_RESPONSE

# Generic (non-JSON-required) request() does NOT treat a non-JSON body
# as an error -- plenty of legitimate responses aren't JSON.
transport.set_response("http://county.test/html", HttpResponse(200, "<html>ok</html>"))
status, payload = client.request("GET", "http://county.test/html")
checks["generic_request_does_not_reject_non_json_2xx"] = status == errors.PASS

# --- other status coverage: 404 and generic 4xx, for completeness ---------
transport.set_response("http://county.test/missing", HttpResponse(404, "Not Found"))
status, _ = client.request("GET", "http://county.test/missing")
checks["http_404_maps_to_not_found"] = status == errors.TRANSPORT_NOT_FOUND
checks["not_found_is_not_in_transient_statuses"] = errors.TRANSPORT_NOT_FOUND not in TRANSIENT_STATUSES

transport.set_response("http://county.test/badrequest", HttpResponse(400, "Bad Request"))
status, _ = client.request("GET", "http://county.test/badrequest")
checks["http_400_maps_to_client_error"] = status == errors.TRANSPORT_CLIENT_ERROR
checks["client_error_is_not_in_transient_statuses"] = errors.TRANSPORT_CLIENT_ERROR not in TRANSIENT_STATUSES

# --- 8. No raw network exception escapes, even for an unexpected
# transport failure kind. ---------------------------------------------------
transport.set_error("http://county.test/weird", "SOMETHING_WEIRD", "unclassified failure")
raised = False
try:
    status, payload = client.request("GET", "http://county.test/weird")
except Exception:
    raised = True
checks["unclassified_transport_error_does_not_raise"] = not raised
checks["unclassified_transport_error_maps_to_unknown"] = status == errors.TRANSPORT_UNKNOWN_ERROR

# A transport implementation that raises something OTHER than
# TransportError entirely (a bug in a hypothetical future real
# transport) must still not escape NetworkClient.request().
class MisbehavingTransport(HttpTransport):
    def send(self, request):
        raise RuntimeError("a transport implementation bug, not a TransportError")

misbehaving_client = NetworkClient(MisbehavingTransport())
raised2 = False
try:
    status2, payload2 = misbehaving_client.request("GET", "http://county.test/anything")
except Exception:
    raised2 = True
checks["non_transport_error_exception_also_does_not_raise"] = not raised2
checks["non_transport_error_exception_maps_to_unknown"] = status2 == errors.TRANSPORT_UNKNOWN_ERROR

# --- 9. Retry wraps a transient network failure -- integration between
# RetryExecutor and the network layer's own statuses. -----------------------
audit = BaseAuditPublisher()
sleeper = FakeSleeper()
executor = RetryExecutor(audit=audit, sleep_fn=sleeper)
retry_policy = RetryPolicy(max_retries=3, retry_delay_seconds=2)

flaky_transport = MockHttpTransport()
flaky_client = NetworkClient(flaky_transport)
call_log = {"n": 0}

def flaky_network_call():
    call_log["n"] += 1
    if call_log["n"] == 1:
        flaky_transport.set_error("http://county.test/flaky", "TIMEOUT")
    elif call_log["n"] == 2:
        flaky_transport.set_response("http://county.test/flaky", HttpResponse(500, "still broken"))
    else:
        flaky_transport.set_response("http://county.test/flaky", HttpResponse(200, '{"ok": true}'))
    return flaky_client.request_json("GET", "http://county.test/flaky")

status, result = executor.run("COUNTY_TEST", retry_policy, flaky_network_call)
checks["retry_wraps_transient_network_failure_and_succeeds"] = (
    status == errors.PASS and result["json"] == {"ok": True}
)
checks["retry_wrapped_network_failure_took_three_attempts"] = call_log["n"] == 3
checks["retry_wrapped_network_failure_recorded_attempts"] = any(
    e["event_type"] == "RETRY_ATTEMPTED" for e in audit.events
)
checks["retry_wrapped_network_failure_recorded_success"] = any(
    e["event_type"] == "RETRY_SUCCEEDED" and e["payload"]["attempts"] == 3 for e in audit.events
)

# 403 through the retry executor must NOT be retried, even though it
# came from the network layer.
audit2 = BaseAuditPublisher()
sleeper2 = FakeSleeper()
executor2 = RetryExecutor(audit=audit2, sleep_fn=sleeper2)
forbidden_transport = MockHttpTransport()
forbidden_transport.set_response("http://county.test/nope", HttpResponse(403, "Forbidden"))
forbidden_client = NetworkClient(forbidden_transport)
forbidden_log = {"n": 0}

def forbidden_call():
    forbidden_log["n"] += 1
    return forbidden_client.request("GET", "http://county.test/nope")

status, result = executor2.run("COUNTY_TEST", retry_policy, forbidden_call)
checks["http_403_through_retry_executor_not_retried"] = (
    forbidden_log["n"] == 1 and status == errors.TRANSPORT_UNAUTHORIZED
)
checks["http_403_through_retry_executor_no_sleep"] = len(sleeper2.calls) == 0

# --- 10. No raw network exception escapes RetryExecutor either, even
# when every attempt fails at the transport level. ---------------------------
audit3 = BaseAuditPublisher()
sleeper3 = FakeSleeper()
executor3 = RetryExecutor(audit=audit3, sleep_fn=sleeper3)
always_down_transport = MockHttpTransport()
always_down_transport.set_error("http://county.test/down", "CONNECTION_ERROR")
always_down_client = NetworkClient(always_down_transport)

raised3 = False
try:
    status3, result3 = executor3.run(
        "COUNTY_TEST", retry_policy,
        lambda: always_down_client.request("GET", "http://county.test/down"),
    )
except Exception:
    raised3 = True
checks["retry_executor_never_raises_on_persistent_network_failure"] = not raised3
checks["retry_executor_exhausts_and_returns_clean_status"] = status3 == errors.TRANSPORT_CONNECTION_ERROR

# --- 11. No live provider dependency / no scraping: confirm nothing in
# the container or any connector constructs a real transport or a
# NetworkClient anywhere reachable by the pipeline yet. -----------------------
import era.container as container_module
import inspect
container_source = inspect.getsource(container_module)
checks["container_does_not_reference_network_client"] = "NetworkClient" not in container_source
checks["container_does_not_reference_urllib_transport"] = "UrllibHttpTransport" not in container_source

# --- 12. Preserve rate limit gate before network calls: this is a
# structural confirmation that RATE-RETRY-001's gate still sits before
# LPA in the pipeline -- NETWORK-001 didn't move or bypass it, because
# it isn't wired into the pipeline at all yet. --------------------------------
import era.pipeline as pipeline_module
pipeline_source = inspect.getsource(pipeline_module)
rate_limit_index = pipeline_source.index('record_stage("RATE_LIMIT"')
lpa_index = pipeline_source.index('record_stage("LPA"')
checks["rate_limit_gate_still_precedes_lpa_in_pipeline_source"] = rate_limit_index < lpa_index

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"NETWORK-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
