import sys
from time import sleep
from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
from era.acquisition import connector_errors as errors
def resource_policy(**overrides):
    data = {
        "refresh_schedule_hours": 24,
        "rate_limit_per_day": 500,
        "cache_duration_hours": 24,
        "monthly_budget_limit": 0.0,
        "max_requests": 500,
    }
    data.update(overrides)
    return ResourcePolicy(**data)
def retry_policy(**overrides):
    data = {
        "max_retries": 2,
        "retry_delay_seconds": 10,
    }
    data.update(overrides)
    return RetryPolicy(**data)
def connector(**overrides):
    data = {
        "connector_id": "COUNTY_TARRANT_ASSESSOR",
        "provider_name": "Tarrant County Assessor",
        "version": "1.0",
        "category": ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        "legal_classification": LegalClassification.PUBLIC_RECORD,
        "status": ConnectorStatus.ACTIVE,
        "capabilities": [
            "OWNERSHIP",
            "PARCEL",
            "TAX_ASSESSMENT",
            "BUILDING_SIZE",
            "LOT_SIZE",
            "YEAR_BUILT",
        ],
        "resource_policy": resource_policy(),
        "retry_policy": retry_policy(),
    }
    data.update(overrides)
    return ConnectorRecord(**data)
engine = SourceReliabilityRegistry()
tests = [
    ("EV-001", errors.CONNECTOR_REQUIRED, lambda: engine.register_connector(connector(connector_id=""))[0]),
    ("EV-003", errors.LEGAL_CLASSIFICATION_REQUIRED, lambda: engine.register_connector(connector(connector_id="BAD-LEGAL", legal_classification="PUBLIC"))[0]),
    ("EV-004", errors.RESOURCE_POLICY_REQUIRED, lambda: engine.register_connector(connector(connector_id="BAD-RATE", resource_policy=resource_policy(rate_limit_per_day=0)))[0]),
    ("EV-005", errors.REFRESH_POLICY_REQUIRED, lambda: engine.register_connector(connector(connector_id="BAD-REFRESH", resource_policy=resource_policy(refresh_schedule_hours=0)))[0]),
    ("EV-006", errors.UNKNOWN_CAPABILITY, lambda: engine.register_connector(connector(connector_id="BAD-CAP", capabilities=["ALIEN_SIGNAL"]))[0]),
    ("EV-007", errors.READ_ONLY_CONNECTOR, lambda: engine.attempt_evidence_modification()[1]),
    ("EV-008", errors.CONFIDENCE_AUTHORITY_VIOLATION, lambda: engine.attempt_confidence_assignment()[1]),
]
print("SRR-001 ACQUISITION REGISTRY VERIFICATION")
print("=" * 70)
passed = 0
for ev_id, expected, fn in tests:
    actual = fn()
    ok = actual == expected
    if ok:
        passed += 1
    print(ev_id)
    print("  EXPECTED:", expected)
    print("  ACTUAL:  ", actual)
    print("  PASS:    ", ok)
    print()
status, registered = engine.register_connector(connector())
dup_status, dup = engine.register_connector(connector())
print("EV-002")
print("  EXPECTED:", errors.DUPLICATE_CONNECTOR)
print("  ACTUAL:  ", dup_status)
print("  PASS:    ", dup_status == errors.DUPLICATE_CONNECTOR)
print()
if dup_status == errors.DUPLICATE_CONNECTOR:
    passed += 1
engine2 = SourceReliabilityRegistry()
status_a, a = engine2.register_connector(connector(connector_id="DET-001"))
engine3 = SourceReliabilityRegistry()
status_b, b = engine3.register_connector(connector(connector_id="DET-001"))
deterministic = (
    status_a == status_b
    and a.connector_id == b.connector_id
    and a.legal_classification == b.legal_classification
    and a.capabilities == b.capabilities
    and a.resource_policy.rate_limit_per_day == b.resource_policy.rate_limit_per_day
)
print("EV-009")
print("  EXPECTED:", errors.DETERMINISTIC_REGISTRY)
print("  ACTUAL:  ", errors.DETERMINISTIC_REGISTRY if deterministic else "NON_DETERMINISTIC")
print("  PASS:    ", deterministic)
print()
if deterministic:
    passed += 1
