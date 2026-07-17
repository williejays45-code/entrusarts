"""
Shared base for the per-engine audit publishers.

Previously 22 packages each defined their own byte-for-byte identical
class (self.events = []; publish() appends a dict). This collapses that
into one implementation so a fix or feature (e.g. persistence, a shared
sink) only has to happen once.

NOTE ON SCOPE: this still does not solve the "no cross-engine, no
persistent audit trail" finding from the review (C6). Each engine still
gets its own in-memory instance by default, so events still don't
survive process exit and still aren't visible across engines. What this
DOES fix is the duplication itself, and it adds an optional `sink`
so a caller CAN wire in shared/persistent storage without every engine
needing its own bespoke change.
"""

from datetime import datetime, timezone


class BaseAuditPublisher:
    """Base class for all engine-local audit publishers.

    Args:
        sink: optional callable(event: dict) -> None. If provided, every
            published event is also handed to the sink (e.g. to append to
            a shared list, write to a file, or insert into a DB), in
            addition to being kept in self.events for local inspection.
            If no sink is given, behavior is identical to the original
            22 duplicated classes: in-memory only, scoped to this instance.
    """

    def __init__(self, sink=None):
        self.events = []
        self._sink = sink

    def publish(self, event_type: str, payload: dict) -> bool:
        event = {
            "event_type": event_type,
            "payload": payload,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        self.events.append(event)
        if self._sink is not None:
            try:
                self._sink(event)
            except Exception:
                # Persistence error handling: a sink failure (durable
                # audit write) must never propagate into and block the
                # business operation that triggered it. The event is
                # still retained in self.events for this process's
                # lifetime; only the durable copy is at risk here.
                # era.shared.persistence.SqliteStore.event_sink() already
                # catches its own PersistenceError internally -- this is
                # a second, deliberately broader backstop for any other
                # sink implementation a caller might wire in.
                pass
        return True
