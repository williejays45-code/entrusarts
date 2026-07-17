"""AX-ADAPT-001 live raw-boundary adapters for AX's single acquire seam."""

from __future__ import annotations

from dataclasses import dataclass

from era.acquisition_execution.executor import (
    FAILED, SUCCEEDED, AcquisitionStepRequest, AcquisitionStepResponse,
)
from era.providers import provider_errors


RAW_BOUNDARY_UNAVAILABLE = "RAW_BOUNDARY_UNAVAILABLE"
RAW_BYTES_MISSING = "RAW_BYTES_MISSING"
PROVIDER_NOT_COMPOSED = "PROVIDER_NOT_COMPOSED"


@dataclass(frozen=True)
class ProviderCaptureSeam:
    provider_id: str
    adapter: object
    capture_attribute: str
    media_type: str

    def acquire(self, request: AcquisitionStepRequest) -> AcquisitionStepResponse:
        if request.provider_id != self.provider_id:
            return AcquisitionStepResponse(FAILED, failure_code=PROVIDER_NOT_COMPOSED)
        # Clear operation-local capture so a previous observation cannot leak.
        setattr(self.adapter, self.capture_attribute, None)
        status, response = self.adapter.retrieve(request.provider_local_lookup_reference)
        if status != provider_errors.PASS:
            return AcquisitionStepResponse(
                FAILED, transport_status=str(status), failure_code=str(status),
            )
        raw = getattr(self.adapter, self.capture_attribute, None)
        if not isinstance(raw, (bytes, bytearray)):
            return AcquisitionStepResponse(FAILED, failure_code=RAW_BYTES_MISSING)
        source_reference = response.get("source_reference", "") if isinstance(response, dict) else ""
        return AcquisitionStepResponse(
            SUCCEEDED,
            raw_bytes=bytes(raw),
            media_type=self.media_type,
            provider_response_metadata=(("source_reference", str(source_reference)),),
            provider_local_record_key=request.provider_local_lookup_reference,
            transport_status=str(status),
        )


class UnsupportedRawCaptureSeam:
    """Fail-closed seam for governed stubs with no real byte boundary."""

    def __init__(self, provider_id):
        self.provider_id = provider_id

    def acquire(self, request):
        return AcquisitionStepResponse(FAILED, failure_code=RAW_BOUNDARY_UNAVAILABLE)


class RawCaptureAcquisitionInvoker:
    """Runtime seam dispatch only; does not enumerate or grant eligibility."""

    def __init__(self, seams: tuple[object, ...]):
        self._seams = {item.provider_id: item for item in seams}

    def acquire(self, request):
        seam = self._seams.get(request.provider_id)
        if seam is None:
            return AcquisitionStepResponse(FAILED, failure_code=PROVIDER_NOT_COMPOSED)
        return seam.acquire(request)


def dcad_capture_seam(adapter):
    return ProviderCaptureSeam(
        "DCAD_BULK_DATA_2025", adapter, "_last_raw_source_bytes", "application/zip"
    )


def collin_capture_seam(adapter):
    return ProviderCaptureSeam(
        "COLLIN_BULK_MDB", adapter, "_last_raw_query_bytes", "application/json"
    )
