import sys
import io
import zipfile
import tempfile
import os
import pandas as pd
from era.live_adapters.dcad_bulk_data_adapter import DCADBulkDataAdapter
from era.live_adapters.dcad_bulk_data_models import DCADAccountMapping
from era.live_adapters import dcad_bulk_errors as errors
from era.network.mock_transport import MockHttpTransport
from era.network.network_models import HttpResponse
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import TokenStore, MockTokenStore
from era.live_adapters.dcad_test_data import resolve_dcad_test_paths
APPR_PATH, INFO_PATH, USING_FULL_DCAD_DATA = resolve_dcad_test_paths()

print("DCAD-MAP-AUTH-001 HARD REVIEW VERIFICATION")
print("=" * 70)

checks = {}

URL = "https://test/dcad.zip"
ACCT_BASELINE = "00000416479000000"

appr_df = pd.read_csv(APPR_PATH, dtype=str, nrows=50)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("ACCOUNT_APPRL_YEAR.CSV", appr_df.head(3).to_csv(index=False))
REAL_ZIP = buf.getvalue()


def fresh_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    return path


def cleanup(path):
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


def new_adapter(auth=None):
    transport = MockHttpTransport()
    transport.set_response(URL, HttpResponse(200, "", content=REAL_ZIP))
    path = fresh_db_path()
    adapter = DCADBulkDataAdapter(download_url=URL, transport=transport, index_db_path=path, auth=auth)
    return adapter, path


class CaptureOnlyTokenStore(TokenStore):
    """A token carrying CAPTURE (not ADMIN/FOUNDER) -- exists to prove
    item 3: CAPTURE-only, which OP-AUTH-001 accepts for manual capture,
    must NOT be sufficient here. This is a deliberately different bar
    from the manual adapter, by design, and needs its own proof."""

    def lookup(self, token):
        if token != "capture-only-token":
            return None
        return {"user_id": "FIELD-OP-001", "role": "USER", "permissions": ["CAPTURE"], "expired": False}


mapping = DCADAccountMapping("P-TEST", ACCT_BASELINE, "2025")

# --- 0. Structural checks, read directly from source, not assumed. ----------
import inspect
retrieve_source = inspect.getsource(DCADBulkDataAdapter.retrieve)
checks["retrieve_never_references_self_auth"] = "self.auth" not in retrieve_source
checks["dcad_account_mapping_has_no_actor_field"] = not any(
    f in DCADAccountMapping.__dataclass_fields__ for f in
    ("actor", "user_id", "role", "registered_by", "captured_by", "author")
)

# --- 1. Missing authentication blocks mutation (no auth wired at all). ------
adapter1, path1 = new_adapter(auth=None)
try:
    status, ok = adapter1.register_account_mapping(mapping, "admin-token")
    checks["missing_auth_engine_blocks_mutation"] = status == errors.AUTH_ENGINE_REQUIRED and not ok
    checks["missing_auth_engine_does_not_register"] = adapter1._mappings.get("P-TEST") is None
finally:
    cleanup(path1)

# Also: an auth engine wired in, but no token given at all.
adapter1b, path1b = new_adapter(auth=AuthEngine(token_store=MockTokenStore()))
try:
    status, ok = adapter1b.register_account_mapping(mapping, None)
    checks["missing_token_blocks_mutation"] = status == "TOKEN_REQUIRED" and not ok
finally:
    cleanup(path1b)

# --- 2. USER with READ permission cannot mutate mappings. -------------------
adapter2, path2 = new_adapter(auth=AuthEngine(token_store=MockTokenStore()))
try:
    status, ok = adapter2.register_account_mapping(mapping, "user-token")  # USER role, READ only
    checks["user_read_permission_cannot_mutate"] = status == "PERMISSION_DENIED" and not ok
    checks["user_read_permission_does_not_register"] = adapter2._mappings.get("P-TEST") is None
finally:
    cleanup(path2)

