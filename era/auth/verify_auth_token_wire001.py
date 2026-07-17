import sys
import os
import tempfile
import sqlite3
from datetime import datetime, timedelta, timezone
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import MockTokenStore
from era.auth.hashed_token_store import HashedTokenStore
from era.auth.auth_enums import AuthPermission
from era.shared.audit import BaseAuditPublisher

print("AUTH-TOKEN-WIRE-001 VERIFICATION")
print("=" * 70)

checks = {}


def fresh_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    return path


def cleanup(path):
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


class FakeClock:
    def __init__(self, start=None):
        self.now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


# --- 1. Default app / default AuthEngine uses HashedTokenStore, not
# MockTokenStore, with no explicit configuration at all. ---------------------
path1 = fresh_db_path()
try:
    engine1 = AuthEngine(auth_db_path=path1)
    checks["default_resolution_is_hashed_token_store"] = isinstance(engine1.token_store, HashedTokenStore)
    status, _ = engine1.authenticate("admin-token")
    checks["default_resolution_rejects_old_mock_tokens"] = status == "INVALID_TOKEN"
finally:
    cleanup(path1)

# --- 2. MockTokenStore requires explicit test configuration -- both
# valid paths (explicit injection, and use_mock_auth=True) work; the
# implicit no-argument path never resolves to it. ----------------------------
engine2a = AuthEngine(token_store=MockTokenStore())
status, result = engine2a.authenticate("admin-token")
checks["explicit_injection_reaches_mock_tokens"] = status == "PASS" and result.user_id == "ADMIN-001"

engine2b = AuthEngine(use_mock_auth=True)
checks["use_mock_auth_flag_resolves_to_mock_token_store"] = isinstance(engine2b.token_store, MockTokenStore)
status, result = engine2b.authenticate("founder-token")
checks["use_mock_auth_flag_reaches_mock_tokens"] = status == "PASS" and result.user_id == "FOUNDER-001"

path2c = fresh_db_path()
try:
    engine2c = AuthEngine(auth_db_path=path2c)  # neither override given
    checks["unconfigured_default_never_resolves_to_mock"] = not isinstance(engine2c.token_store, MockTokenStore)
finally:
    cleanup(path2c)

# --- Resolution priority: explicit token_store wins even if
# use_mock_auth=True is ALSO passed (first branch of the locked rule
# takes priority over the second). --------------------------------------------
custom_store = MockTokenStore()
engine_priority = AuthEngine(token_store=custom_store, use_mock_auth=True)
checks["explicit_token_store_wins_over_use_mock_auth_flag"] = engine_priority.token_store is custom_store

# --- 3. Raw token never appears in SQLite -- inspect the actual file
# bytes, not just the ORM-level API. -------------------------------------------
path3 = fresh_db_path()
try:
    store3 = HashedTokenStore(path3)
    raw_token = store3.issue_token("USER-RAW-CHECK", "USER", ["READ"], ttl_seconds=3600)
    del store3  # force any buffered writes to have already happened via _persist per-call

    conn = sqlite3.connect(path3)
    conn.execute("PRAGMA journal_mode=WAL")  # ensure WAL contents are checked too, not just the main file
    all_text = []
    for (table_name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for row in conn.execute(f"SELECT * FROM {table_name}").fetchall():
            all_text.append(str(row))
    conn.close()

    # Also check the raw file bytes directly (covers WAL/journal
    # remnants a plain SELECT might not surface).
    raw_bytes = b""
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path3 + suffix):
            with open(path3 + suffix, "rb") as f:
                raw_bytes += f.read()

    checks["raw_token_not_in_any_sqlite_row"] = not any(raw_token in t for t in all_text)
    checks["raw_token_not_in_raw_db_file_bytes"] = raw_token.encode("utf-8") not in raw_bytes
finally:
    cleanup(path3)

