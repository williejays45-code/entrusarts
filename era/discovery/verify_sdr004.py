"""SDR-004 validated acquisition package and boundary verification."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from era.acquisition_execution.executor import (
    COMPLETED, FAILED as STEP_FAILED, NOT_EXECUTED, SUCCEEDED,
    AcquisitionAttempt, AcquisitionExecutionResult, AcquisitionStepExecution,
    RawArtifact,
)
from era.discovery.acquisition_package import (
    ARTIFACT_SOURCE_MISMATCH, COMPLETE, FAILED, FINGERPRINT_MISMATCH, NO_EXECUTABLE_ARTIFACTS,
    PARTIAL, PROVIDER_ID_MISMATCH, SOURCE_ID_MISMATCH, VALID,
    AcquisitionPackageValidator,
)
from era.discovery.acquisition_planning import AcquisitionPlan, AcquisitionPlanStep, PLANNED


def plan():
    return AcquisitionPlan(
        PLANNED,
        (
            AcquisitionPlanStep(1, "src:tx-dallas:a:cad:parcel", "A", "PARCEL", "A:1", "POLICY_PRIORITY"),
            AcquisitionPlanStep(2, "src:tx-dallas:b:cad:tax", "B", "TAX", "B:1", "POLICY_PRIORITY"),
        ), (), "POLICY-1", "CATALOG-4", (), "2026-07-12T22:00:00+00:00",
    )


def artifact(source, provider, raw=b"RAW"):
    import hashlib
    return RawArtifact(
        raw, "application/test", hashlib.sha256(raw).hexdigest(), source,
        provider, "LOCAL-1", "2026-07-12T23:00:00+00:00", (("transport", "test"),),
    )


def step(sequence, source, provider, outcome=SUCCEEDED, item=None, attempts=True):
    attempt = AcquisitionAttempt(
        1, outcome, "200" if outcome == SUCCEEDED else "500",
        "" if outcome == SUCCEEDED else "FAILED", "", "2026-07-12T23:00:00+00:00",
        item,
    )
    return AcquisitionStepExecution(
        f"PLAN-1:{sequence}", sequence, source, provider, f"{provider}:1",
        outcome, "", (attempt,) if attempts else (),
    )


def execution(steps):
    return AcquisitionExecutionResult(
        "EXEC-1", "PLAN-1", COMPLETED, tuple(steps),
        "2026-07-12T23:00:00+00:00", "2026-07-12T23:01:00+00:00",
    )


def run_checks():
    p = plan()
    a1 = artifact(p.steps[0].canonical_source_id, "A", b"A")
    a2 = artifact(p.steps[1].canonical_source_id, "B", b"B")
    validator = AcquisitionPackageValidator()
    complete = validator.package(p, execution((
        step(1, p.steps[0].canonical_source_id, "A", item=a1),
        step(2, p.steps[1].canonical_source_id, "B", item=a2),
    )))
    partial = validator.package(p, execution((
        step(1, p.steps[0].canonical_source_id, "A", item=a1),
        step(2, p.steps[1].canonical_source_id, "B", STEP_FAILED, None),
    )))
    failed = validator.package(p, execution((
        step(1, p.steps[0].canonical_source_id, "A", STEP_FAILED, None),
        step(2, p.steps[1].canonical_source_id, "B", STEP_FAILED, None),
    )))
    none = validator.package(p, execution((
        step(1, p.steps[0].canonical_source_id, "A", NOT_EXECUTED, None, False),
        step(2, p.steps[1].canonical_source_id, "B", NOT_EXECUTED, None, False),
    )))

    checks = {
        "complete_status": complete.package_status == COMPLETE and complete.valid_artifact_count == 2,
        "partial_status": partial.package_status == PARTIAL and partial.valid_artifact_count == 1,
        "partial_preserves_failure": partial.steps[1].execution_outcome == STEP_FAILED and bool(partial.steps[1].attempts),
        "failed_status": failed.package_status == FAILED and failed.valid_artifact_count == 0,
        "no_executable_status": none.package_status == NO_EXECUTABLE_ARTIFACTS,
        "raw_bytes_unchanged": complete.steps[0].artifact.raw_bytes == b"A",
        "attempt_history_preserved": complete.steps[0].attempts[0].artifact == a1,
        "identities_projected": complete.plan_id == "PLAN-1" and complete.execution_id == "EXEC-1",
        "policy_catalog_projected": complete.policy_id == "POLICY-1" and complete.catalog_version == "CATALOG-4",
        "provenance_complete_only_for_complete": complete.provenance_complete and not partial.provenance_complete,
        "coverage_limits_explicit": complete.coverage_statement.startswith("2/2") and partial.coverage_statement.startswith("1/2"),
        "evidence_boundary_payloads_raw_only": complete.evidence_boundary_payloads() == (a1, a2),
        "deterministic_package": complete == validator.package(p, execution((
            step(1, p.steps[0].canonical_source_id, "A", item=a1),
            step(2, p.steps[1].canonical_source_id, "B", item=a2),
        ))),
    }

    bad_hash = replace(a1, sha256="0" * 64)
    invalid_hash = validator.package(p, execution((
        step(1, p.steps[0].canonical_source_id, "A", item=bad_hash),
        step(2, p.steps[1].canonical_source_id, "B", item=a2),
    )))
    checks["fingerprint_revalidated"] = FINGERPRINT_MISMATCH in invalid_hash.steps[0].validation_reasons and invalid_hash.steps[0].artifact is None

    wrong_source_artifact = replace(a1, canonical_source_id="src:wrong")
    wrong_source = validator.package(p, execution((
        step(1, p.steps[0].canonical_source_id, "A", item=wrong_source_artifact),
        step(2, p.steps[1].canonical_source_id, "B", item=a2),
    )))
    checks["artifact_source_checked"] = ARTIFACT_SOURCE_MISMATCH in wrong_source.steps[0].validation_reasons and wrong_source.steps[0].artifact is None

    wrong_execution_provider = step(1, p.steps[0].canonical_source_id, "Z", item=replace(a1, provider_id="Z"))
    wrong_provider = validator.package(p, execution((wrong_execution_provider, step(2, p.steps[1].canonical_source_id, "B", item=a2))))
    checks["execution_provider_checked"] = PROVIDER_ID_MISMATCH in wrong_provider.steps[0].validation_reasons

    try:
        complete.package_status = PARTIAL
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["package_immutable"] = frozen
    checks["validator_stateless"] = validator.__dict__ == {}

    source_text = (Path(__file__).parent / "acquisition_package.py").read_text(encoding="utf-8").lower()
    checks["no_acquisition"] = all(term not in source_text for term in (".acquire(", ".retrieve("))
    checks["no_evidence_creation"] = all(term not in source_text for term in ("canonicalevidence", "normalize_record", "register_evidence"))
    checks["no_persistence_reasoning"] = all(term not in source_text for term in ("sqlite", "persist(", "decisionengine", "confidence"))
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"SDR-004 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
