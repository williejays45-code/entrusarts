"""AX-ADAPT-001 genuine raw-boundary capture verification."""

from pathlib import Path

from era.acquisition_execution.executor import (
    FAILED, SUCCEEDED, AcquisitionStepRequest, ExecutionPolicy,
)
from era.acquisition_execution.raw_capture_invoker import (
    PROVIDER_NOT_COMPOSED, RAW_BOUNDARY_UNAVAILABLE, RAW_BYTES_MISSING,
    ProviderCaptureSeam, RawCaptureAcquisitionInvoker,
    UnsupportedRawCaptureSeam,
)
from era.providers import provider_errors


def request(provider_id="RAW_PROVIDER"):
    return AcquisitionStepRequest(
        "EXEC-1", "PLAN-1", "PLAN-1:1", "src:tx-test:raw:public:parcel",
        provider_id, "PARCEL", "LOOKUP-1", ExecutionPolicy(),
        "2026-07-12T23:30:00+00:00", 1,
    )


class GenuineBoundaryAdapter:
    def __init__(self, raw=b"ORIGINAL-BYTES", status=provider_errors.PASS):
        self._last_raw = None
        self.raw = raw
        self.status = status
        self.outputs = []

    def retrieve(self, lookup):
        # Test double models capture before parsing; parsed response remains separate.
        self._last_raw = self.raw
        parsed = {"evidence": ("UNCHANGED",), "source_reference": "SOURCE:1"}
        self.outputs.append(parsed)
        return self.status, parsed


class ParsedOnlyAdapter:
    def __init__(self): self._last_raw = None
    def retrieve(self, lookup):
        return provider_errors.PASS, {"evidence": ("PARSED",), "source_reference": "SOURCE:2"}


def run_checks():
    adapter = GenuineBoundaryAdapter()
    seam = ProviderCaptureSeam("RAW_PROVIDER", adapter, "_last_raw", "application/test")
    response = seam.acquire(request())
    response2 = seam.acquire(request())
    parsed_only = ProviderCaptureSeam(
        "RAW_PROVIDER", ParsedOnlyAdapter(), "_last_raw", "application/test"
    ).acquire(request())
    unsupported = UnsupportedRawCaptureSeam("COUNTY_DALLAS_CAD").acquire(request("COUNTY_DALLAS_CAD"))
    invoker = RawCaptureAcquisitionInvoker((seam, UnsupportedRawCaptureSeam("COUNTY_TARRANT_ASSESSOR")))
    missing = invoker.acquire(request("UNKNOWN"))

    checks = {
        "original_bytes_returned": response.outcome == SUCCEEDED and response.raw_bytes == b"ORIGINAL-BYTES",
        "media_type_projected": response.media_type == "application/test",
        "lookup_key_preserved": response.provider_local_record_key == "LOOKUP-1",
        "transport_metadata_preserved": response.provider_response_metadata == (("source_reference", "SOURCE:1"),),
        "repeat_observation_separate": response2.raw_bytes == response.raw_bytes and len(adapter.outputs) == 2,
        "parsed_output_unchanged": adapter.outputs == [
            {"evidence": ("UNCHANGED",), "source_reference": "SOURCE:1"},
            {"evidence": ("UNCHANGED",), "source_reference": "SOURCE:1"},
        ],
        "parsed_only_fails_closed": parsed_only.outcome == FAILED and parsed_only.failure_code == RAW_BYTES_MISSING,
        "stub_boundary_fails_closed": unsupported.outcome == FAILED and unsupported.failure_code == RAW_BOUNDARY_UNAVAILABLE,
        "unknown_runtime_fails_closed": missing.outcome == FAILED and missing.failure_code == PROVIDER_NOT_COMPOSED,
        "runtime_map_not_enumeration": set(invoker._seams) == {"RAW_PROVIDER", "COUNTY_TARRANT_ASSESSOR"},
    }

    era = Path(__file__).resolve().parents[1]
    dcad = (era / "live_adapters" / "dcad_bulk_data_adapter.py").read_text(encoding="utf-8")
    collin = (era / "live_adapters" / "collin_bulk_data_adapter.py").read_text(encoding="utf-8")
    invoker_source = (Path(__file__).parent / "raw_capture_invoker.py").read_text(encoding="utf-8").lower()
    checks["dcad_capture_precedes_zip_parse"] = dcad.index("self._last_raw_source_bytes = bytes(content)") < dcad.index("zipfile.ZipFile(io.BytesIO(content))")
    checks["dcad_capture_precedes_csv_parse"] = dcad.index("self._last_raw_source_bytes = bytes(content)") < dcad.index("csv.DictReader")
    checks["collin_binary_subprocess_capture"] = 'text=False' in collin and 'bytes(completed.stdout)' in collin
    checks["collin_capture_precedes_json_parse"] = collin.index("self._last_raw_query_bytes = raw_output") < collin.index('json.loads(output or "[]")')
    checks["no_parsed_serializing_fallback"] = all(term not in invoker_source for term in ("json.dumps", "pickle", ".encode("))
    checks["no_persistence"] = all(term not in invoker_source for term in ("sqlite", "database", "persist("))
    checks["no_evidence_reasoning"] = all(term not in invoker_source for term in ("canonicalevidence", "decisionengine", "confidence"))
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"AX-ADAPT-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)

