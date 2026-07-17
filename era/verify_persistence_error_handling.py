import sys
import os
import stat
import tempfile
from era.shared.persistence import SqliteStore, PersistenceError
from era.shared.audit import BaseAuditPublisher

print("PERSISTENCE ERROR HANDLING VERIFICATION")
print("=" * 70)

checks = {}


class BrokenStore:
    """Test double: same shape as SqliteStore, but save_record always
    fails. Used to force every engine's failure path deterministically,
    without depending on flaky real-disk fault injection."""
    def event_sink(self, namespace):
        def _sink(event):
            raise PersistenceError("event_sink", namespace, event.get("event_type", "-"), RuntimeError("simulated"))
        return _sink
    def save_record(self, table_name, record_id, data, conn=None):
        raise PersistenceError("save_record", table_name, record_id, RuntimeError("simulated disk failure"))
    def load_record(self, table_name, record_id, conn=None):
        return None
    def list_records(self, table_name, conn=None):
        return []
    def delete_record(self, table_name, record_id, conn=None):
        raise PersistenceError("delete_record", table_name, record_id, RuntimeError("simulated"))
    def query_events(self, namespace=None, event_type=None, limit=500):
        return []


broken = BrokenStore()

# --- 1. SRR: register_connector must roll back and return
# PERSISTENCE_WRITE_FAILED, not raise. ---
from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
from era.acquisition import connector_errors as srr_errors

def make_connector():
    return ConnectorRecord(
        connector_id="COUNTY_TEST", provider_name="Test County", version="1.0",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS, legal_classification=LegalClassification.PUBLIC_RECORD,
        status=ConnectorStatus.ACTIVE, capabilities=["OWNERSHIP"],
        resource_policy=ResourcePolicy(refresh_schedule_hours=24, rate_limit_per_day=500,
                                        cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=500),
        retry_policy=RetryPolicy(max_retries=2, retry_delay_seconds=10),
    )

srr = SourceReliabilityRegistry(store=broken)
try:
    status, connector = srr.register_connector(make_connector())
    checks["srr_returns_failure_not_raises"] = status == srr_errors.PERSISTENCE_WRITE_FAILED and connector is None
except Exception:
    checks["srr_returns_failure_not_raises"] = False
checks["srr_rolled_back_no_ghost_connector"] = srr.get_connector("COUNTY_TEST") is None
checks["srr_audit_recorded_failure"] = any(
    e["payload"].get("reason") == srr_errors.PERSISTENCE_WRITE_FAILED for e in srr.audit.events
)

# --- 2. UPR: create_property must roll back. ---
from era.property_record.unified_property_record import UnifiedPropertyRecordEngine
from era.property_record.property_models import PropertyIdentity, EvidenceEntry
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record import property_errors as upr_errors

identity = PropertyIdentity(
    property_id="ERA-PR-TEST-001", address="1 Test St", city="Dallas", state="TX",
    zip_code="75001", county="Dallas", parcel_apn="000", latitude=None, longitude=None,
    property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
)
upr = UnifiedPropertyRecordEngine(store=broken)
try:
    status, record = upr.create_property(identity)
    checks["upr_returns_failure_not_raises"] = status == upr_errors.PERSISTENCE_WRITE_FAILED and record is None
except Exception:
    checks["upr_returns_failure_not_raises"] = False
checks["upr_rolled_back_no_ghost_property"] = identity.property_id not in upr.records

# --- 3. EPM: register_evidence must roll back (including the two-record
# supersede case). ---
from era.provenance.provenance_manager import EvidenceProvenanceManager
from era.provenance.provenance_models import ProvenanceInput
from era.provenance import provenance_errors as epm_errors

def make_input(evidence_id, previous=None):
    return ProvenanceInput(
        evidence_id=evidence_id, property_id="ERA-PR-TEST-001", canonical_field="address",
        canonical_value="1 Test St", original_value="1 Test St", provider_id="COUNTY_TEST",
        provider_name="Test County", legal_basis="PUBLIC_RECORD", source_reference="TEST-SRC",
        retrieved_at="2026-07-09T00:00:00+00:00", connector_version="1.0",
        adapter_version="LPA-001.0", normalization_version="ECM-001.0", previous_evidence_id=previous,
    )

