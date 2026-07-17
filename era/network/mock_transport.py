"""
NETWORK-001: injectable transport for tests. Never touches a real
socket. Configure a canned HttpResponse or a canned TransportError per
URL (or a default for anything unconfigured), and it hands them back or
raises exactly like a real transport would -- so NetworkClient can be
fully tested without live network access.
"""

from era.network.http_transport import HttpTransport, TransportError


class MockHttpTransport(HttpTransport):
    def __init__(self):
        self._responses = {}
        self._default = None
        self.sent_requests = []

    def set_response(self, url: str, response):
        self._responses[url] = response

    def set_error(self, url: str, kind: str, detail: str = "simulated"):
        self._responses[url] = TransportError(kind, detail)

    def set_default_response(self, response):
        self._default = response

    def send(self, request):
        self.sent_requests.append(request)
        outcome = self._responses.get(request.url, self._default)
        if outcome is None:
            raise TransportError(
                "UNKNOWN", f"MockHttpTransport has no configured response for {request.url}"
            )
        if isinstance(outcome, TransportError):
            raise outcome
        return outcome