# --- 4. Raw token never appears in audit events -- issue, authenticate,
# revoke, and a deliberately failed authentication attempt, then scan
# every event from both HashedTokenStore's own audit and AuthEngine's. ------
path4 = fresh_db_path()
try:
    store_audit = BaseAuditPublisher()
    engine_audit = BaseAuditPublisher()
    store4 = HashedTokenStore(path4, audit=store_audit)
    engine4 = AuthEngine(token_store=store4, audit=engine_audit)

    raw_token4 = store4.issue_token("USER-AUDIT-CHECK", "ADMIN", ["READ", "ADMIN"], ttl_seconds=3600)
    engine4.authenticate(raw_token4)
    engine4.authenticate("not-a-real-token-at-all")
    store4.revoke_token(raw_token4)
    engine4.authenticate(raw_token4)  # now revoked -- should fail

    all_events_text = [str(e) for e in store_audit.events] + [str(e) for e in engine_audit.events]
    checks["raw_token_not_in_any_audit_event"] = not any(raw_token4 in t for t in all_events_text)
    checks["audit_events_were_actually_generated"] = len(store_audit.events) + len(engine_audit.events) >= 4
finally:
    cleanup(path4)

# --- 5. Expiration survives restart. ------------------------------------------
path5 = fresh_db_path()
try:
    clock5 = FakeClock()
    store5a = HashedTokenStore(path5, now_fn=clock5)
    token5 = store5a.issue_token("USER-EXPIRY-CHECK", "USER", ["READ"], ttl_seconds=60)
    checks["expiry_not_yet_expired_before_restart"] = store5a.lookup(token5)["expired"] is False
    del store5a  # simulate process exit

    clock5.advance(seconds=61)  # time passes across the "restart"
    store5b = HashedTokenStore(path5, now_fn=clock5)  # fresh instance, same file
    checks["expiry_correctly_expired_after_restart"] = store5b.lookup(token5)["expired"] is True
finally:
    cleanup(path5)

# --- 6. Revocation survives restart. -------------------------------------------
path6 = fresh_db_path()
try:
    store6a = HashedTokenStore(path6)
    token6 = store6a.issue_token("USER-REVOKE-CHECK", "USER", ["READ"], ttl_seconds=3600)
    store6a.revoke_token(token6)
    del store6a

    store6b = HashedTokenStore(path6)
    checks["revocation_survives_restart"] = store6b.lookup(token6)["expired"] is True
finally:
    cleanup(path6)

# --- 7. Roles and permissions survive restart. ---------------------------------
path7 = fresh_db_path()
try:
    store7a = HashedTokenStore(path7)
    token7 = store7a.issue_token("USER-ROLE-CHECK", "FOUNDER", ["READ", "EXPORT", "ADMIN", "FOUNDER"], ttl_seconds=3600)
    del store7a

    store7b = HashedTokenStore(path7)
    data7 = store7b.lookup(token7)
    checks["role_survives_restart"] = data7["role"] == "FOUNDER"
    checks["permissions_survive_restart"] = data7["permissions"] == ["READ", "EXPORT", "ADMIN", "FOUNDER"]
    checks["user_id_survives_restart"] = data7["user_id"] == "USER-ROLE-CHECK"

    # And restart survival end-to-end through AuthEngine + authorize().
    engine7 = AuthEngine(token_store=store7b)
    auth_status, auth_result = engine7.authenticate(token7)
    authz_status = engine7.authorize(auth_result, AuthPermission.FOUNDER)
    checks["restart_survived_role_authorizes_correctly"] = auth_status == "PASS" and authz_status == "PASS"
finally:
    cleanup(path7)

# --- 8. Separate test databases cannot contaminate each other. -----------------
path8a = fresh_db_path()
path8b = fresh_db_path()
try:
    store8a = HashedTokenStore(path8a)
    store8b = HashedTokenStore(path8b)
    token8a = store8a.issue_token("USER-DB-A", "USER", ["READ"], ttl_seconds=3600)
    checks["token_from_db_a_works_in_db_a"] = store8a.lookup(token8a) is not None
    checks["token_from_db_a_does_not_work_in_db_b"] = store8b.lookup(token8a) is None

    token8b = store8b.issue_token("USER-DB-B", "USER", ["READ"], ttl_seconds=3600)
    checks["token_from_db_b_does_not_work_in_db_a"] = store8a.lookup(token8b) is None
    checks["db_a_only_contains_its_own_token_after_both_issued"] = (
        store8a.lookup(token8a) is not None and store8a.lookup(token8b) is None
    )
finally:
    cleanup(path8a)
    cleanup(path8b)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"AUTH-TOKEN-WIRE-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
