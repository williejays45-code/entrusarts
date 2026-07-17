from adapters.phase2_contract import AdapterIntent
from adapters.phase2_runtime import ERAMorrowPhase2Adapter
from adapters.era_morrow_preflight_contract import ADAPTER_CONTRACT_VERSION, MORROW_INTERFACE_VERSION
import sqlite3
def make_intent(request_id, morrow_confidence="VERIFIED", version=MORROW_INTERFACE_VERSION):
    return AdapterIntent(
        request_id=request_id,
        source_engine="ERA",
        target_engine="MORROW",
        adapter_version=ADAPTER_CONTRACT_VERSION,
        target_interface_version=version,
        request_type="confidence_translation",
        payload={"morrow_confidence": morrow_confidence},
    )
print("ERA-MORROW PHASE 2 PRE-LIVE SAFETY CHECK")
print("=" * 70)
live = ERAMorrowPhase2Adapter("eri_persistence.db", morrow_available=True)
offline = ERAMorrowPhase2Adapter("eri_persistence.db", morrow_available=False)
cases = [
    ("HAPPY_PATH", live, make_intent("REQ-001", "VERIFIED")),
    ("OFFLINE", offline, make_intent("REQ-002", "VERIFIED")),
    ("VERSION_MISMATCH", live, make_intent("REQ-003", "VERIFIED", "MORROW_INTERFACE-2.0")),
    ("UNKNOWN_CONFIDENCE", live, make_intent("REQ-004", "ALIEN_STATE")),
    ("DUPLICATE_FIRST", live, make_intent("REQ-005", "VALID")),
    ("DUPLICATE_RETRY", live, make_intent("REQ-005", "VALID")),
]
for name, adapter, intent in cases:
    result = adapter.call(intent)
    print(name)
    print("  REQUEST_ID:", result.request_id)
    print("  ACCEPTED:", result.accepted)
    print("  OUTCOME:", result.outcome)
    print("  FAILURE:", result.failure_state)
    print("  CONFIDENCE:", result.translated_confidence)
    print()
conn = sqlite3.connect("eri_persistence.db")
rows = conn.execute("""
SELECT request_id, stage, outcome, failure_state, translated_confidence
FROM adapter_phase2_audit
ORDER BY id DESC
LIMIT 12
""").fetchall()
print("LATEST PHASE 2 AUDIT")
for row in rows:
    print(row)
conn.close()
