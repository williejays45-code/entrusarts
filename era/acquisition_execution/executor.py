"""AX-001: execute immutable acquisition plans through one explicit seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import time
from typing import Callable, Protocol


SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
NOT_EXECUTED = "NOT_EXECUTED"
STEP_OUTCOMES = frozenset({SUCCEEDED, FAILED, SKIPPED, NOT_EXECUTED})

STOP_ON_FAILURE = "STOP_ON_FAILURE"
CONTINUE_IN_PLAN_ORDER = "CONTINUE_IN_PLAN_ORDER"
EXECUTION_MODES = frozenset({STOP_ON_FAILURE, CONTINUE_IN_PLAN_ORDER})

COMPLETED = "COMPLETED"
STOPPED = "STOPPED"

NO_ARTIFACT = "NO_ARTIFACT"
STOP_CONDITION = "STOP_CONDITION"
SKIP_CONDITION = "SKIP_CONDITION"
UNHANDLED_PROVIDER_EXCEPTION = "UNHANDLED_PROVIDER_EXCEPTION"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retryable_failure_codes: tuple[str, ...] = ()
    fixed_delay_seconds: float = 0

    def __post_init__(self):
        if self.max_attempts < 1 or self.fixed_delay_seconds < 0:
            raise ValueError("INVALID_RETRY_POLICY")


@dataclass(frozen=True)
class ExecutionPolicy:
    mode: str = CONTINUE_IN_PLAN_ORDER
    retry: RetryPolicy = RetryPolicy()
    skip_is_terminal: bool = False

    def __post_init__(self):
        if self.mode not in EXECUTION_MODES:
            raise ValueError("INVALID_EXECUTION_MODE")


@dataclass(frozen=True)
class AcquisitionStepRequest:
    execution_id: str
    plan_id: str
    plan_step_id: str
    canonical_source_id: str
    provider_id: str
    record_type: str
    provider_local_lookup_reference: str
    execution_policy: ExecutionPolicy
    observation_timestamp: str
    attempt_number: int


@dataclass(frozen=True)
class AcquisitionStepResponse:
    outcome: str
    raw_bytes: bytes | None = None
    media_type: str = "application/octet-stream"
    provider_response_metadata: tuple[tuple[str, str], ...] = ()
    provider_local_record_key: str = ""
    transport_status: str = ""
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self):
        if self.outcome not in (SUCCEEDED, FAILED, SKIPPED):
            raise ValueError("INVALID_PROVIDER_OUTCOME")


class AcquisitionInvoker(Protocol):
    def acquire(self, request: AcquisitionStepRequest) -> AcquisitionStepResponse: ...


@dataclass(frozen=True)
class RawArtifact:
    raw_bytes: bytes
    media_type: str
    sha256: str
    canonical_source_id: str
    provider_id: str
    provider_local_record_key: str
    retrieved_at: str
    transport_metadata: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AcquisitionAttempt:
    attempt_number: int
    outcome: str
    transport_status: str
    failure_code: str
    failure_detail: str
    observed_at: str
    artifact: RawArtifact | None


@dataclass(frozen=True)
class AcquisitionStepExecution:
    plan_step_id: str
    sequence: int
    canonical_source_id: str
    provider_id: str
    provider_local_lookup_reference: str
    outcome: str
    reason_code: str
    attempts: tuple[AcquisitionAttempt, ...]


@dataclass(frozen=True)
class AcquisitionExecutionResult:
    execution_id: str
    plan_id: str
    status: str
    steps: tuple[AcquisitionStepExecution, ...]
    started_at: str
    completed_at: str


class AcquisitionExecutor:
    """Execute plan steps without modifying, supplementing, or persisting them."""

    def __init__(
        self,
        invoker: AcquisitionInvoker,
        clock: Callable[[], datetime] | None = None,
        delay: Callable[[float], None] | None = None,
    ):
        self.invoker = invoker
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.delay = delay or time.sleep

    def execute(self, plan, plan_id: str, execution_id: str, policy: ExecutionPolicy = ExecutionPolicy()):
        started_at = self._now()
        results = []
        stopped = False
        for step in plan.steps:
            step_id = f"{plan_id}:{step.sequence}"
            if stopped:
                results.append(AcquisitionStepExecution(
                    step_id, step.sequence, step.canonical_source_id, step.provider_id,
                    step.provider_local_lookup_reference, NOT_EXECUTED,
                    STOP_CONDITION, (),
                ))
                continue

            attempts = []
            final_outcome = FAILED
            final_reason = NO_ARTIFACT
            for attempt_number in range(1, policy.retry.max_attempts + 1):
                observed_at = self._now()
                request = AcquisitionStepRequest(
                    execution_id, plan_id, step_id, step.canonical_source_id,
                    step.provider_id, step.record_type,
                    step.provider_local_lookup_reference, policy,
                    observed_at, attempt_number,
                )
                try:
                    response = self.invoker.acquire(request)
                except Exception as exc:
                    response = AcquisitionStepResponse(
                        FAILED, failure_code=UNHANDLED_PROVIDER_EXCEPTION,
                        failure_detail=type(exc).__name__,
                    )
                artifact = self._artifact(response, step, observed_at)
                outcome = response.outcome
                reason = response.failure_code
                if outcome == SUCCEEDED and artifact is None:
                    outcome = FAILED
                    reason = NO_ARTIFACT
                attempts.append(AcquisitionAttempt(
                    attempt_number, outcome, response.transport_status, reason,
                    response.failure_detail, observed_at, artifact,
                ))
                final_outcome = outcome
                final_reason = reason
                retryable = (
                    outcome == FAILED
                    and reason in policy.retry.retryable_failure_codes
                    and attempt_number < policy.retry.max_attempts
                )
                if not retryable:
                    break
                if policy.retry.fixed_delay_seconds:
                    self.delay(policy.retry.fixed_delay_seconds)

            results.append(AcquisitionStepExecution(
                step_id, step.sequence, step.canonical_source_id, step.provider_id,
                step.provider_local_lookup_reference, final_outcome,
                final_reason or (SKIP_CONDITION if final_outcome == SKIPPED else ""),
                tuple(attempts),
            ))
            stopped = (
                final_outcome == FAILED and policy.mode == STOP_ON_FAILURE
            ) or (final_outcome == SKIPPED and policy.skip_is_terminal)

        return AcquisitionExecutionResult(
            execution_id, plan_id, STOPPED if stopped else COMPLETED,
            tuple(results), started_at, self._now(),
        )

    def _now(self):
        return self.clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _artifact(response, step, observed_at):
        if response.outcome != SUCCEEDED or response.raw_bytes is None:
            return None
        raw = bytes(response.raw_bytes)
        return RawArtifact(
            raw, response.media_type, hashlib.sha256(raw).hexdigest(),
            step.canonical_source_id, step.provider_id,
            response.provider_local_record_key, observed_at,
            tuple(sorted(response.provider_response_metadata)),
        )

