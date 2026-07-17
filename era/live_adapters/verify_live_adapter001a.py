import sys
import os
import inspect
import tempfile as _tempfile
from dataclasses import replace as dc_replace
from era.live_adapters.manual_record_adapter import ManualRecordAdapter, validate_capture
from era.live_adapters.manual_record_models import ManualRecordCapture, ManualFieldCapture
from era.live_adapters import manual_record_errors as errors
from era.auth.auth_engine import AuthEngine
from era.auth.token_store import TokenStore, MockTokenStore
from era.app import build_app, bootstrap_manual_demo
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory

print("LIVE-ADAPTER-001A VERIFICATION")
print("=" * 70)

checks = {}

VALIDATION_PROPERTY_ID = "ERA-PR-2026-000001"
VALIDATION_ADDRESS = "5926 Sandhurst Ln Unit 224"
ADMIN_TOKEN = "admin-token"
FOUNDER_TOKEN = "founder-token"
USER_TOKEN = "user-token"


def full_capture(property_id=VALIDATION_PROPERTY_ID, **overrides):
    data = dict(
        property_id=property_id,
        source_reference="DCAD-PUBLIC-LOOKUP-MANUAL",
        legal_basis="PUBLIC_RECORD",
        captured_by="unverified-claim",  # deliberately not trusted -- see test below
        fields=(
            ManualFieldCapture("property_address", VALIDATION_ADDRESS),
            ManualFieldCapture("city", "Dallas"),
            ManualFieldCapture("county", "Dallas"),
            ManualFieldCapture("state", "TX"),
            ManualFieldCapture("property_type", "CONDO"),
        ),
    )
    data.update(overrides)
    return ManualRecordCapture(**data)


def validation_identity():
    return PropertyIdentity(
        property_id=VALIDATION_PROPERTY_ID, address=VALIDATION_ADDRESS, city="Dallas",
        state="TX", zip_code="75252", county="Dallas", parcel_apn="00000000000",
        latitude=None, longitude=None,
        property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
    )


def authed_adapter():
    return ManualRecordAdapter(auth=AuthEngine(token_store=MockTokenStore()))


# --- 0. Operator authorization is real, not an honor system. -------------
unauthed = ManualRecordAdapter()
status, staged = unauthed.stage_capture(full_capture(), ADMIN_TOKEN)
checks["no_auth_wired_fails_closed"] = status == errors.AUTH_ENGINE_REQUIRED and not staged

status, staged = authed_adapter().stage_capture(full_capture(), None)
checks["missing_token_blocked"] = status == "TOKEN_REQUIRED" and not staged

status, staged = authed_adapter().stage_capture(full_capture(), "not-a-real-token")
checks["invalid_token_blocked"] = status == "INVALID_TOKEN" and not staged

status, staged = authed_adapter().stage_capture(full_capture(), "expired-token")
checks["expired_token_blocked"] = status == "EXPIRED_TOKEN" and not staged

status, staged = authed_adapter().stage_capture(full_capture(), USER_TOKEN)
checks["user_with_read_permission_allowed"] = status == errors.PASS and staged

status, staged = authed_adapter().stage_capture(full_capture(), ADMIN_TOKEN)
checks["admin_token_allowed"] = status == errors.PASS and staged

status, staged = authed_adapter().stage_capture(full_capture(), FOUNDER_TOKEN)
checks["founder_token_allowed"] = status == errors.PASS and staged

# A token with NEITHER READ nor CAPTURE must be genuinely blocked --
# proves this isn't just "everyone passes now."
class NoPermissionTokenStore(TokenStore):
    def lookup(self, token):
        if token != "no-permission-token":
            return None
        return {"user_id": "NOBODY-001", "role": "GUEST", "permissions": [], "expired": False}

no_perm_adapter = ManualRecordAdapter(auth=AuthEngine(token_store=NoPermissionTokenStore()))
status, staged = no_perm_adapter.stage_capture(full_capture(), "no-permission-token")
checks["genuinely_insufficient_permission_blocked"] = status == "PERMISSION_DENIED" and not staged

# CAPTURE permission (not READ) is accepted as an alternative grant --
# OP-AUTH-001's "READ or CAPTURE" rule, exercised on its own branch.
class CaptureOnlyTokenStore(TokenStore):
    def lookup(self, token):
        if token != "capture-only-token":
            return None
        return {"user_id": "FIELD-OP-001", "role": "USER", "permissions": ["CAPTURE"], "expired": False}

