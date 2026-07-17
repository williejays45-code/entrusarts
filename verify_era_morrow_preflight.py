from adapters.era_morrow_preflight_contract import (
    PREFLIGHT_VERSION,
    ERA_INTERFACE_VERSION,
    MORROW_INTERFACE_VERSION,
    ADAPTER_CONTRACT_VERSION,
    MORROW_VERSION_CONTRACT,
    CONFIDENCE_TRANSLATION_TABLE,
    ADAPTER_AUDIT_SCHEMA,
    translate_morrow_to_era,
    validate_preflight_contract,
)
print("ERA-MORROW ADAPTER PREFLIGHT CHECK")
print("=" * 60)
print("PREFLIGHT_VERSION:", PREFLIGHT_VERSION)
print("ERA_INTERFACE_VERSION:", ERA_INTERFACE_VERSION)
print("MORROW_INTERFACE_VERSION:", MORROW_INTERFACE_VERSION)
print("ADAPTER_CONTRACT_VERSION:", ADAPTER_CONTRACT_VERSION)
print()
print("MORROW VERSION CONTRACT")
print(MORROW_VERSION_CONTRACT)
print()
print("CONFIDENCE TRANSLATION")
for rule in CONFIDENCE_TRANSLATION_TABLE:
    print(f"{rule.morrow_state} -> {rule.era_confidence} | ceiling={rule.ceiling}")
print()
print("TRANSLATION TESTS")
print("VERIFIED ->", translate_morrow_to_era("VERIFIED"))
print("VALID ->", translate_morrow_to_era("VALID"))
print("PARTIAL ->", translate_morrow_to_era("PARTIAL"))
print("UNKNOWN ->", translate_morrow_to_era("UNKNOWN"))
print()
print("AUDIT SCHEMA FIELD COUNT:", len(ADAPTER_AUDIT_SCHEMA))
for field in ADAPTER_AUDIT_SCHEMA:
    print(f"{field.field_name} | required={field.required}")
print()
print("PREFLIGHT VALID:", validate_preflight_contract())
