import sqlite3
conn = sqlite3.connect("eri_persistence.db")
conn.execute("""
CREATE TABLE IF NOT EXISTS evidence_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL UNIQUE,
    score_entry_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    metric TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_value TEXT NOT NULL,
    confidence TEXT NOT NULL,
    validator_status TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
)
""")
conn.execute("""
CREATE INDEX IF NOT EXISTS ix_evidence_score_entry
ON evidence_records(score_entry_id)
""")
conn.execute("""
CREATE INDEX IF NOT EXISTS ix_evidence_engine_metric
ON evidence_records(engine, metric)
""")
conn.commit()
conn.close()
print("evidence_records table ready")
