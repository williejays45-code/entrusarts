import sys
import os
import tempfile
from era.shared.persistence import SqliteStore
from era.provenance.provenance_manager import EvidenceProvenanceManager
from era.provenance.provenance_models import ProvenanceInput
from era.provenance.provenance_enums import EvidenceStatus
from era.provenance import provenance_errors as errors

print("EPM PERSISTENCE VERIFICATION (C4 rollout, step 3)")
print("=" * 70)


def make_input(evidence_id, value, previous_evidence_id=None):
    return ProvenanceInput(
        evidence_id=evidence_id, property_id="ERA-PR-2026-000001",
        canonical_field="address", canonical_value=value, original_value=value,
        provider_id="COUNTY_DALLAS_CAD", provider_name="Dallas Central Appraisal District",
        legal_basis="PUBLIC_RECORD", source_reference="DCAD-PUBLIC-SEARCH",
        retrieved_at="2026-07-09T00:00:00+00:00", connector_version="1.0",
        adapter_version="LPA-001.0", normalization_version="ECM-001.0",
        previous_evidence_id=previous_evidence_id,
    )


checks = {}
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    store_a = SqliteStore(db_path)
    manager_a = EvidenceProvenanceManager(store=store_a)
    status1, record1 = manager_a.register_evidence(make_input("EV-001", "5926 Sandhurst Ln"))
    checks["first_register_ok"] = status1 == errors.PASS
    # Register a correction that supersedes EV-001 -- this is the
    # trickiest state to get right: it mutates EV-001's stored status,
    # not just inserts a new row.
    status2, record2 = manager_a.register_evidence(
        make_input("EV-002", "5926 Sandhurst Ln Unit 224", previous_evidence_id="EV-001")
    )
    checks["superseding_register_ok"] = status2 == errors.PASS and record2.chain_position == 2
    del manager_a  # simulate process exit

    store_b = SqliteStore(db_path)
    manager_b = EvidenceProvenanceManager(store=store_b)
    reloaded_ev001 = manager_b.get_record("EV-001")
    reloaded_ev002 = manager_b.get_record("EV-002")
    checks["superseded_record_status_survived_restart"] = (
        reloaded_ev001 is not None and reloaded_ev001.status == EvidenceStatus.SUPERSEDED
    )
    checks["superseded_by_survived_restart"] = (
        reloaded_ev001.superseded_by == "EV-002" if reloaded_ev001 else False
    )
    checks["active_record_survived_restart"] = (
        reloaded_ev002 is not None and reloaded_ev002.status == EvidenceStatus.ACTIVE
    )
    checks["chain_position_survived_restart"] = (
        reloaded_ev002.chain_position == 2 if reloaded_ev002 else False
    )
    chain = manager_b.get_chain("EV-002")
    checks["get_chain_survived_restart"] = (
        len(chain) == 2 and chain[0].evidence_id == "EV-001" and chain[1].evidence_id == "EV-002"
    )
    # Hash integrity must still hold after reload -- a real reconstructed
    # ProvenanceRecord, not a dict pretending to be one.
    checks["evidence_hash_present_after_reload"] = bool(reloaded_ev002.evidence_hash)

    plain_manager = EvidenceProvenanceManager()
    plain_status, _ = plain_manager.register_evidence(make_input("EV-003", "test"))
    checks["no_store_default_still_works"] = plain_status == errors.PASS
    checks["no_store_default_has_no_store_attr_set"] = plain_manager.store is None

finally:
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print("EPM PERSISTENCE CHECKS PASSED:", f"{passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
