import sys
from era.app import build_app, bootstrap_demo
from era.auth.token_store import MockTokenStore
from era.auth.auth_engine import AuthEngine
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType

print("AUTH-WIRE-001 VERIFICATION")
print("=" * 70)

identity = PropertyIdentity(
    property_id="ERA-PR-2026-000001",
    address="5926 Sandhurst Ln Unit 224", city="Dallas", state="TX",
    zip_code="75252", county="Dallas", parcel_apn="00000000000",
    latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)

app = build_app(token_store=MockTokenStore())
bootstrap_demo(app)
result = app.run_property(
    property_id=identity.property_id, identity=identity,
    state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
)
api = app.c.api

checks = {}

# --- missing auth blocked ---
status, response = api.get_property(None, identity.property_id)
checks["missing_auth_blocked"] = status == "TOKEN_REQUIRED" and response is None
status, response = api.get_property("", identity.property_id)
checks["empty_token_also_blocked"] = status == "TOKEN_REQUIRED" and response is None

# --- invalid token blocked ---
status, response = api.get_property("not-a-real-token", identity.property_id)
checks["invalid_token_blocked"] = status == "INVALID_TOKEN" and response is None

# --- expired token blocked ---
status, response = api.get_property("expired-token", identity.property_id)
checks["expired_token_blocked"] = status == "EXPIRED_TOKEN" and response is None

# --- user READ allowed (property/evidence/decision/policy all require READ) ---
u_prop = api.get_property("user-token", identity.property_id)
u_evid = api.get_evidence("user-token", identity.property_id)
u_dec = api.get_decision("user-token", identity.property_id)
u_pol = api.get_policy("user-token", identity.property_id)
checks["user_read_allowed"] = all(s == "PASS" for s, _ in [u_prop, u_evid, u_dec, u_pol])

# --- user ADMIN denied (audit endpoint requires ADMIN; USER role doesn't have it) ---
status, response = api.get_audit("user-token", identity.property_id)
checks["user_admin_denied"] = status == "PERMISSION_DENIED" and response is None
# USER also lacks EXPORT.
status, response = api.get_export("user-token", identity.property_id)
checks["user_export_denied"] = status == "PERMISSION_DENIED" and response is None

# --- admin allowed where appropriate (ADMIN has READ+EXPORT+ADMIN, not FOUNDER) ---
a_prop = api.get_property("admin-token", identity.property_id)
a_export = api.get_export("admin-token", identity.property_id)
a_audit = api.get_audit("admin-token", identity.property_id)
checks["admin_allowed_where_appropriate"] = all(
    s == "PASS" for s, _ in [a_prop, a_export, a_audit]
)

# --- founder allowed (FOUNDER holds every permission) ---
f_prop = api.get_property("founder-token", identity.property_id)
f_export = api.get_export("founder-token", identity.property_id)
f_audit = api.get_audit("founder-token", identity.property_id)
checks["founder_allowed"] = all(s == "PASS" for s, _ in [f_prop, f_export, f_audit])

# --- health public (no token required, no auth check applied) ---
health_status, health_response = api.health()
checks["health_public_no_token_arg_required"] = health_status == "PASS"
checks["health_reveals_no_property_data"] = health_response.property_id is None

# --- deterministic authorization: same token+permission, called twice,
# same result both times ---
r1_status, r1 = api.get_property("user-token", identity.property_id)
r2_status, r2 = api.get_property("user-token", identity.property_id)
checks["deterministic_authorization"] = (
    r1_status == r2_status == "PASS" and r1.data == r2.data
)
d1_status, _ = api.get_audit("user-token", identity.property_id)
d2_status, _ = api.get_audit("user-token", identity.property_id)
checks["deterministic_denial"] = d1_status == d2_status == "PERMISSION_DENIED"

# --- audit recorded: both allowed and denied calls leave a trace ---
before = len(api.audit.events)
api.get_property("user-token", identity.property_id)  # allowed
api.get_audit("user-token", identity.property_id)      # denied
after = len(api.audit.events)
checks["allowed_call_recorded"] = any(
    e["event_type"] == "API_REQUEST_RECORDED" for e in api.audit.events[before:after]
)
checks["denied_call_recorded"] = any(
    e["event_type"] == "API_BLOCKED" for e in api.audit.events[before:after]
)
checks["auth_engine_also_logs_authentication"] = any(
    e["event_type"] == "AUTHENTICATED" for e in app.c.auth.audit.events
)
checks["auth_engine_also_logs_denial"] = any(
    e["event_type"] == "AUTH_BLOCKED" and e["payload"].get("reason") == "PERMISSION_DENIED"
    for e in app.c.auth.audit.events
)

# --- fail-closed: an EraApiEngine built with no auth at all must block,
# not silently allow ---
from era.api.api_engine import EraApiEngine
unwired = EraApiEngine(store=app.c.api_store)  # no auth= passed
status, response = unwired.get_property("founder-token", identity.property_id)
checks["no_auth_wired_fails_closed"] = status == "AUTH_ENGINE_REQUIRED" and response is None

# --- AUTH-TOKEN-WIRE-001: the DEFAULT token store (no override at all)
# must be HashedTokenStore, and the old MockTokenStore fixed tokens
# must NOT authenticate against it. This is the actual regression
# guard for the production/default flip -- every other check in this
# file explicitly passes MockTokenStore(), which would still pass even
# if the underlying default silently reverted; this one doesn't. ------------
from era.auth.hashed_token_store import HashedTokenStore
default_engine = AuthEngine()
checks["default_token_store_is_hashed_not_mock"] = isinstance(default_engine.token_store, HashedTokenStore)
default_status, default_result = default_engine.authenticate("admin-token")
checks["default_store_does_not_authenticate_old_mock_tokens"] = (
    default_status == "INVALID_TOKEN" and default_result is None
)
default_app = build_app()  # no token_store override
checks["default_build_app_also_uses_hashed_token_store"] = (
    isinstance(default_app.c.auth.token_store, HashedTokenStore)
)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"AUTH-WIRE-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