# --- 3. USER with CAPTURE-only permission cannot mutate mappings --
# deliberately stricter than the manual adapter, which DOES accept
# CAPTURE alone (OP-AUTH-001). This is the item most likely to be
# silently wrong if DCAD-MAP-AUTH-001 accidentally reused OP-AUTH-001's
# permission check instead of its own. -----------------------------------
adapter3, path3 = new_adapter(auth=AuthEngine(token_store=CaptureOnlyTokenStore()))
try:
    status, ok = adapter3.register_account_mapping(mapping, "capture-only-token")
    checks["capture_only_permission_cannot_mutate"] = status == "PERMISSION_DENIED" and not ok
    checks["capture_only_does_not_register"] = adapter3._mappings.get("P-TEST") is None
finally:
    cleanup(path3)

# --- 4. ADMIN can mutate. ----------------------------------------------------
adapter4, path4 = new_adapter(auth=AuthEngine(token_store=MockTokenStore()))
try:
    status, ok = adapter4.register_account_mapping(mapping, "admin-token")
    checks["admin_can_mutate"] = status == "PASS" and ok
    checks["admin_mutation_actually_registered"] = adapter4._mappings.get("P-TEST") is not None
finally:
    cleanup(path4)

# --- 5. FOUNDER can mutate. --------------------------------------------------
adapter5, path5 = new_adapter(auth=AuthEngine(token_store=MockTokenStore()))
try:
    status, ok = adapter5.register_account_mapping(mapping, "founder-token")
    checks["founder_can_mutate"] = status == "PASS" and ok
    checks["founder_mutation_actually_registered"] = adapter5._mappings.get("P-TEST") is not None
finally:
    cleanup(path5)

# --- 6. Invalid token blocks before mutation. --------------------------------
adapter6, path6 = new_adapter(auth=AuthEngine(token_store=MockTokenStore()))
try:
    status, ok = adapter6.register_account_mapping(mapping, "this-token-does-not-exist")
    checks["invalid_token_blocks_mutation"] = status == "INVALID_TOKEN" and not ok
    checks["invalid_token_does_not_register"] = adapter6._mappings.get("P-TEST") is None
finally:
    cleanup(path6)

# --- 7. Expired token blocks before mutation. --------------------------------
adapter7, path7 = new_adapter(auth=AuthEngine(token_store=MockTokenStore()))
try:
    status, ok = adapter7.register_account_mapping(mapping, "expired-token")
    checks["expired_token_blocks_mutation"] = status == "EXPIRED_TOKEN" and not ok
    checks["expired_token_does_not_register"] = adapter7._mappings.get("P-TEST") is None
finally:
    cleanup(path7)

# --- 8. Revoked token blocks before mutation -- real HashedTokenStore,
# a real issued token, genuinely revoked, not simulated. ---------------------
from era.auth.hashed_token_store import HashedTokenStore
path8_tokens = fresh_db_path()
try:
    token_store8 = HashedTokenStore(path8_tokens)
    real_token8 = token_store8.issue_token("ADMIN-REVOKE-TEST", "ADMIN", ["READ", "EXPORT", "ADMIN"], ttl_seconds=3600)
    adapter8, path8 = new_adapter(auth=AuthEngine(token_store=token_store8))
    try:
        # Confirm it WOULD have worked before revocation.
        pre_status, pre_ok = adapter8.register_account_mapping(
            DCADAccountMapping("P-PRE-REVOKE", ACCT_BASELINE, "2025"), real_token8
        )
        checks["valid_admin_token_works_before_revocation"] = pre_status == "PASS" and pre_ok

        token_store8.revoke_token(real_token8)
        status, ok = adapter8.register_account_mapping(mapping, real_token8)
        checks["revoked_token_blocks_mutation"] = status == "EXPIRED_TOKEN" and not ok
        checks["revoked_token_does_not_register_new_mapping"] = adapter8._mappings.get("P-TEST") is None
    finally:
        cleanup(path8)
finally:
    cleanup(path8_tokens)