audit_ok = len(engine.audit.events) > 0
print("EV-010")
print("  EXPECTED:", "AUDIT PRESENT")
print("  ACTUAL:  ", "AUDIT PRESENT" if audit_ok else errors.AUDIT_REQUIRED)
print("  PASS:    ", audit_ok)
print()
if audit_ok:
    passed += 1
disable_status = engine.disable_connector("COUNTY_TARRANT_ASSESSOR")
disabled = engine.get_connector("COUNTY_TARRANT_ASSESSOR").status == ConnectorStatus.DISABLED
print("EV-011")
print("  EXPECTED:", "DISABLED STATE PERSISTED")
print("  ACTUAL:  ", "DISABLED STATE PERSISTED" if disabled else "STATUS_NOT_CHANGED")
print("  PASS:    ", disable_status == errors.PASS and disabled)
print()
if disable_status == errors.PASS and disabled:
    passed += 1
enable_status = engine.enable_connector("COUNTY_TARRANT_ASSESSOR")
enabled = engine.get_connector("COUNTY_TARRANT_ASSESSOR").status == ConnectorStatus.ACTIVE
print("EV-012")
print("  EXPECTED:", "ACTIVE STATE PERSISTED")
print("  ACTUAL:  ", "ACTIVE STATE PERSISTED" if enabled else "STATUS_NOT_CHANGED")
print("  PASS:    ", enable_status == errors.PASS and enabled)
print()
if enable_status == errors.PASS and enabled:
    passed += 1
before = connector(connector_id="TIME-001").created_at
sleep(1)
after = connector(connector_id="TIME-002").created_at
timestamp_ok = before != after
print("EV-013")
print("  EXPECTED:", "UNIQUE INSTANCE TIMESTAMPS")
print("  ACTUAL:  ", "UNIQUE INSTANCE TIMESTAMPS" if timestamp_ok else "SHARED_IMPORT_TIMESTAMP")
print("  PASS:    ", timestamp_ok)
print()
if timestamp_ok:
    passed += 1
success_status = engine.record_success("COUNTY_TARRANT_ASSESSOR", 120)
success_connector = engine.get_connector("COUNTY_TARRANT_ASSESSOR")
success_ok = (
    success_status == errors.PASS
    and success_connector.last_success is not None
    and success_connector.average_response_time_ms == 120
    and success_connector.consecutive_failures == 0
    and success_connector.success_count >= 1
)
print("EV-014")
print("  EXPECTED:", "SUCCESS METRICS RECORDED")
print("  ACTUAL:  ", "SUCCESS METRICS RECORDED" if success_ok else "SUCCESS_METRICS_MISSING")
print("  PASS:    ", success_ok)
print()
if success_ok:
    passed += 1
failure_status = engine.record_failure("COUNTY_TARRANT_ASSESSOR")
failure_connector = engine.get_connector("COUNTY_TARRANT_ASSESSOR")
failure_ok = (
    failure_status == errors.PASS
    and failure_connector.last_failure is not None
    and failure_connector.consecutive_failures == 1
    and failure_connector.failure_count >= 1
    and failure_connector.success_rate is not None
)
print("EV-015")
print("  EXPECTED:", "FAILURE METRICS RECORDED")
print("  ACTUAL:  ", "FAILURE METRICS RECORDED" if failure_ok else "FAILURE_METRICS_MISSING")
print("  PASS:    ", failure_ok)
print()
if failure_ok:
    passed += 1
happy_ok = (
    status == errors.PASS
    and registered is not None
    and registered.connector_id == "COUNTY_TARRANT_ASSESSOR"
)
print("HAPPY PATH")
print("  STATUS:", status)
print("  CONNECTOR:", registered.connector_id if registered else None)
print("  LEGAL:", registered.legal_classification.value if registered else None)
print("  CAPABILITIES:", len(registered.capabilities) if registered else None)
print("  CURRENT STATUS:", engine.get_connector("COUNTY_TARRANT_ASSESSOR").status.value)
print("  SUCCESS RATE:", engine.get_connector("COUNTY_TARRANT_ASSESSOR").success_rate)
print("  PASS:", happy_ok)
print()
print("AUDIT EVENTS:", len(engine.audit.events))
for event in engine.audit.events:
    print(event)
print()
print("VIOLATION TESTS PASSED:", f"{passed}/15")
print("OVERALL:", "PASS" if passed == 15 and happy_ok else "FAIL")
_ERA_OVERALL_OK = (passed == 15 and happy_ok)
if not _ERA_OVERALL_OK:
    sys.exit(1)