capture_only_adapter = ManualRecordAdapter(auth=AuthEngine(token_store=CaptureOnlyTokenStore()))
status, staged = capture_only_adapter.stage_capture(full_capture("ERA-PR-CAPTURE-PERM"), "capture-only-token")
checks["capture_permission_alone_allowed"] = status == errors.PASS and staged
checks["capture_permission_identity_recorded_correctly"] = (
    capture_only_adapter._pending["ERA-PR-CAPTURE-PERM"].captured_by == "FIELD-OP-001"
)

identity_test_adapter = authed_adapter()
claimed_capture = full_capture("ERA-PR-IDENTITY-TEST", captured_by="someone-else-entirely")
identity_test_adapter.stage_capture(claimed_capture, ADMIN_TOKEN)
staged_record = identity_test_adapter._pending["ERA-PR-IDENTITY-TEST"]
checks["captured_by_not_trusted_from_caller"] = staged_record.captured_by == "ADMIN-001"
checks["captured_by_overwritten_not_the_claimed_value"] = staged_record.captured_by != "someone-else-entirely"

# --- 1. Missing record blocked. ------------------------------------------
adapter = authed_adapter()
status, staged = adapter.stage_capture(None, ADMIN_TOKEN)
checks["missing_record_blocked_on_stage"] = status == errors.RECORD_REQUIRED and not staged
retrieve_status, retrieve_payload = adapter.retrieve("nothing-staged-for-this-id")
checks["missing_record_blocked_on_retrieve"] = (
    retrieve_status == errors.RECORD_REQUIRED and retrieve_payload == {}
)

# --- 2. Missing source reference blocked. ---------------------------------
status, staged = authed_adapter().stage_capture(full_capture(source_reference=""), ADMIN_TOKEN)
checks["missing_source_reference_blocked"] = status == errors.SOURCE_REFERENCE_REQUIRED and not staged

# --- 3. Missing legal basis blocked. ---------------------------------------
status, staged = authed_adapter().stage_capture(full_capture(legal_basis=""), ADMIN_TOKEN)
checks["missing_legal_basis_blocked"] = status == errors.LEGAL_BASIS_REQUIRED and not staged

# --- 4. Missing property ID blocked. ----------------------------------------
status, staged = authed_adapter().stage_capture(full_capture(property_id=""), ADMIN_TOKEN)
checks["missing_property_id_blocked"] = status == errors.PROPERTY_ID_REQUIRED and not staged

# --- 5. Malformed field blocked. --------------------------------------------
malformed_empty_value = full_capture(fields=(ManualFieldCapture("property_address", ""),))
status, staged = authed_adapter().stage_capture(malformed_empty_value, ADMIN_TOKEN)
checks["malformed_field_empty_value_blocked"] = status == errors.MALFORMED_FIELD and not staged

malformed_empty_name = full_capture(fields=(ManualFieldCapture("", "some value"),))
status, staged = authed_adapter().stage_capture(malformed_empty_name, ADMIN_TOKEN)
checks["malformed_field_empty_name_blocked"] = status == errors.MALFORMED_FIELD and not staged

malformed_whitespace_value = full_capture(fields=(ManualFieldCapture("property_address", "   "),))
status, staged = authed_adapter().stage_capture(malformed_whitespace_value, ADMIN_TOKEN)
checks["malformed_field_whitespace_only_blocked"] = status == errors.MALFORMED_FIELD and not staged

# --- 6. Read-only enforced. --------------------------------------------------
write_ok, write_reason = ManualRecordAdapter().attempt_write()
checks["read_only_enforced"] = write_ok is False and write_reason == errors.READ_ONLY_ADAPTER

# --- 7. Confidence authority blocked. ----------------------------------------
conf_ok, conf_reason = ManualRecordAdapter().assign_confidence()
checks["confidence_authority_blocked"] = (
    conf_ok is False and conf_reason == errors.CONFIDENCE_AUTHORITY_VIOLATION
)

# ---- integration tests against the real container/pipeline ----------------