# --- 9. Caller-supplied actor identity is ignored. DCADAccountMapping
# has no field for this at all (checked structurally above), so the
# only remaining surface is the AUDIT record -- prove it always
# reflects the AUTHENTICATED identity, never anything else, across two
# different real authenticated identities registering the SAME
# property_id in sequence. ----------------------------------------------------
adapter9, path9 = new_adapter(auth=AuthEngine(token_store=MockTokenStore()))
try:
    adapter9.register_account_mapping(
        DCADAccountMapping("P-IDENTITY", ACCT_BASELINE, "2025"), "admin-token"
    )
    admin_event = next(e for e in adapter9.audit.events if e["event_type"] == "DCAD_MAPPING_REGISTERED")
    checks["audit_reflects_authenticated_admin_identity"] = (
        admin_event["payload"]["registered_by"] == "ADMIN-001" and admin_event["payload"]["role"] == "ADMIN"
    )

    adapter9.register_account_mapping(
        DCADAccountMapping("P-IDENTITY", ACCT_BASELINE, "2025"), "founder-token"
    )
    founder_events = [e for e in adapter9.audit.events if e["event_type"] == "DCAD_MAPPING_REGISTERED"]
    checks["audit_reflects_authenticated_founder_identity_on_second_call"] = (
        founder_events[-1]["payload"]["registered_by"] == "FOUNDER-001"
        and founder_events[-1]["payload"]["role"] == "FOUNDER"
    )
    checks["no_caller_supplied_identity_field_exists_to_override_this"] = (
        "captured_by" not in mapping.__dataclass_fields__ and "actor" not in mapping.__dataclass_fields__
    )
finally:
    cleanup(path9)

# --- 10. user_id and role are derived from the authenticated identity
# -- re-confirmed end-to-end with a real HashedTokenStore-issued token
# (not just MockTokenStore's fixed strings), proving this isn't
# special-cased to the mock. ---------------------------------------------------
path10_tokens = fresh_db_path()
try:
    token_store10 = HashedTokenStore(path10_tokens)
    real_token10 = token_store10.issue_token("REAL-FOUNDER-XYZ", "FOUNDER", ["READ", "EXPORT", "ADMIN", "FOUNDER"], ttl_seconds=3600)
    adapter10, path10 = new_adapter(auth=AuthEngine(token_store=token_store10))
    try:
        status, ok = adapter10.register_account_mapping(
            DCADAccountMapping("P-REAL-TOKEN", ACCT_BASELINE, "2025"), real_token10
        )
        real_event = next(e for e in adapter10.audit.events if e["event_type"] == "DCAD_MAPPING_REGISTERED")
        checks["real_hashed_token_store_identity_correctly_derived"] = (
            status == "PASS" and ok
            and real_event["payload"]["registered_by"] == "REAL-FOUNDER-XYZ"
            and real_event["payload"]["role"] == "FOUNDER"
        )
    finally:
        cleanup(path10)
finally:
    cleanup(path10_tokens)

# --- Ordinary read/lookup remains completely unaffected by any of this
# -- a retrieve() call with no auth wired at all still works. ----------------
transport_read = MockHttpTransport()
transport_read.set_response(URL, HttpResponse(200, "", content=REAL_ZIP))
path_read = fresh_db_path()
try:
    read_adapter = DCADBulkDataAdapter(download_url=URL, transport=transport_read, index_db_path=path_read, auth=None)
    # Register via a raw dict manipulation to isolate this check from
    # register_account_mapping's own gating -- proving retrieve() itself,
    # not the mapping registration path, is what's under test here.
    read_adapter._mappings["P-READ-ONLY"] = DCADAccountMapping("P-READ-ONLY", ACCT_BASELINE, "2025")
    read_status, read_payload = read_adapter.retrieve("P-READ-ONLY")
    checks["ordinary_read_unaffected_by_missing_auth"] = read_status == "PASS" and len(read_payload.get("evidence", [])) > 0
finally:
    cleanup(path_read)

# --- No duplicate auth/mapping system: confirm this adapter uses the
# SAME AuthEngine type as everything else, not a bespoke check. --------------
checks["uses_standard_auth_engine_type"] = isinstance(adapter4.auth, AuthEngine)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"DCAD-MAP-AUTH-001 HARD REVIEW CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