epm_working = EvidenceProvenanceManager()  # real in-memory, to seed a first record
epm_working.register_evidence(make_input("EV-001"))
# Now attach a broken store to a fresh manager pre-loaded with the same
# record, and try to supersede it -- both the supersede and the insert
# must roll back together.
epm_broken = EvidenceProvenanceManager(store=broken)
epm_broken.records["EV-001"] = epm_working.records["EV-001"]
try:
    status, record = epm_broken.register_evidence(make_input("EV-002", previous="EV-001"))
    checks["epm_returns_failure_not_raises"] = status == epm_errors.PERSISTENCE_WRITE_FAILED and record is None
except Exception:
    checks["epm_returns_failure_not_raises"] = False
checks["epm_previous_record_not_superseded_after_rollback"] = (
    epm_broken.records["EV-001"].status.value == "ACTIVE"
)
checks["epm_new_record_not_ghosted_after_rollback"] = "EV-002" not in epm_broken.records

# --- 4. ECR: resolve() must roll back per-report and not raise. ---
from era.conflict.conflict_resolver import EvidenceConflictResolver
from era.conflict.conflict_models import ConflictEvidence
from era.conflict import conflict_errors as ecr_errors

ecr = EvidenceConflictResolver(store=broken)
evidence_items = [
    ConflictEvidence(evidence_id="EV-A", property_id="ERA-PR-TEST-001", field_name="year_built",
                      normalized_value="1998", provider_id="P1", source_reference="S1"),
    ConflictEvidence(evidence_id="EV-B", property_id="ERA-PR-TEST-001", field_name="year_built",
                      normalized_value="2001", provider_id="P2", source_reference="S2"),
]
try:
    status, reports = ecr.resolve(evidence_items)
    checks["ecr_returns_failure_not_raises"] = status == ecr_errors.PERSISTENCE_WRITE_FAILED and reports == []
except Exception:
    checks["ecr_returns_failure_not_raises"] = False
checks["ecr_rolled_back_no_ghost_report"] = len(ecr.reports) == 0

# --- 5. DEC: decide() must roll back. ---
from era.decision.decision_engine import DecisionEngine
from era.decision.decision_models import DecisionInput
from era.decision import decision_errors as dec_errors

dec = DecisionEngine(store=broken)
decision_input = DecisionInput(
    property_id="ERA-PR-TEST-001", evidence_count=2, required_fields_present=True,
    has_conflicts=False, has_policy_violation=False, manual_review_flag=False,
    single_source_only=False, export_ready=True, supporting_evidence_ids=["EV-001"],
)
try:
    status, record = dec.decide(decision_input)
    checks["dec_returns_failure_not_raises"] = status == dec_errors.PERSISTENCE_WRITE_FAILED and record is None
except Exception:
    checks["dec_returns_failure_not_raises"] = False
checks["dec_rolled_back_no_ghost_decision"] = dec.get_decision("ERA-PR-TEST-001") is None

# --- 6. POL: evaluate() must roll back. ---
from era.policy.policy_engine import PolicyEngine
from era.policy.policy_models import PolicyRuleSet, PolicyDecisionInput
from era.policy import policy_errors as pol_errors

pol = PolicyEngine(store=broken)
policy = PolicyRuleSet(policy_id="POL-TEST", policy_version="1.0",
                        allowed_decisions=["ACCEPT"], export_allowed=True,
                        require_manual_review_on_conflict=True)
policy_input = PolicyDecisionInput(property_id="ERA-PR-TEST-001", decision="ACCEPT",
                                    has_conflicts=False, export_requested=True,
                                    policy_violation=False, supporting_evidence_ids=["EV-001"])
