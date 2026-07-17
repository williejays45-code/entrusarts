"""EIL-CONTRACT-001 package identity and trace-survival verification."""

from dataclasses import FrozenInstanceError, replace

from era.acquisition_execution.executor import (
    COMPLETED, SUCCEEDED, AcquisitionAttempt, AcquisitionExecutionResult,
    AcquisitionStepExecution, RawArtifact,
)
from era.discovery.acquisition_package import AcquisitionPackageValidator
from era.discovery.acquisition_planning import AcquisitionPlan, AcquisitionPlanStep, PLANNED
from era.evidence_intelligence.contracts import (
    REQUIRED_TRACE_FIELDS, TRACE_DISPOSITION, EvidenceCandidate, ParserTrace,
)
from era.provenance.provenance_manager import EvidenceProvenanceManager
from era.provenance.provenance_models import ProvenanceInput


def package(execution_id="EXEC-1", completed_at="2026-07-13T00:01:00+00:00"):
    import hashlib
    raw = b"RAW"
    source = "src:tx-dallas:dcad:bulk:parcel"
    artifact = RawArtifact(
        raw, "application/zip", hashlib.sha256(raw).hexdigest(), source,
        "DCAD", "LOOKUP", "2026-07-13T00:00:00+00:00", (),
    )
    attempt = AcquisitionAttempt(1, SUCCEEDED, "200", "", "", artifact.retrieved_at, artifact)
    step = AcquisitionStepExecution("PLAN-1:1", 1, source, "DCAD", "LOOKUP", SUCCEEDED, "", (attempt,))
    execution = AcquisitionExecutionResult(
        execution_id, "PLAN-1", COMPLETED, (step,),
        "2026-07-13T00:00:00+00:00", completed_at,
    )
    plan = AcquisitionPlan(
        PLANNED, (AcquisitionPlanStep(1, source, "DCAD", "PARCEL", "LOOKUP", "POLICY_PRIORITY"),),
        (), "POLICY-1", "CATALOG-5", (), "2026-07-12T23:59:00+00:00",
    )
    return AcquisitionPackageValidator().package(plan, execution)


def provenance_input(trace):
    return ProvenanceInput(
        evidence_id="EV-TRACE-1", property_id="PROP-1", canonical_field="parcel_id",
        canonical_value="001", original_value="001", provider_id="DCAD",
        provider_name="Dallas CAD", legal_basis="PUBLIC_RECORD",
        source_reference="SOURCE", retrieved_at="2026-07-13T00:00:00+00:00",
        connector_version="1", adapter_version="1", normalization_version="ECM-1",
        artifact_sha256=trace.artifact_sha256, package_id=trace.package_id,
        execution_id=trace.execution_id, canonical_source_id=trace.canonical_source_id,
        parser_id=trace.parser_id, parser_version=trace.parser_version,
        schema_profile_id=trace.schema_profile_id,
        schema_profile_version=trace.schema_profile_version,
        source_location=trace.source_location,
        trace_contract_version=trace.trace_contract_version,
    )


def run_checks():
    p1 = package()
    p2 = package(completed_at="2099-01-01T00:00:00+00:00")
    p3 = package(execution_id="EXEC-2")
    trace = ParserTrace(
        p1.steps[0].artifact.sha256, p1.package_id, p1.execution_id,
        p1.steps[0].canonical_source_id, "CSV", "1", "DCAD-CSV", "1",
        "zip:ACCOUNT.CSV/row:1/column:ACCOUNT_NUM",
    )
    candidate = EvidenceCandidate("CAND-1", "parcel_id", "001", "001", "IDENTIFIER", trace)
    manager = EvidenceProvenanceManager()
    status, record = manager.register_evidence(provenance_input(trace))

    checks = {
        "package_id_deterministic": p1.package_id == p2.package_id,
        "package_id_excludes_timestamps": p1.package_id == p2.package_id,
        "execution_changes_package_id": p1.package_id != p3.package_id,
        "package_identity_version": p1.package_identity_version == "1",
        "package_id_sha256_shape": len(p1.package_id) == 64 and all(c in "0123456789abcdef" for c in p1.package_id),
        "trace_complete": trace.is_complete() and candidate.is_trace_complete(),
        "trace_fields_closed": tuple(field for field, _ in TRACE_DISPOSITION) == REQUIRED_TRACE_FIELDS,
        "every_trace_field_has_disposition": all(destinations == ("ECM", "EPM", "AUDIT") for _, destinations in TRACE_DISPOSITION),
        "epm_registration_passes": status == "PASS" and record is not None,
        "epm_retains_artifact_sha": record.artifact_sha256 == trace.artifact_sha256,
        "epm_retains_package_execution": record.package_id == trace.package_id and record.execution_id == trace.execution_id,
        "epm_retains_source": record.canonical_source_id == trace.canonical_source_id,
        "epm_retains_parser": record.parser_id == trace.parser_id and record.parser_version == trace.parser_version,
        "epm_retains_profile": record.schema_profile_id == trace.schema_profile_id and record.schema_profile_version == trace.schema_profile_version,
        "epm_retains_location": record.source_location == trace.source_location,
        "trace_changes_evidence_hash": record.evidence_hash != EvidenceProvenanceManager().compute_evidence_hash(replace(provenance_input(trace), artifact_sha256="", package_id="", execution_id="", canonical_source_id="", parser_id="", parser_version="", schema_profile_id="", schema_profile_version="", source_location="", trace_contract_version="")),
    }
    try:
        trace.parser_id = "changed"
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["trace_immutable"] = frozen
    checks["candidate_not_canonical_evidence"] = candidate.__class__.__name__ == "EvidenceCandidate"
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"EIL-CONTRACT-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)

