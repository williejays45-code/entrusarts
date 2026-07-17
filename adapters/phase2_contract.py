from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict
@dataclass(frozen=True)
class AdapterIntent:
    request_id: str
    source_engine: str
    target_engine: str
    adapter_version: str
    target_interface_version: str
    request_type: str
    payload: Dict[str, Any]
@dataclass(frozen=True)
class AdapterOutcome:
    request_id: str
    accepted: bool
    translated_confidence: str
    outcome: str
    failure_state: str
    response_payload: Dict[str, Any]
    created_at: str
def now_utc() -> str:
    return datetime.utcnow().isoformat()
def offline_outcome(request_id: str) -> AdapterOutcome:
    return AdapterOutcome(
        request_id=request_id,
        accepted=False,
        translated_confidence="UNSUPPORTED",
        outcome="REJECT",
        failure_state="MORROW_UNAVAILABLE",
        response_payload={"reason": "MORROW unavailable. ERA continues local reasoning only."},
        created_at=now_utc(),
    )
def version_mismatch_outcome(request_id: str) -> AdapterOutcome:
    return AdapterOutcome(
        request_id=request_id,
        accepted=False,
        translated_confidence="UNSUPPORTED",
        outcome="REJECT",
        failure_state="VERSION_MISMATCH",
        response_payload={"reason": "Interface version mismatch. Adapter regression required."},
        created_at=now_utc(),
    )
def duplicate_outcome(request_id: str, prior_payload: Dict[str, Any]) -> AdapterOutcome:
    return AdapterOutcome(
        request_id=request_id,
        accepted=True,
        translated_confidence=prior_payload.get("translated_confidence", "UNSUPPORTED"),
        outcome="DUPLICATE_RETURNED_PRIOR_RESULT",
        failure_state="NONE",
        response_payload=prior_payload,
        created_at=now_utc(),
    )