try:
    status, result = pol.evaluate(policy, policy_input)
    checks["pol_returns_failure_not_raises"] = status == pol_errors.PERSISTENCE_WRITE_FAILED and result is None
except Exception:
    checks["pol_returns_failure_not_raises"] = False
checks["pol_rolled_back_no_ghost_result"] = pol.get_result("ERA-PR-TEST-001") is None

# --- 7. EXP: export() must roll back. ---
from era.export.export_engine import ExportEngine
from era.export.export_models import ExportRequest
from era.export.export_enums import ExportFormat
from era.export import export_errors as exp_errors

exp = ExportEngine(store=broken)
request = ExportRequest(property_id="ERA-PR-TEST-001", decision="ACCEPT", policy_verdict="AUTHORIZED",
                         provenance_complete=True, export_format=ExportFormat.JSON, payload={})
try:
    status, package = exp.export(request)
    checks["exp_returns_failure_not_raises"] = status == exp_errors.PERSISTENCE_WRITE_FAILED and package is None
except Exception:
    checks["exp_returns_failure_not_raises"] = False
checks["exp_rolled_back_no_ghost_export"] = exp.get_export("ERA-PR-TEST-001") is None

# --- 8. Audit sink failures must never propagate into the caller. ---
class AlwaysFailsSink:
    def __call__(self, event):
        raise RuntimeError("simulated audit sink failure")

publisher = BaseAuditPublisher(sink=AlwaysFailsSink())
try:
    result = publisher.publish("SOME_EVENT", {"x": 1})
    checks["audit_sink_failure_does_not_raise"] = result is True
except Exception:
    checks["audit_sink_failure_does_not_raise"] = False
checks["audit_event_still_kept_in_memory_despite_sink_failure"] = (
    len(publisher.events) == 1 and publisher.events[0]["event_type"] == "SOME_EVENT"
)

# --- 9. Real end-to-end proof: an actual unusable SQLite path (not a
# mock) produces the same clean failure path through SRR. A directory
# can never be opened as a database file by sqlite3, regardless of user
# privileges -- unlike a read-only file, which root bypasses, so this
# is a reliable fault to inject in any environment, including this one.
db_dir = tempfile.mkdtemp()
broken_db_path = db_dir  # the existing directory cannot be a SQLite file
try:
    real_store_failed_to_init = False
    try:
        real_store = SqliteStore(broken_db_path)
    except PersistenceError:
        # _ensure_schema() itself fails immediately against a directory
        # path -- that's still "fails clean with PersistenceError", just
        # at construction time instead of at register_connector() time.
        real_store_failed_to_init = True
    if real_store_failed_to_init:
        checks["real_broken_path_returns_failure_not_raises"] = True
        checks["real_broken_path_rolled_back"] = True
    else:
        real_srr = SourceReliabilityRegistry(store=real_store)
        try:
            status, connector = real_srr.register_connector(make_connector())
            checks["real_broken_path_returns_failure_not_raises"] = (
                status == srr_errors.PERSISTENCE_WRITE_FAILED and connector is None
            )
        except Exception:
            checks["real_broken_path_returns_failure_not_raises"] = False
        checks["real_broken_path_rolled_back"] = real_srr.get_connector("COUNTY_TEST") is None
finally:
    import shutil
    shutil.rmtree(db_dir, ignore_errors=True)

# --- 10. Successful writes are completely unaffected -- persistence
# error handling must not change the happy path at all. ---
real_db_fd, real_db_path = tempfile.mkstemp(suffix=".db")
os.close(real_db_fd)
os.remove(real_db_path)
try:
    healthy_store = SqliteStore(real_db_path)
    healthy_srr = SourceReliabilityRegistry(store=healthy_store)
    status, connector = healthy_srr.register_connector(make_connector())
    checks["happy_path_unaffected"] = status == srr_errors.PASS and connector is not None
finally:
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(real_db_path + suffix):
            os.remove(real_db_path + suffix)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"PERSISTENCE ERROR HANDLING CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