# --- 8. Rate limit still enforced. -------------------------------------------
rl_app = build_app(token_store=MockTokenStore())
bootstrap_manual_demo(rl_app)
tight_connector = ConnectorRecord(
    connector_id="MANUAL_RECORD_CAPTURE", provider_name="Manual Public-Record Capture",
    version="1.0", category=ConnectorCategory.COUNTY_PUBLIC_RECORDS,
    legal_classification=LegalClassification.PUBLIC_RECORD, status=ConnectorStatus.ACTIVE,
    capabilities=["OWNERSHIP"],
    resource_policy=ResourcePolicy(refresh_schedule_hours=24, rate_limit_per_day=500,
                                    cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=1),
    retry_policy=RetryPolicy(max_retries=2, retry_delay_seconds=10),
)
rl_app.c.srr.connectors["MANUAL_RECORD_CAPTURE"] = tight_connector

rl_app.c.manual_record_adapter.stage_capture(full_capture("ERA-PR-RATE-1"), ADMIN_TOKEN)
rl_app.c.manual_record_adapter.stage_capture(full_capture("ERA-PR-RATE-2"), ADMIN_TOKEN)
result1 = rl_app.run_property(
    property_id="ERA-PR-RATE-1",
    identity=PropertyIdentity(property_id="ERA-PR-RATE-1", address=VALIDATION_ADDRESS, city="Dallas",
                               state="TX", zip_code="75252", county="Dallas", parcel_apn="1",
                               latitude=None, longitude=None,
                               property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL),
    state="TX", county="Dallas", provider_id="MANUAL_RECORD_CAPTURE",
)
result2 = rl_app.run_property(
    property_id="ERA-PR-RATE-2",
    identity=PropertyIdentity(property_id="ERA-PR-RATE-2", address=VALIDATION_ADDRESS, city="Dallas",
                               state="TX", zip_code="75252", county="Dallas", parcel_apn="2",
                               latitude=None, longitude=None,
                               property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL),
    state="TX", county="Dallas", provider_id="MANUAL_RECORD_CAPTURE",
)
checks["rate_limit_first_request_allowed"] = (
    result1.stage("RATE_LIMIT") is not None and result1.stage("RATE_LIMIT").ok
)
checks["rate_limit_second_request_blocked"] = (
    result2.stage("RATE_LIMIT") is not None and not result2.stage("RATE_LIMIT").ok
    and not result2.ok
)

# --- 9. Retry wrapper still used. ---------------------------------------------
retry_app = build_app(token_store=MockTokenStore())
bootstrap_manual_demo(retry_app)
retry_app.c.manual_record_adapter.stage_capture(full_capture("ERA-PR-RETRY-1"), ADMIN_TOKEN)
connector = retry_app.c.srr.get_connector("MANUAL_RECORD_CAPTURE")

real_retrieve = retry_app.c.manual_record_adapter.retrieve
flaky_log = {"n": 0}
def flaky_retrieve(property_id):
    flaky_log["n"] += 1
    if flaky_log["n"] < 2:
        return "PROVIDER_UNAVAILABLE", {}
    return real_retrieve(property_id)
retry_app.c.manual_record_adapter.retrieve = flaky_retrieve

retry_status, retry_result = retry_app.c.retry_executor.run(
    "MANUAL_RECORD_CAPTURE", connector.retry_policy,
    lambda: retry_app.c.manual_record_adapter.retrieve("ERA-PR-RETRY-1"),
)
retry_app.c.manual_record_adapter.retrieve = real_retrieve

checks["retry_wrapper_used_and_recovers"] = retry_status == "PASS" and flaky_log["n"] == 2
checks["retry_wrapper_recorded_attempt_event"] = any(
    e["event_type"] == "RETRY_ATTEMPTED" for e in retry_app.c.retry_executor.audit.events
)
checks["retry_wrapper_recorded_success_event"] = any(
    e["event_type"] == "RETRY_SUCCEEDED" for e in retry_app.c.retry_executor.audit.events
)

# --- 10, 11, 12: full pipeline, provenance, export-only-after-policy. --------
main_app = build_app(token_store=MockTokenStore())
bootstrap_manual_demo(main_app)
main_app.c.manual_record_adapter.stage_capture(full_capture(), ADMIN_TOKEN)
result = main_app.run_property(
    property_id=VALIDATION_PROPERTY_ID, identity=validation_identity(),
    state="TX", county="Dallas", provider_id="MANUAL_RECORD_CAPTURE",
)

checks["full_pipeline_succeeds_with_valid_manual_record"] = result.ok
checks["full_pipeline_reaches_export"] = (
    result.export_package is not None and result.export_package.status.value == "EXPORTED"
)

