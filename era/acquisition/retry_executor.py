"""
RATE-RETRY-001: enforcement for the two retry-behavior fields
ConnectorRecord.retry_policy already declared (max_retries,
retry_delay_seconds) but nothing ever actually used to control a retry
loop. This module is that loop.

Design:
- Wraps any zero-argument callable `fn` that returns a (status, result)
  tuple -- exactly the shape every engine in this codebase already
  returns. No new calling convention for callers to learn.
- Retries only on a small, explicit set of statuses considered
  transient (see TRANSIENT_STATUSES below) or on the wrapped callable
  raising an exception. Permission/configuration failures
  (PROVIDER_UNAUTHORIZED, LEGAL_SOURCE_REQUIRED, CONNECTOR_NOT_ACTIVE,
  PROVIDER_REQUIRED, ...) are NOT retried -- retrying a connector that's
  disabled or a legal-basis mismatch wastes a retry budget on something
  a retry can never fix. NETWORK-001 will need to add real transport
  errors (timeout, connection reset) to TRANSIENT_STATUSES once they
  exist; nothing in this module assumes what those will be.
- "Fail gracefully without raw exceptions": an exception raised by the
  wrapped callable is caught here and converted into a clean
  (RETRY_EXECUTOR_EXCEPTION, None) result, itself retryable like any
  other transient status, so a caller of RetryExecutor.run() never sees
  a raw traceback from whatever it wrapped.
- retry_delay_seconds is honored via an injectable sleep_fn (defaults
  to time.sleep) so tests can assert on delay without actually waiting.
"""

import time

from era.acquisition import rate_retry_errors as errors
from era.network import network_errors as network_errors

TRANSIENT_STATUSES = {
    "PROVIDER_UNAVAILABLE",
    "RAW_EVIDENCE_EMPTY",
    "EMPTY_EVIDENCE",
    errors.RETRY_EXECUTOR_EXCEPTION,
    # NETWORK-001: timeouts, connection failures, HTTP 429 (server-side
    # rate limiting), and HTTP 5xx are all worth retrying -- the
    # request never got a usable response, or the server itself said
    # "try again." HTTP 403/404/4xx and invalid-response are
    # deliberately NOT here: retrying an authorization failure or a
    # malformed response wastes the retry budget on something a retry
    # can't fix. See era.network.network_client's module docstring.
    network_errors.TRANSPORT_TIMEOUT,
    network_errors.TRANSPORT_CONNECTION_ERROR,
    network_errors.TRANSPORT_RATE_LIMITED,
    network_errors.TRANSPORT_SERVER_ERROR,
}


class RetryExecutor:
    def __init__(self, audit, sleep_fn=None):
        self.audit = audit
        self._sleep_fn = sleep_fn or time.sleep

    def run(self, connector_id: str, retry_policy, fn):
        max_attempts = 1 + max(0, retry_policy.max_retries if retry_policy else 0)
        attempt = 0
        last_status = errors.RETRY_EXECUTOR_EXCEPTION
        last_result = None

        while attempt < max_attempts:
            attempt += 1
            try:
                status, result = fn()
            except Exception:
                status, result = errors.RETRY_EXECUTOR_EXCEPTION, None

            last_status, last_result = status, result

            if status == errors.PASS:
                if attempt > 1:
                    self.audit.publish("RETRY_SUCCEEDED", {
                        "connector_id": connector_id, "attempts": attempt,
                    })
                return status, result

            transient = status in TRANSIENT_STATUSES
            if not transient:
                # A non-transient failure is final on the first attempt
                # it occurs -- no point recording "retry attempted" for
                # something that was never going to be retried.
                return status, result

            if attempt >= max_attempts:
                self.audit.publish("RETRY_EXHAUSTED", {
                    "connector_id": connector_id, "attempts": attempt,
                    "final_status": status,
                })
                return status, result

            delay = retry_policy.retry_delay_seconds if retry_policy else 0
            self.audit.publish("RETRY_ATTEMPTED", {
                "connector_id": connector_id, "attempt": attempt,
                "status": status, "delay_seconds": delay,
            })
            self._sleep_fn(delay)

        return last_status, last_result
