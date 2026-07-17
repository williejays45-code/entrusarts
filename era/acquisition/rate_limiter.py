"""
RATE-RETRY-001: enforcement for the two request-volume fields
ConnectorRecord.resource_policy already declared (SourceReliabilityRegistry
validated they were present and positive at registration time -- see
register_connector() -- but nothing anywhere ever checked them again
before a request went out). This module is that check.

Two independent limits, matching the two distinct fields as declared:

- max_requests: a hard ceiling on total requests made through this
  connector.
- rate_limit_per_day: a rolling 24-hour window cap, independent of the
  lifetime ceiling above.

Persistence (added post-checkpoint-review): pass `store=` (an
era.shared.persistence.SqliteStore) and rate-limit state survives a
restart, same opt-in pattern as every other engine. Pass nothing and
behavior is exactly what it was before -- in-memory only, scoped to
this RateLimiter instance's lifetime.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from era.acquisition import rate_retry_errors as errors


@dataclass
class RateLimitState:
    total_requests: int = 0
    request_timestamps: list = field(default_factory=list)


class RateLimiter:
    TABLE = "rate_limit_state"

    def __init__(self, audit, now_fn=None, store=None):
        self._state = {}
        self.audit = audit
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.store = store
        if self.store:
            self._load_from_store()

    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            state = RateLimitState(
                total_requests=data["total_requests"],
                request_timestamps=[datetime.fromisoformat(t) for t in data["request_timestamps"]],
            )
            self._state[data["connector_id"]] = state

    def _persist(self, connector_id: str, state: RateLimitState):
        if self.store:
            self.store.save_record(self.TABLE, connector_id, {
                "connector_id": connector_id,
                "total_requests": state.total_requests,
                "request_timestamps": [t.isoformat() for t in state.request_timestamps],
            })

    def get_state(self, connector_id: str) -> RateLimitState:
        return self._state.get(connector_id, RateLimitState())

    def check_and_record(self, connector_id: str, resource_policy) -> tuple:
        """Returns (allowed: bool, reason: str). If allowed, the request
        is counted immediately -- callers must not call this speculatively
        and skip the actual request; this is check-and-record, not
        check-then-separately-record, precisely so two near-simultaneous
        callers can't both pass a check that only one of them should."""
        state = self._state.setdefault(connector_id, RateLimitState())
        now = self._now_fn()

        if resource_policy is None:
            self.audit.publish("RATE_LIMIT_BLOCKED", {
                "connector_id": connector_id,
                "reason": errors.RATE_LIMIT_PER_DAY_EXCEEDED,
                "detail": "no resource_policy on connector",
            })
            return False, errors.RATE_LIMIT_PER_DAY_EXCEEDED

        if state.total_requests >= resource_policy.max_requests:
            self.audit.publish("RATE_LIMIT_BLOCKED", {
                "connector_id": connector_id,
                "reason": errors.MAX_REQUESTS_EXCEEDED,
                "max_requests": resource_policy.max_requests,
                "total_requests": state.total_requests,
            })
            return False, errors.MAX_REQUESTS_EXCEEDED

        window_start = now - timedelta(hours=24)
        recent = [t for t in state.request_timestamps if t > window_start]
        if len(recent) >= resource_policy.rate_limit_per_day:
            state.request_timestamps = recent
            self._persist(connector_id, state)
            self.audit.publish("RATE_LIMIT_BLOCKED", {
                "connector_id": connector_id,
                "reason": errors.RATE_LIMIT_PER_DAY_EXCEEDED,
                "rate_limit_per_day": resource_policy.rate_limit_per_day,
                "requests_in_window": len(recent),
            })
            return False, errors.RATE_LIMIT_PER_DAY_EXCEEDED

        state.total_requests += 1
        recent.append(now)
        state.request_timestamps = recent
        self._persist(connector_id, state)
        self.audit.publish("RATE_LIMIT_REQUEST_RECORDED", {
            "connector_id": connector_id,
            "total_requests": state.total_requests,
            "requests_in_window": len(recent),
        })
        return True, errors.ALLOWED
