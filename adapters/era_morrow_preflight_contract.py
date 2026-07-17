from dataclasses import dataclass
PREFLIGHT_VERSION = "ERA_MORROW_ADAPTER_PREFLIGHT-1.0"
ERA_INTERFACE_VERSION = "ERA_INTERFACE-1.0"
MORROW_INTERFACE_VERSION = "MORROW_INTERFACE-1.0"
ADAPTER_CONTRACT_VERSION = "ERA_MORROW_ADAPTER_CONTRACT-1.0"
@dataclass(frozen=True)
class MorrowVersionContract:
    interface_version: str
    evidence_validation_version: str
    continuity_version: str
    recovery_version: str
    confidence_version: str
@dataclass(frozen=True)
class ConfidenceTranslationRule:
    morrow_state: str
    era_confidence: str
    ceiling: str
    reason: str
@dataclass(frozen=True)
class AdapterAuditSchemaField:
    field_name: str
    required: bool
    description: str
MORROW_VERSION_CONTRACT = MorrowVersionContract(
    interface_version=MORROW_INTERFACE_VERSION,
    evidence_validation_version="MORROW_EVIDENCE-1.0",
    continuity_version="MORROW_CONTINUITY-1.0",
    recovery_version="MORROW_RECOVERY-1.0",
    confidence_version="MORROW_CONFIDENCE-1.0",
)
CONFIDENCE_TRANSLATION_TABLE = [
    ConfidenceTranslationRule(
        morrow_state="VERIFIED",
        era_confidence="PARTIAL",
        ceiling="PARTIAL",
        reason="MORROW verification cannot become ERA verification without ERA-side evidence validation.",
    ),
    ConfidenceTranslationRule(
        morrow_state="VALID",
        era_confidence="PARTIAL",
        ceiling="PARTIAL",
        reason="MORROW validity is advisory to ERA and cannot pass through raw.",
    ),
    ConfidenceTranslationRule(
        morrow_state="PARTIAL",
        era_confidence="ESTIMATED",
        ceiling="ESTIMATED",
        reason="MORROW partial confidence becomes estimated support inside ERA.",
    ),
    ConfidenceTranslationRule(
        morrow_state="ESTIMATED",
        era_confidence="ESTIMATED",
        ceiling="ESTIMATED",
        reason="Estimated confidence remains estimated across the boundary.",
    ),
    ConfidenceTranslationRule(
        morrow_state="DRAFT",
        era_confidence="DRAFT",
        ceiling="DRAFT",
        reason="Draft confidence remains draft across the boundary.",
    ),
    ConfidenceTranslationRule(
        morrow_state="PLACEHOLDER",
        era_confidence="DRAFT",
        ceiling="DRAFT",
        reason="Placeholder confidence cannot influence ERA as mature evidence.",
    ),
    ConfidenceTranslationRule(
        morrow_state="REJECTED",
        era_confidence="UNSUPPORTED",
        ceiling="UNSUPPORTED",
        reason="Rejected MORROW output is not usable by ERA.",
    ),
    ConfidenceTranslationRule(
        morrow_state="UNSUPPORTED",
        era_confidence="UNSUPPORTED",
        ceiling="UNSUPPORTED",
        reason="Unsupported MORROW output remains unsupported.",
    ),
]
ADAPTER_AUDIT_SCHEMA = [
    AdapterAuditSchemaField("era_interface_version", True, "Version of ERA interface consuming the adapter."),
    AdapterAuditSchemaField("adapter_contract_version", True, "Version of the frozen adapter contract."),
    AdapterAuditSchemaField("morrow_interface_version", True, "Version of MORROW interface targeted by the adapter."),
    AdapterAuditSchemaField("request_id", True, "Unique request identifier."),
    AdapterAuditSchemaField("request_type", True, "Type of adapter request."),
    AdapterAuditSchemaField("request_payload", True, "Serialized request payload."),
    AdapterAuditSchemaField("response_payload", True, "Serialized response payload."),
    AdapterAuditSchemaField("translated_confidence", True, "ERA-side translated confidence."),
    AdapterAuditSchemaField("outcome", True, "ACCEPT or REJECT."),
    AdapterAuditSchemaField("failure_state", True, "Failure state if rejected, NONE if accepted."),
    AdapterAuditSchemaField("created_at", True, "UTC timestamp."),
]
def translate_morrow_to_era(morrow_state: str) -> str:
    normalized = str(morrow_state).upper()
    for rule in CONFIDENCE_TRANSLATION_TABLE:
        if rule.morrow_state == normalized:
            return rule.era_confidence
    return "UNSUPPORTED"
def validate_preflight_contract() -> bool:
    if MORROW_VERSION_CONTRACT.interface_version != MORROW_INTERFACE_VERSION:
        return False
    if len(CONFIDENCE_TRANSLATION_TABLE) < 8:
        return False
    if translate_morrow_to_era("VERIFIED") == "VERIFIED":
        return False
    if translate_morrow_to_era("VALID") == "VERIFIED":
        return False
    required_fields = [field for field in ADAPTER_AUDIT_SCHEMA if field.required]
    if len(required_fields) != len(ADAPTER_AUDIT_SCHEMA):
        return False
    required_names = {field.field_name for field in ADAPTER_AUDIT_SCHEMA}
    expected = {
        "era_interface_version",
        "adapter_contract_version",
        "morrow_interface_version",
        "request_id",
        "request_type",
        "request_payload",
        "response_payload",
        "translated_confidence",
        "outcome",
        "failure_state",
        "created_at",
    }
    return expected.issubset(required_names)
