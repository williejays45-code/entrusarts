import sys
from datetime import datetime, timedelta, timezone
from era.acquisition.rate_limiter import RateLimiter
from era.acquisition.retry_executor import RetryExecutor
from era.acquisition import rate_retry_errors as errors
from era.shared.audit import BaseAuditPublisher
from era.acquisition.connector_models import ResourcePolicy, RetryPolicy

print("RATE-RETRY-001 VERIFICATION")
print("=" * 70)

checks = {}


class FakeClock:
    """Injectable clock -- deterministic control over 'now' for the
    rolling 24h rate-limit window, instead of relying on real time
    passing during the test."""
    def __init__(self, start=None):
        self.now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class FakeSleeper:
    """Injectable sleeper -- records every requested delay instead of
    actually waiting, so retry_delay_seconds is provably honored
    (the correct value was requested) without a slow test."""
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


# ---- rate limiting -------------------------------------------------

# --- 1. Provider within limit passes. --------------------------------
audit1 = BaseAuditPublisher()
clock1 = FakeClock()
limiter1 = RateLimiter(audit=audit1, now_fn=clock1)
policy_generous = ResourcePolicy(
    refresh_schedule_hours=24, rate_limit_per_day=500, cache_duration_hours=24,
    monthly_budget_limit=0.0, max_requests=500,
)
allowed, reason = limiter1.check_and_record("COUNTY_TEST", policy_generous)
checks["provider_within_limit_passes"] = allowed and reason == errors.ALLOWED
checks["within_limit_state_recorded"] = limiter1.get_state("COUNTY_TEST").total_requests == 1

# --- 2. Provider over max_requests blocks. ----------------------------
audit2 = BaseAuditPublisher()
clock2 = FakeClock()
limiter2 = RateLimiter(audit=audit2, now_fn=clock2)
policy_tiny_max = ResourcePolicy(
    refresh_schedule_hours=24, rate_limit_per_day=500, cache_duration_hours=24,
    monthly_budget_limit=0.0, max_requests=2,
)
r1 = limiter2.check_and_record("COUNTY_TEST", policy_tiny_max)
r2 = limiter2.check_and_record("COUNTY_TEST", policy_tiny_max)
r3 = limiter2.check_and_record("COUNTY_TEST", policy_tiny_max)
checks["first_two_requests_within_max_requests_allowed"] = r1[0] and r2[0]
checks["third_request_over_max_requests_blocked"] = (
    not r3[0] and r3[1] == errors.MAX_REQUESTS_EXCEEDED
)
checks["max_requests_block_recorded_in_audit"] = any(
    e["event_type"] == "RATE_LIMIT_BLOCKED" and e["payload"]["reason"] == errors.MAX_REQUESTS_EXCEEDED
    for e in audit2.events
)

# --- 3. Rate limit blocks excess calls (rolling 24h window, distinct
# from the lifetime max_requests ceiling). -----------------------------
audit3 = BaseAuditPublisher()
clock3 = FakeClock()
limiter3 = RateLimiter(audit=audit3, now_fn=clock3)
policy_tiny_rate = ResourcePolicy(
    refresh_schedule_hours=24, rate_limit_per_day=2, cache_duration_hours=24,
    monthly_budget_limit=0.0, max_requests=1000,  # generous lifetime cap, tight daily rate
)
r1 = limiter3.check_and_record("COUNTY_TEST", policy_tiny_rate)
r2 = limiter3.check_and_record("COUNTY_TEST", policy_tiny_rate)
r3 = limiter3.check_and_record("COUNTY_TEST", policy_tiny_rate)  # same instant, still within window
checks["rate_limit_first_two_in_window_allowed"] = r1[0] and r2[0]
checks["rate_limit_third_in_window_blocked"] = (
    not r3[0] and r3[1] == errors.RATE_LIMIT_PER_DAY_EXCEEDED
)
checks["rate_limit_block_recorded_in_audit"] = any(
    e["event_type"] == "RATE_LIMIT_BLOCKED" and e["payload"]["reason"] == errors.RATE_LIMIT_PER_DAY_EXCEEDED
    for e in audit3.events
)
# Advance the fake clock past the 24h window -- the same connector
# should be allowed again, proving this is a rolling window, not a
# permanent block once tripped.
clock3.advance(hours=25)
r4 = limiter3.check_and_record("COUNTY_TEST", policy_tiny_rate)
checks["rate_limit_window_rolls_forward_after_24h"] = r4[0]

# --- distinct connectors don't share state ----------------------------
audit4 = BaseAuditPublisher()
limiter4 = RateLimiter(audit=audit4, now_fn=FakeClock())
tiny = ResourcePolicy(refresh_schedule_hours=24, rate_limit_per_day=1, cache_duration_hours=24,
                       monthly_budget_limit=0.0, max_requests=1)
limiter4.check_and_record("COUNTY_A", tiny)
other_connector_result = limiter4.check_and_record("COUNTY_B", tiny)
checks["separate_connectors_have_independent_limits"] = other_connector_result[0]

# ---- retry ------------------------------------------------------------

# --- 4. Retry succeeds after transient failure. ------------------------
audit5 = BaseAuditPublisher()
sleeper5 = FakeSleeper()
executor5 = RetryExecutor(audit=audit5, sleep_fn=sleeper5)
retry_policy = RetryPolicy(max_retries=3, retry_delay_seconds=7)

call_log = {"attempts": 0}
def flaky_then_ok():
    call_log["attempts"] += 1
    if call_log["attempts"] < 3:
        return "PROVIDER_UNAVAILABLE", None
    return "PASS", {"data": "ok"}

