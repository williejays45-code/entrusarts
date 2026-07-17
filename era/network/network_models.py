from dataclasses import dataclass, field


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    text: str
    headers: dict = field(default_factory=dict)
    # LIVE-ADAPTER-001B: raw bytes, for binary payloads (ZIP downloads,
    # in particular). `text` alone isn't safe for these -- decoding
    # arbitrary binary as UTF-8 with errors="replace" silently corrupts
    # it. Defaults to b"" so every existing HttpResponse(status_code,
    # text) construction from NETWORK-001 still works unchanged.
    content: bytes = b""
