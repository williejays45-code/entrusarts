from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    provider_name: str
    connector_version: str
    legal_basis: str
    source_name: str


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    status: str


@dataclass(frozen=True)
class AcquisitionRequest:
    property_id: str
    address: str = ""
    jurisdiction: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AcquisitionResult:
    status: str
    evidence: Sequence[Any] = field(default_factory=tuple)
    provenance: Mapping[str, str] = field(default_factory=dict)
    source_reference: str = ""


@runtime_checkable
class AcquisitionProvider(Protocol):
    """Runtime provider contract consumed by ``LiveProviderAdapter``.

    The pipeline's acquisition boundary predates the structured request/result
    value objects above and consumes this tuple/payload interface directly.
    Keeping the runtime protocol aligned with that real call site makes
    structural checks meaningful; richer metadata remains an optional
    capability rather than a falsely mandatory method.
    """

    def provider_id(self) -> str: ...

    def provider_name(self) -> str: ...

    def connector_version(self) -> str: ...

    def retrieve(self, property_id: str) -> tuple[str, Mapping[str, Any]]: ...

    def health_check(self) -> Any: ...
