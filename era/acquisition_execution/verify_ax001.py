"""AX-001 execution fidelity, artifact integrity, and boundary verification."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

from era.acquisition_execution.executor import (
    COMPLETED, CONTINUE_IN_PLAN_ORDER, FAILED, NOT_EXECUTED, SKIPPED,
    STOP_ON_FAILURE, STOPPED, SUCCEEDED, AcquisitionExecutor,
    AcquisitionStepResponse, ExecutionPolicy, RetryPolicy,
)
from era.discovery.acquisition_planning import AcquisitionPlan, AcquisitionPlanStep, PLANNED


NOW = datetime(2026, 7, 12, 23, 0, tzinfo=timezone.utc)


def plan():
    return AcquisitionPlan(
        PLANNED,
        (
            AcquisitionPlanStep(1, "src:tx-dallas:a:cad:parcel", "A", "PARCEL", "A:LOOKUP", "POLICY_PRIORITY"),
            AcquisitionPlanStep(2, "src:tx-dallas:b:cad:tax", "B", "TAX", "B:LOOKUP", "POLICY_PRIORITY"),
            AcquisitionPlanStep(3, "src:tx-dallas:c:cad:parcel", "C", "PARCEL", "C:LOOKUP", "POLICY_PRIORITY"),
        ),
        (), "POLICY-1", "CATALOG-4", (), "2026-07-12T22:00:00+00:00",
    )


class Invoker:
    def __init__(self, responses):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.requests = []

    def acquire(self, request):
        self.requests.append(request)
        response = self.responses[request.provider_id].pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def success(payload):
    return AcquisitionStepResponse(
        SUCCEEDED, payload, "application/json", (("transport", "https"),),
        "LOCAL-1", "200",
    )


def failure(code="TIMEOUT"):
    return AcquisitionStepResponse(FAILED, transport_status="504", failure_code=code, failure_detail="closed")


def run_checks():
    delays = []
    invoker = Invoker({"A": (success(b'{"a":1}'),), "B": (failure(),), "C": (success(b"C"),)})
    executor = AcquisitionExecutor(invoker, clock=lambda: NOW, delay=delays.append)
    result = executor.execute(plan(), "PLAN-1", "EXEC-1")
    outcomes = tuple(item.outcome for item in result.steps)
    checks = {
        "default_continue_mode": outcomes == (SUCCEEDED, FAILED, SUCCEEDED) and result.status == COMPLETED,
        "plan_order_preserved": tuple(item.provider_id for item in result.steps) == ("A", "B", "C"),
        "one_invocation_seam": len(invoker.requests) == 3,
        "request_identity_complete": invoker.requests[0].plan_step_id == "PLAN-1:1" and invoker.requests[0].canonical_source_id == plan().steps[0].canonical_source_id,
        "lookup_reference_preserved": invoker.requests[0].provider_local_lookup_reference == "A:LOOKUP",
        "no_retry_by_default": all(len(item.attempts) == 1 for item in result.steps),
        "raw_bytes_preserved": result.steps[0].attempts[0].artifact.raw_bytes == b'{"a":1}',
        "sha256_correct": result.steps[0].attempts[0].artifact.sha256 == "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862",
        "artifact_envelope_complete": result.steps[0].attempts[0].artifact.canonical_source_id == plan().steps[0].canonical_source_id,
        "failed_has_no_artifact": result.steps[1].attempts[0].artifact is None,
        "attempts_independently_visible": all(item.attempts[0].attempt_number == 1 for item in result.steps),
        "execution_identity_distinct": result.execution_id == "EXEC-1" and result.plan_id == "PLAN-1",
        "observation_timestamp_injected": result.started_at == "2026-07-12T23:00:00+00:00",
    }

    stop_invoker = Invoker({"A": (success(b"A"),), "B": (failure(),), "C": (success(b"NEVER"),)})
    stopped = AcquisitionExecutor(stop_invoker, clock=lambda: NOW).execute(
        plan(), "PLAN-1", "EXEC-2", ExecutionPolicy(STOP_ON_FAILURE)
    )
    checks["stop_on_failure"] = tuple(item.outcome for item in stopped.steps) == (SUCCEEDED, FAILED, NOT_EXECUTED)
    checks["not_executed_not_invoked"] = tuple(item.provider_id for item in stop_invoker.requests) == ("A", "B")
    checks["stopped_status_explicit"] = stopped.status == STOPPED

    retry_invoker = Invoker({
        "A": (failure("TRANSIENT"), success(b"A2")),
        "B": (success(b"B"),), "C": (success(b"C"),),
    })
    retry_policy = ExecutionPolicy(
        CONTINUE_IN_PLAN_ORDER, RetryPolicy(2, ("TRANSIENT",), 3)
    )
    retried = AcquisitionExecutor(retry_invoker, clock=lambda: NOW, delay=delays.append).execute(
        plan(), "PLAN-1", "EXEC-3", retry_policy
    )
    checks["declared_retry_visible"] = tuple(item.outcome for item in retried.steps[0].attempts) == (FAILED, SUCCEEDED)
    checks["retry_identity_unchanged"] = len({(item.plan_step_id, item.provider_id, item.canonical_source_id, item.provider_local_lookup_reference) for item in retry_invoker.requests[:2]}) == 1
    checks["fixed_delay_applied"] = delays == [3]

    nonretry_invoker = Invoker({"A": (failure("PERMANENT"),), "B": (success(b"B"),), "C": (success(b"C"),)})
    nonretry = AcquisitionExecutor(nonretry_invoker, clock=lambda: NOW).execute(
        plan(), "PLAN-1", "EXEC-4", ExecutionPolicy(retry=RetryPolicy(3, ("TRANSIENT",), 0))
    )
    checks["nonretryable_not_retried"] = len(nonretry.steps[0].attempts) == 1

    skip_invoker = Invoker({"A": (AcquisitionStepResponse(SKIPPED, failure_code="NOT_APPLICABLE"),), "B": (success(b"B"),), "C": (success(b"C"),)})
    skipped = AcquisitionExecutor(skip_invoker, clock=lambda: NOW).execute(plan(), "PLAN-1", "EXEC-5")
    checks["skip_continues_by_default"] = tuple(item.outcome for item in skipped.steps) == (SKIPPED, SUCCEEDED, SUCCEEDED)

    empty_success = Invoker({"A": (AcquisitionStepResponse(SUCCEEDED, raw_bytes=None),), "B": (success(b"B"),), "C": (success(b"C"),)})
    empty = AcquisitionExecutor(empty_success, clock=lambda: NOW).execute(plan(), "PLAN-1", "EXEC-6")
    checks["success_without_bytes_fails_closed"] = empty.steps[0].outcome == FAILED and empty.steps[0].attempts[0].artifact is None

    try:
        result.status = STOPPED
        frozen = False
    except FrozenInstanceError:
        frozen = True
    checks["execution_result_immutable"] = frozen
    checks["executor_has_no_result_store"] = set(executor.__dict__) == {"invoker", "clock", "delay"}

    source = (Path(__file__).parent / "executor.py").read_text(encoding="utf-8").lower()
    checks["no_persistence"] = all(term not in source for term in ("sqlite", "database", "persist("))
    checks["no_evidence_reasoning"] = all(term not in source for term in ("canonicalevidence", "decisionengine", "confidence", "recommendation"))
    checks["no_provider_substitution"] = "resolve_provider" not in source and "provider_enumeration" not in source
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"AX-001 CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