status, result = executor5.run("COUNTY_TEST", retry_policy, flaky_then_ok)
checks["retry_succeeds_after_transient_failure"] = status == "PASS" and result == {"data": "ok"}
checks["retry_succeeded_after_correct_attempt_count"] = call_log["attempts"] == 3
checks["retry_succeeded_event_recorded"] = any(
    e["event_type"] == "RETRY_SUCCEEDED" and e["payload"]["attempts"] == 3 for e in audit5.events
)

# --- 5. Retry stops at max_retries. ------------------------------------
audit6 = BaseAuditPublisher()
sleeper6 = FakeSleeper()
executor6 = RetryExecutor(audit=audit6, sleep_fn=sleeper6)
retry_policy_2 = RetryPolicy(max_retries=2, retry_delay_seconds=5)

always_fails_log = {"attempts": 0}
def always_transient_failure():
    always_fails_log["attempts"] += 1
    return "PROVIDER_UNAVAILABLE", None

status, result = executor6.run("COUNTY_TEST", retry_policy_2, always_transient_failure)
checks["retry_stops_at_max_retries"] = status == "PROVIDER_UNAVAILABLE" and result is None
checks["retry_exhausted_correct_total_attempts"] = (
    always_fails_log["attempts"] == 1 + retry_policy_2.max_retries  # initial + 2 retries = 3
)
checks["retry_exhausted_event_recorded"] = any(
    e["event_type"] == "RETRY_EXHAUSTED" and e["payload"]["attempts"] == 3 for e in audit6.events
)

# --- 6. Retry delay is honored / testable through the injected sleeper. -
checks["retry_delay_honored_correct_number_of_sleeps"] = len(sleeper6.calls) == 2  # one sleep between each retry
checks["retry_delay_honored_correct_duration"] = all(s == 5 for s in sleeper6.calls)
checks["retry_delay_honored_first_scenario_too"] = sleeper5.calls == [7, 7]  # 2 sleeps for a 3rd-attempt success

# --- 7. Non-transient failures are NOT retried (retrying can't fix a
# disabled connector or a legal-basis mismatch). ------------------------
audit7 = BaseAuditPublisher()
sleeper7 = FakeSleeper()
executor7 = RetryExecutor(audit=audit7, sleep_fn=sleeper7)
permanent_log = {"attempts": 0}
def permanently_unauthorized():
    permanent_log["attempts"] += 1
    return "PROVIDER_UNAUTHORIZED", None

status, result = executor7.run("COUNTY_TEST", retry_policy, permanently_unauthorized)
checks["non_transient_failure_not_retried"] = permanent_log["attempts"] == 1 and status == "PROVIDER_UNAUTHORIZED"
checks["non_transient_failure_no_sleep_calls"] = len(sleeper7.calls) == 0

# --- 8. Fail gracefully without raw exceptions: a callable that raises
# is caught, treated as retryable, and never lets the exception escape. -
audit8 = BaseAuditPublisher()
sleeper8 = FakeSleeper()
executor8 = RetryExecutor(audit=audit8, sleep_fn=sleeper8)
raise_log = {"attempts": 0}
def raises_then_ok():
    raise_log["attempts"] += 1
    if raise_log["attempts"] < 2:
        raise RuntimeError("simulated network blip")
    return "PASS", {"ok": True}

raised = False
try:
    status, result = executor8.run("COUNTY_TEST", retry_policy, raises_then_ok)
except Exception:
    raised = True
checks["exception_from_wrapped_call_never_escapes"] = not raised
checks["exception_recovered_via_retry"] = status == "PASS" and result == {"ok": True}

# --- 9. Zero max_retries means exactly one attempt, no retry loop. -----
audit9 = BaseAuditPublisher()
sleeper9 = FakeSleeper()
executor9 = RetryExecutor(audit=audit9, sleep_fn=sleeper9)
zero_retry_policy = RetryPolicy(max_retries=0, retry_delay_seconds=99)
zero_log = {"attempts": 0}
def always_fails():
    zero_log["attempts"] += 1
    return "PROVIDER_UNAVAILABLE", None
status, _ = executor9.run("COUNTY_TEST", zero_retry_policy, always_fails)
checks["zero_max_retries_means_exactly_one_attempt"] = zero_log["attempts"] == 1
checks["zero_max_retries_no_sleep"] = len(sleeper9.calls) == 0

# ---- integration: real pipeline unaffected on the happy path ---------

from era.app import build_app, bootstrap_demo
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType

app = build_app()
bootstrap_demo(app)
identity = PropertyIdentity(
    property_id="ERA-PR-RATE-RETRY-001", address="5926 Sandhurst Ln Unit 224", city="Dallas",
    state="TX", zip_code="75252", county="Dallas", parcel_apn="00000000000",
    latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)
result = app.run_property(
    property_id=identity.property_id, identity=identity,
    state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
)
checks["real_pipeline_still_succeeds_with_enforcement_wired_in"] = result.ok
checks["rate_limit_stage_present_and_allowed"] = (
    result.stage("RATE_LIMIT") is not None and result.stage("RATE_LIMIT").ok
)
checks["no_retry_noise_on_first_try_success"] = not any(
    e["event_type"] == "RETRY_ATTEMPTED" for e in app.c.retry_executor.audit.events
)
checks["rate_limiter_recorded_the_real_request"] = (
    app.c.rate_limiter.get_state("COUNTY_DALLAS_CAD").total_requests == 1
)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"RATE-RETRY-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
