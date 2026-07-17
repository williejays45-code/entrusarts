"""
NETWORK-001: transport spine only.

This module provides a real HTTP client interface (HttpTransport) and a
real implementation of it (UrllibHttpTransport, stdlib-backed, no new
dependency). But nothing else in this codebase constructs or calls
UrllibHttpTransport yet -- no connector, no Container, no pipeline
stage references it. It exists so the transport layer is real, tested
code, not just an interface sitting behind a mock -- while genuinely
deferring "which live provider do we actually call, and when" to its
own separate decision, per FORGE's instruction not to connect to Dallas
CAD live yet.

No scraping: this layer does not know about county-specific page
structure or field extraction. It moves bytes and maps transport/HTTP
outcomes to a clean status. Turning a response into structured evidence
is a connector's job (a future one), not this layer's.
"""

import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from urllib.parse import urlencode

from era.network.network_models import HttpRequest, HttpResponse


class TransportError(Exception):
    """Raised by HttpTransport implementations for failures that never
    produced an HTTP response at all (timeout, connection refused, DNS
    failure, ...). Any response that DID come back with an HTTP status
    code -- even 4xx/5xx -- is returned as an HttpResponse, not raised;
    status-code interpretation happens one layer up, in
    network_client.NetworkClient, not here."""

    def __init__(self, kind: str, detail: str):
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


class HttpTransport(ABC):
    @abstractmethod
    def send(self, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError


class UrllibHttpTransport(HttpTransport):
    """Real implementation. Not instantiated anywhere in this codebase
    yet -- see module docstring."""

    def send(self, request: HttpRequest) -> HttpResponse:
        url = request.url
        if request.params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(request.params)}"
        req = urllib.request.Request(url, method=request.method, headers=dict(request.headers or {}))
        try:
            with urllib.request.urlopen(req, timeout=request.timeout_seconds) as resp:
                raw_bytes = resp.read()
                body = raw_bytes.decode("utf-8", errors="replace")
                return HttpResponse(
                    status_code=resp.status, text=body, headers=dict(resp.headers), content=raw_bytes
                )
        except urllib.error.HTTPError as exc:
            raw_bytes = exc.read() if exc.fp else b""
            body = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else ""
            return HttpResponse(
                status_code=exc.code, text=body, headers=dict(exc.headers or {}), content=raw_bytes
            )
        except socket.timeout as exc:
            raise TransportError("TIMEOUT", str(exc)) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise TransportError("TIMEOUT", str(exc.reason)) from exc
            raise TransportError("CONNECTION_ERROR", str(exc.reason)) from exc
        except Exception as exc:
            raise TransportError("UNKNOWN", str(exc)) from exc
