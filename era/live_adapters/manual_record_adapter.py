"""
LIVE-ADAPTER-001A: Manual Live Record Adapter.

Accepts official public-record fields that an authorized operator has
manually captured (read themselves from an official public source and
transcribed) and packages them into the same provider-payload shape
every LPA-compatible provider produces -- implementing the same
provider_id/provider_name/connector_version/health_check/retrieve
interface as CountyConnectorProviderAdapter (Dallas) and
TarrantConnectorProviderAdapter (Tarrant), so it plugs into
LiveProviderAdapter identically.

LIVE DATA LAW compliance, by construction:
- No scraping, no live website automation: ManualCaptureTransport below
  never opens a socket. It exists purely so a manual record still
  travels through the real NetworkClient/HttpTransport code path
  instead of being special-cased around it -- the "response" is just
  the operator's own captured data, serialized and parsed back exactly
  as a real HTTP round-trip would be.
- Rate limiting and retry enforcement are NOT re-implemented here. Both
  already wrap every registered provider at the pipeline level (see
  pipeline.py stage 3 -- RateLimiter.check_and_record() before LPA,
  RetryExecutor.run() wrapping the LPA call). Re-implementing either
  here would double-apply both against the same request. This adapter
  only has to be a well-behaved provider; the pipeline supplies the
  enforcement, the same way it does for Dallas and Tarrant.
- No direct UPR write: this adapter's retrieve() returns a payload for
  LiveProviderAdapter to package; it never touches
  UnifiedPropertyRecordEngine, EvidenceProvenanceManager, or any other
  downstream engine directly.
- No confidence assignment: assign_confidence() is permanently blocked.
  DecisionEngine and PolicyEngine remain the sole authority, exactly as
  C2 already established for recommendation and every provider since.
"""

import json

from era.live_adapters import manual_record_errors as errors
from era.live_adapters.manual_record_models import ManualRecordCapture
from era.network.http_transport import HttpTransport
from era.network.network_models import HttpResponse
from era.network.network_client import NetworkClient
from era.network import network_errors as network_errors
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors as provider_errors
from era.shared.audit import BaseAuditPublisher
from era.auth.auth_enums import AuthPermission


class ManualCaptureTransport(HttpTransport):
    """The 'manual/mock transport' the LIVE DATA LAW requires: a real
    HttpTransport implementation, genuinely invoked by NetworkClient,
    that never makes an outbound call. Its only job is to hand back the
    operator's own captured record as an HTTP-response-shaped payload,
    so the record still crosses the transport abstraction boundary
    instead of skipping it."""

    def __init__(self, capture: ManualRecordCapture):
        self._capture = capture

    def send(self, request):
        body = json.dumps({
            "property_id": self._capture.property_id,
            "source_reference": self._capture.source_reference,
            "legal_basis": self._capture.legal_basis,
            "captured_by": self._capture.captured_by,
            "captured_at": self._capture.captured_at,
            "fields": [
                {"field_name": f.field_name, "raw_value": f.raw_value}
                for f in self._capture.fields
            ],
        })
        return HttpResponse(status_code=200, text=body, headers={})


def validate_capture(capture: ManualRecordCapture) -> str:
    if capture is None:
        return errors.RECORD_REQUIRED
    if not capture.property_id:
        return errors.PROPERTY_ID_REQUIRED
    if not capture.source_reference:
        return errors.SOURCE_REFERENCE_REQUIRED
    if not capture.legal_basis:
        return errors.LEGAL_BASIS_REQUIRED
    if not capture.fields:
        return errors.RECORD_REQUIRED
    for item in capture.fields:
        if not getattr(item, "field_name", None) or not isinstance(item.field_name, str):
            return errors.MALFORMED_FIELD
        raw_value = getattr(item, "raw_value", None)
        if not isinstance(raw_value, str) or not raw_value.strip():
            return errors.MALFORMED_FIELD
    return errors.PASS


