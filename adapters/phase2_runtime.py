from adapters.phase2_contract import (
    AdapterIntent,
    offline_outcome,
    version_mismatch_outcome,
    duplicate_outcome,
    AdapterOutcome,
    now_utc,
)
from adapters.phase2_audit_store import AdapterAuditStore
from adapters.era_morrow_preflight_contract import (
    ADAPTER_CONTRACT_VERSION,
    MORROW_INTERFACE_VERSION,
    translate_morrow_to_era,
)
class ERAMorrowPhase2Adapter:
    def __init__(self, db_path: str = "eri_persistence.db", morrow_available: bool = True):
        self.audit = AdapterAuditStore(db_path)
        self.morrow_available = morrow_available
    def call(self, intent: AdapterIntent) -> AdapterOutcome:
        prior = self.audit.prior_final_outcome(intent.request_id)
        if prior is not None:
            return duplicate_outcome(intent.request_id, prior)
        self.audit.write_intent(intent)
        if intent.target_interface_version != MORROW_INTERFACE_VERSION:
            outcome = version_mismatch_outcome(intent.request_id)
            self.audit.write_outcome(intent, outcome)
            return outcome
        if not self.morrow_available:
            outcome = offline_outcome(intent.request_id)
            self.audit.write_outcome(intent, outcome)
            return outcome
        morrow_confidence = intent.payload.get("morrow_confidence", "UNSUPPORTED")
        translated = translate_morrow_to_era(morrow_confidence)
        outcome = AdapterOutcome(
            request_id=intent.request_id,
            accepted=translated != "UNSUPPORTED",
            translated_confidence=translated,
            outcome="ACCEPT" if translated != "UNSUPPORTED" else "REJECT",
            failure_state="NONE" if translated != "UNSUPPORTED" else "UNSUPPORTED_CONFIDENCE",
            response_payload={
                "morrow_confidence": morrow_confidence,
                "translated_confidence": translated,
                "adapter_contract_version": ADAPTER_CONTRACT_VERSION,
            },
            created_at=now_utc(),
        )
        self.audit.write_outcome(intent, outcome)
        return outcome
