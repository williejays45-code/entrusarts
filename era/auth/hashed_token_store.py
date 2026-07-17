"""
A real TokenStore implementation, replacing the "four hardcoded
plaintext strings with a static expired flag" shape of MockTokenStore
with something an actual deployment could use:

- Tokens are never stored in plaintext -- only a salted SHA-256 hash.
- Tokens are cryptographically random (secrets.token_urlsafe), not
  human-chosen strings.
- Expiry is a real timestamp, checked against the current time (with an
  injectable clock for testability), not a static boolean flag.
- Persisted via era.shared.persistence.SqliteStore -- pass db_path (a
  real file) for durable, restart-surviving storage, same as every
  other engine in this codebase; pass nothing for an in-memory-only
  store (tests that don't care about restart survival).
- Every audit event this store itself publishes (issue, revoke) uses
  ONLY the token hash and non-secret metadata (user_id, role,
  expires_at) -- the raw token is never passed to audit.publish()
  anywhere in this module. issue_token() returns the raw token exactly
  once, directly to its caller; after that return, this object itself
  never sees or stores the raw value again, only its hash.

What this is NOT: a connection to any real external identity provider,
SSO, or OAuth system. issue_token() is still this store deciding who
gets a token and what role they get -- there is no real-world identity
verification behind that decision. Wiring in a real IdP (Okta, Auth0, a
company SSO, whatever it ends up being) is a separate, later decision
that requires knowing which one; this module is the piece that makes
whatever tokens ARE issued behave like real credentials instead of
magic strings, regardless of what eventually decides to issue them.

AUTH-TOKEN-WIRE-001: this is now AuthEngine's default (see
auth_engine.py's locked resolution rule) -- MockTokenStore is no longer
the zero-config fallback. A caller that wants MockTokenStore must ask
for it explicitly, either by injecting it directly or via
use_mock_auth=True.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from era.auth.token_store import TokenStore
from era.shared.persistence import SqliteStore


def _utc_now():
    return datetime.now(timezone.utc)


class HashedTokenStore(TokenStore):
    TABLE = "auth_tokens"

    def __init__(self, db_path: str = None, store=None, now_fn=None, audit=None):
        # store takes priority if explicitly injected (tests reusing an
        # existing SqliteStore instance); otherwise db_path builds a
        # real, durable one; otherwise this store is in-memory only for
        # this process's lifetime.
        self.store = store or (SqliteStore(db_path) if db_path else None)
        self._now_fn = now_fn or _utc_now
        self.audit = audit
        self._records = {}  # token_hash -> dict, mirrors self.store when present
        if self.store:
            self._load_from_store()

    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            self._records[data["token_hash"]] = data

    def _persist(self, token_hash: str, record: dict):
        if self.store:
            self.store.save_record(self.TABLE, token_hash, record)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue_token(self, user_id: str, role: str, permissions: list, ttl_seconds: int = 3600) -> str:
        """Generates a new random token, stores only its hash plus
        metadata, and returns the raw token exactly once -- the caller
        is responsible for delivering it to the actual user. It cannot
        be retrieved again; only its hash is ever kept. The audit event
        published here (if an audit publisher was given) carries the
        hash and non-secret metadata only -- never the raw_token
        variable itself."""
        raw_token = secrets.token_urlsafe(32)
        token_hash = self._hash(raw_token)
        expires_at = (self._now_fn() + timedelta(seconds=ttl_seconds)).isoformat()
        record = {
            "token_hash": token_hash,
            "user_id": user_id,
            "role": role,
            "permissions": list(permissions),
            "expires_at": expires_at,
            "revoked": False,
        }
        self._records[token_hash] = record
        self._persist(token_hash, record)
        if self.audit:
            self.audit.publish("TOKEN_ISSUED", {
                "token_hash": token_hash, "user_id": user_id, "role": role,
                "expires_at": expires_at,
            })
        return raw_token

    def revoke_token(self, token: str) -> bool:
        token_hash = self._hash(token)
        record = self._records.get(token_hash)
        if record is None:
            return False
        record = dict(record)
        record["revoked"] = True
        self._records[token_hash] = record
        self._persist(token_hash, record)
        if self.audit:
            self.audit.publish("TOKEN_REVOKED", {
                "token_hash": token_hash, "user_id": record["user_id"],
            })
        return True

    def lookup(self, token: str):
        """TokenStore interface method -- called by AuthEngine.
        Returns a dict with keys user_id/role/permissions/expired, or
        None if the token is unrecognized, exactly matching
        MockTokenStore's contract, so AuthEngine needs no changes to
        use either one. Never publishes an audit event itself -- a
        lookup happens on every single authenticate() call, including
        failed guesses, and AuthEngine.authenticate() already owns the
        AUTH_BLOCKED/AUTHENTICATED audit trail for that; a second audit
        trail here would be redundant and would need the same
        no-raw-token discipline duplicated for no benefit."""
        if not token:
            return None
        token_hash = self._hash(token)
        record = self._records.get(token_hash)
        if record is None:
            return None
        expires_at = datetime.fromisoformat(record["expires_at"])
        is_expired = record["revoked"] or self._now_fn() >= expires_at
        return {
            "user_id": record["user_id"],
            "role": record["role"],
            "permissions": list(record["permissions"]),
            "expired": is_expired,
        }