checks["provenance_created_nonempty"] = len(result.provenance_records) > 0
checks["provenance_records_tagged_with_manual_provider"] = all(
    pr.provider_id == "MANUAL_RECORD_CAPTURE" for pr in result.provenance_records
)
checks["provenance_records_carry_manual_source_reference"] = all(
    pr.source_reference == "DCAD-PUBLIC-LOOKUP-MANUAL" for pr in result.provenance_records
)
checks["provenance_records_carry_manual_legal_basis"] = all(
    pr.legal_basis == "PUBLIC_RECORD" for pr in result.provenance_records
)
checks["provenance_registered_in_epm"] = any(
    r.provider_id == "MANUAL_RECORD_CAPTURE" for r in main_app.c.epm.records.values()
)

stage_names = [s.name for s in result.stages]
checks["policy_stage_precedes_export_stage"] = (
    "POL" in stage_names and "EXP" in stage_names
    and stage_names.index("POL") < stage_names.index("EXP")
)
checks["export_verdict_matches_policy_verdict"] = (
    result.export_package.policy_verdict == result.policy_result.verdict.value
)

denial_app = build_app(token_store=MockTokenStore())
bootstrap_manual_demo(denial_app)
denial_app.c.manual_record_adapter.stage_capture(full_capture("ERA-PR-MANUAL-DENIED"), ADMIN_TOKEN)
original_policy = denial_app.c.default_policy
denial_app.c.default_policy = dc_replace(original_policy, export_allowed=False)
denied_result = denial_app.run_property(
    property_id="ERA-PR-MANUAL-DENIED",
    identity=PropertyIdentity(property_id="ERA-PR-MANUAL-DENIED", address=VALIDATION_ADDRESS, city="Dallas",
                               state="TX", zip_code="75252", county="Dallas", parcel_apn="3",
                               latitude=None, longitude=None,
                               property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL),
    state="TX", county="Dallas", provider_id="MANUAL_RECORD_CAPTURE",
)
denial_app.c.default_policy = original_policy
checks["export_genuinely_blocked_when_policy_denies"] = (
    not denied_result.ok and denied_result.stage("EXP") is not None
    and not denied_result.stage("EXP").ok
)

adapter_source = inspect.getsource(ManualRecordAdapter)
checks["adapter_never_references_upr_directly"] = (
    "upr" not in adapter_source.lower() and "unified_property_record" not in adapter_source.lower()
)

_audit_db_fd, _audit_db_path = _tempfile.mkstemp(suffix=".db")
os.close(_audit_db_fd)
os.remove(_audit_db_path)
try:
    audit_app = build_app(persistence_path=_audit_db_path, token_store=MockTokenStore())
    bootstrap_manual_demo(audit_app)
    audit_app.c.manual_record_adapter.stage_capture(full_capture("ERA-PR-AUDIT-CHECK"), ADMIN_TOKEN)
    persisted = audit_app.c.persistence_store.query_events(
        namespace="era.live_adapters.manual_record_adapter"
    )
    checks["manual_adapter_audit_trail_actually_persists"] = (
        any(e["event_type"] == "MANUAL_CAPTURE_STAGED" for e in persisted)
    )
    staged_event = next(e for e in persisted if e["event_type"] == "MANUAL_CAPTURE_STAGED")
    checks["audit_records_authenticated_user_id"] = staged_event["payload"].get("captured_by") == "ADMIN-001"
    checks["audit_records_role"] = staged_event["payload"].get("role") == "ADMIN"
    audit_app.c.manual_record_adapter.stage_capture(full_capture("ERA-PR-AUDIT-CHECK-2"), "no-permission-token")
    persisted_after_denial = audit_app.c.persistence_store.query_events(
        namespace="era.live_adapters.manual_record_adapter"
    )
    checks["blocked_auth_attempts_also_recorded_in_audit"] = any(
        e["payload"].get("reason") == "INVALID_TOKEN" for e in persisted_after_denial
    )
    del audit_app
    reopened = build_app(persistence_path=_audit_db_path)
    persisted_after_restart = reopened.c.persistence_store.query_events(
        namespace="era.live_adapters.manual_record_adapter"
    )
    checks["manual_adapter_audit_trail_survives_restart"] = (
        len(persisted_after_restart) == len(persisted_after_denial) and len(persisted_after_restart) > 0
    )
finally:
    for suffix in ("", "-wal", "-shm", ".audit.db", ".audit.db-wal", ".audit.db-shm"):
        if os.path.exists(_audit_db_path + suffix):
            os.remove(_audit_db_path + suffix)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"LIVE-ADAPTER-001A CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
