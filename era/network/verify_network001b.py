import sys
from era.network.mock_transport import MockHttpTransport
from era.network.network_client import NetworkClient
from era.network.network_models import HttpResponse
from era.network.http_transport import TransportError
from era.network import network_errors as errors
from era.acquisition.retry_executor import RetryExecutor, TRANSIENT_STATUSES
from era.acquisition.connector_models import RetryPolicy
from era.shared.audit import BaseAuditPublisher

print("NETWORK-001B VERIFICATION -- binary/ZIP support on the integrated transport spine")
print("=" * 70)

checks = {}

VALID_ZIP = b"PK\x03\x04" + b"DCAD-CERTIFIED-DATA-2025-SAMPLE-BYTES"
URL = "https://example.test/dcad-data-products/2025-certified.zip"


class FakeSleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


# --- 1. Valid ZIP bytes pass through untouched, no UTF-8 coercion. -------
transport = MockHttpTransport()
client = NetworkClient(transport)
transport.set_response(URL, HttpResponse(200, "", content=VALID_ZIP))
status, payload = client.request_bytes("GET", URL, require_zip=True)
checks["valid_zip_returns_pass"] = status == errors.PASS
checks["valid_zip_content_preserved_exactly"] = payload["content"] == VALID_ZIP
checks["valid_zip_payload_has_no_text_key"] = "text" not in payload

# --- 2. Raw bytes preserved exactly, including non-UTF-8 bytes that
# would corrupt or raise under a naive .decode("utf-8"). -------------------
non_utf8_zip = b"PK\x03\x04" + bytes([0xff, 0xfe, 0xfd, 0x00, 0x01])
transport.set_response(URL, HttpResponse(200, "", content=non_utf8_zip))
status, payload = client.request_bytes("GET", URL, require_zip=True)
checks["non_utf8_bytes_no_exception"] = status == errors.PASS
checks["non_utf8_bytes_preserved_exactly"] = payload["content"] == non_utf8_zip

# --- 3. Malformed ZIP signature maps to TRANSPORT_INVALID_RESPONSE --
# the SAME status request_json() already uses for malformed JSON, not
# a second parallel error vocabulary. -------------------------------------
transport.set_response(URL, HttpResponse(200, "", content=b"NOT-A-ZIP-FILE-AT-ALL"))
status, payload = client.request_bytes("GET", URL, require_zip=True)
checks["malformed_zip_maps_to_invalid_response"] = status == errors.TRANSPORT_INVALID_RESPONSE
checks["invalid_response_is_shared_vocabulary_not_a_new_status"] = (
    status == errors.TRANSPORT_INVALID_RESPONSE  # same constant request_json() uses
)

# --- 4. Empty payload also maps cleanly. ----------------------------------
transport.set_response(URL, HttpResponse(200, "", content=b""))
status, payload = client.request_bytes("GET", URL, require_zip=True)
checks["empty_payload_maps_to_invalid_response"] = status == errors.TRANSPORT_INVALID_RESPONSE

# --- 5. Other ZIP signature variants (central directory / data
# descriptor) are also recognized, not just the local-file-header one. ----
for sig_name, sig in [("central_directory", b"PK\x05\x06"), ("data_descriptor", b"PK\x07\x08")]:
    transport.set_response(URL, HttpResponse(200, "", content=sig + b"rest-of-file"))
    status, _ = client.request_bytes("GET", URL, require_zip=True)
    checks[f"zip_signature_variant_{sig_name}_recognized"] = status == errors.PASS

# --- 6. Existing status mapping (429/403/500/timeout/connection error)
# still applies identically on the bytes path -- one shared mapping,
# not reimplemented per-path. ------------------------------------------------
transport.set_response(URL, HttpResponse(429, "", content=VALID_ZIP))
status, _ = client.request_bytes("GET", URL, require_zip=True)
checks["429_maps_same_on_bytes_path"] = status == errors.TRANSPORT_RATE_LIMITED

transport.set_response(URL, HttpResponse(403, "", content=VALID_ZIP))
status, _ = client.request_bytes("GET", URL, require_zip=True)
checks["403_maps_same_on_bytes_path"] = status == errors.TRANSPORT_UNAUTHORIZED

