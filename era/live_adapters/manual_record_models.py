"""
LIVE-ADAPTER-001A: what a human operator manually captures from an
official public-record source (e.g. reading a county assessor's public
lookup page themselves and transcribing it) -- NOT what an automated
scraper extracts. This is raw input to ManualRecordAdapter, not
evidence yet; it becomes evidence only after flowing through the
standard ECM/EPM stages exactly like any other provider's output.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ManualFieldCapture:
    field_name: str
    raw_value: str


@dataclass(frozen=True)
class ManualRecordCapture:
    property_id: str
    source_reference: str
    legal_basis: str
    captured_by: str
    fields: tuple  # tuple[ManualFieldCapture, ...] -- frozen, like every other capture model in this codebase
    captured_at: str = field(default_factory=utc_now)
