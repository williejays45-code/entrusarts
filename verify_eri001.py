from era.evidence_reliability import (
    EvidenceItem,
    METHODOLOGY_VERSION,
    evaluate_evidence,
    detect_contradiction,
)
print("ERI-001 EVIDENCE RELIABILITY ENGINE CHECK")
print("=" * 70)
cases = [
    EvidenceItem(
        evidence_id="EV-001",
        category="government_record",
        source="county_record",
        attribute="occupancy",
        value="occupied",
        methodology_version=METHODOLOGY_VERSION,
        factors={
            "source_authenticity": True,
            "source_authority": True,
            "completeness": 1.0,
            "currency": 1.0,
            "internal_consistency": True,
            "cross_source_agreement": True,
            "chain_of_custody": True,
            "verification_history": 1.0,
        },
    ),
    EvidenceItem(
        evidence_id="EV-002",
        category="ai_inference",
        source="internal_reasoner",
        attribute="risk",
        value="low",
        methodology_version=METHODOLOGY_VERSION,
        factors={
            "source_authenticity": True,
            "completeness": 1.0,
            "currency": 1.0,
            "chain_of_custody": True,
        },
    ),
    EvidenceItem(
        evidence_id="EV-003",
        category="mystery_source",
        source="unknown",
        attribute="occupancy",
        value="vacant",
        methodology_version=METHODOLOGY_VERSION,
        factors={},
    ),
    EvidenceItem(
        evidence_id="EV-004",
        category="government_record",
        source="county_record",
        attribute="occupancy",
        value="occupied",
        methodology_version="OLD_METHOD",
        factors={},
    ),
    EvidenceItem(
        evidence_id="EV-005",
        category="government_record",
        source="county_record",
        attribute="title",
        value="clear",
        methodology_version=METHODOLOGY_VERSION,
        factors={
            "source_authenticity": True,
            "source_authority": True,
            "completeness": 1.0,
            "currency": 1.0,
            "internal_consistency": True,
            "cross_source_agreement": True,
            "chain_of_custody": False,
            "verification_history": 1.0,
        },
    ),
]
for item in cases:
    result = evaluate_evidence(item)
    print(result)
conflict_result = detect_contradiction([
    EvidenceItem(
        evidence_id="EV-C1",
        category="government_record",
        source="county",
        attribute="occupancy",
        value="occupied",
        methodology_version=METHODOLOGY_VERSION,
        factors={},
    ),
    EvidenceItem(
        evidence_id="EV-C2",
        category="inspection",
        source="inspection",
        attribute="occupancy",
        value="vacant",
        methodology_version=METHODOLOGY_VERSION,
        factors={},
    ),
])
print()
print("CONTRADICTION CHECK")
print(conflict_result)
print()
print("EXPECTED PASS CONDITIONS")
print("UNKNOWN -> UNSUPPORTED")
print("AI -> PLACEHOLDER")
print("VERSION MISMATCH -> UNSUPPORTED")
print("CONFLICT -> CONFLICTING_EVIDENCE")
