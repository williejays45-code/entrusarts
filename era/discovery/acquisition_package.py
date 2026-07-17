"""SDR-004: validate AX output and package it for the evidence boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from era.acquisition_execution.executor import FAILED as STEP_FAILED
from era.acquisition_execution.executor import NOT_EXECUTED, SKIPPED, SUCCEEDED


COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
NO_EXECUTABLE_ARTIFACTS = "NO_EXECUTABLE_ARTIFACTS"
PACKAGE_STATUSES = frozenset({COMPLETE, PARTIAL, FAILED, NO_EXECUTABLE_ARTIFACTS})

VALID = "VALID"
INVALID = "INVALID"
NOT_PACKAGEABLE = "NOT_PACKAGEABLE"

PLAN_ID_MISMATCH = "PLAN_ID_MISMATCH"
STEP_COUNT_MISMATCH = "STEP_COUNT_MISMATCH"
STEP_ID_MISMATCH = "STEP_ID_MISMATCH"
SEQUENCE_MISMATCH = "SEQUENCE_MISMATCH"
SOURCE_ID_MISMATCH = "SOURCE_ID_MISMATCH"
PROVIDER_ID_MISMATCH = "PROVIDER_ID_MISMATCH"
ARTIFACT_MISSING = "ARTIFACT_MISSING"
FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
ARTIFACT_SOURCE_MISMATCH = "ARTIFACT_SOURCE_MISMATCH"
ARTIFACT_PROVIDER_MISMATCH = "ARTIFACT_PROVIDER_MISMATCH"
PROVENANCE_INCOMPLETE = "PROVENANCE_INCOMPLETE"
EXECUTION_UNSUCCESSFUL = "EXECUTION_UNSUCCESSFUL"

VALIDATION_REASONS = frozenset({
    PLAN_ID_MISMATCH, STEP_COUNT_MISMATCH, STEP_ID_MISMATCH, SEQUENCE_MISMATCH,
    SOURCE_ID_MISMATCH, PROVIDER_ID_MISMATCH, ARTIFACT_MISSING,
    FINGERPRINT_MISMATCH, ARTIFACT_SOURCE_MISMATCH,
    ARTIFACT_PROVIDER_MISMATCH, PROVENANCE_INCOMPLETE,
    EXECUTION_UNSUCCESSFUL,
})


@dataclass(frozen=True)
class PackagedAcquisitionStep:
    plan_step_id: str
    sequence: int
    canonical_source_id: str
    provider_id: str
    execution_outcome: str
    validation_status: str
    validation_reasons: tuple[str, ...]
    attempts: tuple[object, ...]
    artifact: object | None


@dataclass(frozen=True)
class ValidatedAcquisitionPackage:
    package_status: str
    plan_id: str
    execution_id: str
    policy_id: str
    catalog_version: str
    steps: tuple[PackagedAcquisitionStep, ...]
    valid_artifact_count: int
    provenance_complete: bool
    coverage_statement: str
    package_id: str = ""
    package_identity_version: str = "1"

    def evidence_boundary_payloads(self):
        """Return raw envelopes only; does not create or normalize evidence."""
        return tuple(item.artifact for item in self.steps if item.validation_status == VALID)


class AcquisitionPackageValidator:
    """Fail-closed identity/integrity validation with no external side effects."""

    def package(self, plan, execution_result) -> ValidatedAcquisitionPackage:
        execution_by_sequence = {item.sequence: item for item in execution_result.steps}
        duplicate_sequences = len(execution_by_sequence) != len(execution_result.steps)
        packaged = []
        any_attempted = False

        for plan_step in plan.steps:
            execution = execution_by_sequence.get(plan_step.sequence)
            reasons = []
            if execution_result.plan_id == "":
                reasons.append(PLAN_ID_MISMATCH)
            if duplicate_sequences or len(execution_result.steps) != len(plan.steps):
                reasons.append(STEP_COUNT_MISMATCH)
            if execution is None:
                packaged.append(PackagedAcquisitionStep(
                    f"{execution_result.plan_id}:{plan_step.sequence}", plan_step.sequence,
                    plan_step.canonical_source_id, plan_step.provider_id, NOT_EXECUTED,
                    INVALID, tuple(sorted(set(reasons + [STEP_ID_MISMATCH]))), (), None,
                ))
                continue

            any_attempted = any_attempted or bool(execution.attempts)
            expected_step_id = f"{execution_result.plan_id}:{plan_step.sequence}"
            if execution.plan_step_id != expected_step_id:
                reasons.append(STEP_ID_MISMATCH)
            if execution.sequence != plan_step.sequence:
                reasons.append(SEQUENCE_MISMATCH)
            if execution.canonical_source_id != plan_step.canonical_source_id:
                reasons.append(SOURCE_ID_MISMATCH)
            if execution.provider_id != plan_step.provider_id:
                reasons.append(PROVIDER_ID_MISMATCH)

            artifact = execution.attempts[-1].artifact if execution.attempts else None
            if execution.outcome != SUCCEEDED:
                reasons.append(EXECUTION_UNSUCCESSFUL)
            elif artifact is None:
                reasons.append(ARTIFACT_MISSING)
            else:
                if hashlib.sha256(artifact.raw_bytes).hexdigest() != artifact.sha256:
                    reasons.append(FINGERPRINT_MISMATCH)
                if artifact.canonical_source_id != plan_step.canonical_source_id:
                    reasons.append(ARTIFACT_SOURCE_MISMATCH)
                if artifact.provider_id != plan_step.provider_id:
                    reasons.append(ARTIFACT_PROVIDER_MISMATCH)
                if not all((artifact.media_type, artifact.retrieved_at, artifact.provider_local_record_key)):
                    reasons.append(PROVENANCE_INCOMPLETE)

            valid = not reasons and artifact is not None
            status = VALID if valid else (
                NOT_PACKAGEABLE if execution.outcome in (STEP_FAILED, SKIPPED, NOT_EXECUTED) else INVALID
            )
            packaged.append(PackagedAcquisitionStep(
                execution.plan_step_id, execution.sequence, execution.canonical_source_id,
                execution.provider_id, execution.outcome, status,
                tuple(sorted(set(reasons))), execution.attempts,
                artifact if valid else None,
            ))

        valid_count = sum(item.validation_status == VALID for item in packaged)
        if valid_count == len(plan.steps) and len(plan.steps) > 0:
            package_status = COMPLETE
        elif valid_count > 0:
            package_status = PARTIAL
        elif any_attempted:
            package_status = FAILED
        else:
            package_status = NO_EXECUTABLE_ARTIFACTS
        provenance_complete = all(
            item.validation_status == VALID for item in packaged
        ) and bool(packaged)
        coverage = (
            f"{valid_count}/{len(plan.steps)} planned steps produced validated raw artifacts; "
            "all unsuccessful and unavailable outcomes are preserved."
        )
        package_id = self._package_id(
            execution_result.plan_id, execution_result.execution_id,
            tuple(packaged), "1",
        )
        return ValidatedAcquisitionPackage(
            package_status, execution_result.plan_id, execution_result.execution_id,
            plan.policy_id, plan.catalog_version, tuple(packaged), valid_count,
            provenance_complete, coverage, package_id, "1",
        )

    @staticmethod
    def _package_id(plan_id, execution_id, steps, version):
        identity = {
            "package_identity_version": version,
            "plan_id": plan_id,
            "execution_id": execution_id,
            "steps": [
                {
                    "sequence": item.sequence,
                    "plan_step_id": item.plan_step_id,
                    "canonical_source_id": item.canonical_source_id,
                    "provider_id": item.provider_id,
                    "execution_outcome": item.execution_outcome,
                    "artifact_sha256": item.artifact.sha256 if item.artifact else "",
                }
                for item in steps
            ],
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