class ManualRecordAdapter:
    CONNECTOR_ID = "MANUAL_RECORD_CAPTURE"
    PROVIDER_NAME = "Manual Public-Record Capture"

    def __init__(self, version: str = "1.0", audit=None, auth=None):
        self._version = version
        self._pending = {}
        self.audit = audit or BaseAuditPublisher()
        # auth is intentionally NOT defaulted to a real AuthEngine --
        # same fail-closed discipline as EraApiEngine (AUTH-WIRE-001).
        # Without one wired in, stage_capture() refuses every call
        # rather than silently accepting unauthenticated captures.
        self.auth = auth

    def stage_capture(self, capture: ManualRecordCapture, token: str):
        """Validates and stages a manually captured record for the next
        retrieve() call against its property_id. This is the only way
        data enters this adapter -- there is no automated fetch path.

        OP-AUTH-001 authorization rule: requires a valid, non-expired
        token carrying READ or CAPTURE permission. USER-role tokens
        (which hold READ by default) may submit; ADMIN and FOUNDER
        tokens carry READ too, so both may submit as well. "CAPTURE" is
        checked as a plain permission string rather than a formal
        AuthPermission enum member, since no such member exists yet --
        this keeps a future, more granular capture-specific permission
        usable without requiring an AuthPermission enum change now.

        capture.captured_by is NOT trusted as the authoritative operator
        identity -- a caller could put anything in that field. The
        record actually staged always carries the identity AuthEngine
        itself resolved from the token, overriding whatever the caller
        claimed. Same trust-boundary discipline C2 established for
        recommendation's confidence input, applied here to operator
        identity: never trust a bare caller-supplied value when an
        authoritative source exists.
        """
        if self.auth is None:
            self.audit.publish("MANUAL_CAPTURE_BLOCKED", {"reason": errors.AUTH_ENGINE_REQUIRED})
            return errors.AUTH_ENGINE_REQUIRED, False

        auth_status, auth_result = self.auth.authenticate(token)
        if auth_status != "PASS":
            self.audit.publish("MANUAL_CAPTURE_BLOCKED", {"reason": auth_status})
            return auth_status, False

        authz_status = self.auth.authorize(auth_result, AuthPermission.READ)
        has_capture_permission = "CAPTURE" in auth_result.permissions
        if authz_status != "PASS" and not has_capture_permission:
            self.audit.publish("MANUAL_CAPTURE_BLOCKED", {
                "reason": authz_status, "user_id": auth_result.user_id, "role": auth_result.role,
            })
            return authz_status, False

        status = validate_capture(capture)
        if status != errors.PASS:
            self.audit.publish("MANUAL_CAPTURE_BLOCKED", {
                "reason": status, "user_id": auth_result.user_id, "role": auth_result.role,
            })
            return status, False

        from dataclasses import replace as _replace
        authoritative_capture = _replace(capture, captured_by=auth_result.user_id)
        self._pending[authoritative_capture.property_id] = authoritative_capture
        self.audit.publish("MANUAL_CAPTURE_STAGED", {
            "property_id": authoritative_capture.property_id,
            "source_reference": authoritative_capture.source_reference,
            "legal_basis": authoritative_capture.legal_basis,
            "field_count": len(authoritative_capture.fields),
            "captured_by": authoritative_capture.captured_by,
            "role": auth_result.role,
        })
        return errors.PASS, True

    # ---- standard provider interface (matches Dallas/Tarrant adapters) ----

    def provider_id(self):
        return self.CONNECTOR_ID

    def provider_name(self):
        return self.PROVIDER_NAME

    def connector_version(self):
        return self._version

    def health_check(self):
        return True  # no live endpoint to be unavailable

    def retrieve(self, property_id: str):
        capture = self._pending.get(property_id)
        status = validate_capture(capture)
        if status != errors.PASS:
            self.audit.publish("MANUAL_CAPTURE_BLOCKED", {"reason": status, "property_id": property_id})
            return status, {}

        # Round-trip through NetworkClient / ManualCaptureTransport --
        # the LIVE DATA LAW's transport-layer requirement, honored even
        # though there is no live socket behind it.
        client = NetworkClient(ManualCaptureTransport(capture))
        net_status, payload = client.request_json("GET", f"manual-capture://{property_id}")
        if net_status != network_errors.PASS:
            self.audit.publish("MANUAL_CAPTURE_BLOCKED", {"reason": net_status, "property_id": property_id})
            return net_status, {}

        record = payload["json"]
        evidence = [
            ProviderEvidence(field_name=item["field_name"], raw_value=item["raw_value"])
            for item in record["fields"]
        ]
        self.audit.publish("MANUAL_CAPTURE_RETRIEVED", {
            "property_id": property_id, "evidence_count": len(evidence),
        })
        return provider_errors.PASS, {
            "evidence": evidence,
            "provenance": {"legal_basis": record["legal_basis"]},
            "source_reference": record["source_reference"],
        }

    def attempt_write(self):
        self.audit.publish("MANUAL_CAPTURE_BLOCKED", {"reason": errors.READ_ONLY_ADAPTER})
        return False, errors.READ_ONLY_ADAPTER

    def assign_confidence(self):
        self.audit.publish("MANUAL_CAPTURE_BLOCKED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