transport.set_response(URL, HttpResponse(500, "", content=VALID_ZIP))
status, _ = client.request_bytes("GET", URL, require_zip=True)
checks["500_maps_same_on_bytes_path"] = status == errors.TRANSPORT_SERVER_ERROR

transport.set_error(URL, "TIMEOUT")
status, _ = client.request_bytes("GET", URL, require_zip=True)
checks["timeout_maps_same_on_bytes_path"] = status == errors.TRANSPORT_TIMEOUT

transport.set_error(URL, "CONNECTION_ERROR")
status, _ = client.request_bytes("GET", URL, require_zip=True)
checks["connection_error_maps_same_on_bytes_path"] = status == errors.TRANSPORT_CONNECTION_ERROR

# --- 7. require_zip=False allows arbitrary non-ZIP binary through
# unchanged (this client isn't ZIP-only, ZIP validation is opt-in). --------
transport.set_response(URL, HttpResponse(200, "", content=b"some-other-binary-format"))
status, payload = client.request_bytes("GET", URL, require_zip=False)
checks["non_zip_binary_allowed_when_not_required"] = (
    status == errors.PASS and payload["content"] == b"some-other-binary-format"
)

# --- 8. No raw exception ever escapes request_bytes(), same guarantee
# request()/request_json() already had. -------------------------------------
class MisbehavingTransport:
    def send(self, request):
        raise RuntimeError("a transport implementation bug")

raised = False
try:
    status, _ = NetworkClient(MisbehavingTransport()).request_bytes("GET", URL, require_zip=True)
except Exception:
    raised = True
checks["no_raw_exception_escapes_request_bytes"] = not raised
checks["misbehaving_transport_maps_to_unknown"] = status == errors.TRANSPORT_UNKNOWN_ERROR

# --- 9. Retry behavior is untouched: malformed ZIP is NOT retried (it's
# not in TRANSIENT_STATUSES, and nothing here added it), a transient
# network failure fetching the ZIP IS retried and recovers. -----------------
checks["invalid_response_not_in_transient_statuses"] = (
    errors.TRANSPORT_INVALID_RESPONSE not in TRANSIENT_STATUSES
)

audit = BaseAuditPublisher()
sleeper = FakeSleeper()
executor = RetryExecutor(audit=audit, sleep_fn=sleeper)
retry_policy = RetryPolicy(max_retries=3, retry_delay_seconds=4)

malformed_zip_log = {"n": 0}
def always_malformed():
    malformed_zip_log["n"] += 1
    transport.set_response(URL, HttpResponse(200, "", content=b"NOT-A-ZIP"))
    return client.request_bytes("GET", URL, require_zip=True)

status, _ = executor.run("DCAD_DATA_PRODUCTS", retry_policy, always_malformed)
checks["malformed_zip_not_retried_through_executor"] = (
    malformed_zip_log["n"] == 1 and status == errors.TRANSPORT_INVALID_RESPONSE
)
checks["malformed_zip_no_sleep_calls"] = len(sleeper.calls) == 0

flaky_zip_log = {"n": 0}
def flaky_then_valid_zip():
    flaky_zip_log["n"] += 1
    if flaky_zip_log["n"] == 1:
        transport.set_error(URL, "TIMEOUT")
    elif flaky_zip_log["n"] == 2:
        transport.set_response(URL, HttpResponse(500, "", content=b""))
    else:
        transport.set_response(URL, HttpResponse(200, "", content=VALID_ZIP))
    return client.request_bytes("GET", URL, require_zip=True)

sleeper2 = FakeSleeper()
executor2 = RetryExecutor(audit=BaseAuditPublisher(), sleep_fn=sleeper2)
status, payload = executor2.run("DCAD_DATA_PRODUCTS", retry_policy, flaky_then_valid_zip)
checks["transient_zip_fetch_failure_recovers_via_retry"] = (
    status == errors.PASS and payload["content"] == VALID_ZIP and flaky_zip_log["n"] == 3
)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"NETWORK-001B CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
