from era.evidence_graph import EvidenceRepository, create_evidence_record
repo = EvidenceRepository("eri_persistence.db")
repo.save(create_evidence_record(
    engine="ERA",
    metric="THS",
    evidence_type="score_input",
    source_name="score_history",
    source_value="95.55",
    confidence="PARTIAL",
    validator_status="PLACEHOLDER",
    notes="Latest persisted THS snapshot used as evidence",
))
repo.save(create_evidence_record(
    engine="ERA",
    metric="THS",
    evidence_type="decision_trace",
    source_name="recovery_action",
    source_value="REANCHOR_AND_REVIEW",
    confidence="PARTIAL",
    validator_status="PLACEHOLDER",
    notes="MORROW-style recovery path linked to THS",
))
repo.save(create_evidence_record(
    engine="ERA",
    metric="THS",
    evidence_type="governance",
    source_name="placeholder_integrity_law",
    source_value="THS remains PARTIAL until constants graduate",
    confidence="VERIFIED",
    validator_status="VALID",
    notes="Governance reason supporting confidence cap",
))
rows = repo.load_for_score("ERA", "THS")
print("EVIDENCE COUNT:", len(rows))
for row in rows:
    print(row)
