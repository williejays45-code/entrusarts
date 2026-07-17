"""
NETWORK-001: response status mapping + JSON/text response wrapper.

Converts whatever HttpTransport hands back (a real HttpResponse, or a
TransportError) into the same (status, payload) shape every engine in
this codebase already returns -- so retry_executor.py and any future
connector can treat a network call exactly like any other engine call.
Never raises: every TransportError, and any other unexpected exception,
is caught here.

request() is the generic wrapper: any 2xx is PASS, payload carries the
raw status_code/text/headers. It does not assume the body is JSON --
plenty of legitimate responses aren't. request_json() layers strict
JSON handling on top for callers that specifically need it, and is
where "invalid response maps cleanly" actually applies: a 2xx with a
missing or malformed JSON body maps to TRANSPORT_INVALID_RESPONSE
rather than raising a json.JSONDecodeError.
"""

import json as _json

from era.network import network_errors as errors
from era.network.network_models import HttpRequest
from era.network.http_transport import HttpTransport, TransportError


class NetworkClient:
    # LIVE-ADAPTER-001B: ZIP local-file-header / end-of-central-directory
    # / data-descriptor signatures. Adopted from the reviewed
    # Binary*-stack draft as the one genuinely useful idea in it --
    # folded into this client rather than kept as a separate transport.
    ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

    def __init__(self, transport: HttpTransport):
        self.transport = transport

    def request_bytes(self, method: str, url: str, params: dict = None,
                       headers: dict = None, timeout_seconds: float = 10.0,
                       require_zip: bool = False):
        """The raw-bytes counterpart to request()/request_json(), for
        binary payloads (ZIP downloads in particular) where any text
        decoding -- even the lossy best-effort kind request() tolerates
        -- would corrupt the content. Never touches payload["text"];
        only payload["content"] (raw bytes) is populated.

        require_zip=True additionally validates the response starts
        with a real ZIP signature and is non-empty, mapping a malformed
        or non-ZIP body to the same TRANSPORT_INVALID_RESPONSE status
        request_json() already uses for malformed JSON -- one shared
        error vocabulary, not a second one.
        """
        http_request = HttpRequest(
            method=method, url=url, params=params or {},
            headers=headers or {}, timeout_seconds=timeout_seconds,
        )
        try:
            response = self.transport.send(http_request)
        except TransportError as exc:
            return self._map_transport_error(exc), None
        except Exception:
            return errors.TRANSPORT_UNKNOWN_ERROR, None

        status, payload = self._map_status(response, include_text=False)
        if status != errors.PASS:
            return status, payload

        if require_zip:
            content = payload["content"]
            if not content or not content.startswith(self.ZIP_SIGNATURES):
                return errors.TRANSPORT_INVALID_RESPONSE, payload

        return errors.PASS, payload

    def request(self, method: str, url: str, params: dict = None,
                headers: dict = None, timeout_seconds: float = 10.0):
        http_request = HttpRequest(
            method=method, url=url, params=params or {},
            headers=headers or {}, timeout_seconds=timeout_seconds,
        )
        try:
            response = self.transport.send(http_request)
        except TransportError as exc:
            return self._map_transport_error(exc), None
        except Exception as exc:
            return errors.TRANSPORT_UNKNOWN_ERROR, None

        return self._map_status(response)

    def request_json(self, method: str, url: str, params: dict = None,
                      headers: dict = None, timeout_seconds: float = 10.0):
        status, payload = self.request(
            method, url, params=params, headers=headers, timeout_seconds=timeout_seconds
        )
        if status != errors.PASS:
            return status, payload
        text = payload.get("text") if payload else None
        try:
            parsed = _json.loads(text) if text else None
        except (ValueError, TypeError):
            parsed = None
            invalid = True
        else:
            invalid = parsed is None
        if invalid:
            return errors.TRANSPORT_INVALID_RESPONSE, payload
        result = dict(payload)
        result["json"] = parsed
        return errors.PASS, result

    def _map_transport_error(self, exc: TransportError) -> str:
        if exc.kind == "TIMEOUT":
            return errors.TRANSPORT_TIMEOUT
        if exc.kind == "CONNECTION_ERROR":
            return errors.TRANSPORT_CONNECTION_ERROR
        return errors.TRANSPORT_UNKNOWN_ERROR

    def _map_status(self, response, include_text: bool = True):
        payload = {
            "status_code": response.status_code,
            "headers": dict(response.headers or {}),
            "content": response.content,
        }
        if include_text:
            payload["text"] = response.text
        code = response.status_code
        if 200 <= code < 300:
            return errors.PASS, payload
        if code == 429:
            return errors.TRANSPORT_RATE_LIMITED, payload
        if code == 403:
            return errors.TRANSPORT_UNAUTHORIZED, payload
        if code == 404:
            return errors.TRANSPORT_NOT_FOUND, payload
        if 500 <= code < 600:
            return errors.TRANSPORT_SERVER_ERROR, payload
        if 400 <= code < 500:
            return errors.TRANSPORT_CLIENT_ERROR, payload
        return errors.TRANSPORT_UNKNOWN_ERROR, payload
