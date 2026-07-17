import sqlite3
conn = sqlite3.connect("eri_persistence.db")
conn.execute("""
CREATE TABLE IF NOT EXISTS weight_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weight_id TEXT NOT NULL UNIQUE,
    engine TEXT NOT NULL,
    metric TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    weight_value REAL NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
)
""")
conn.execute("""
CREATE INDEX IF NOT EXISTS ix_weight_registry_engine_metric
ON weight_registry(engine, metric)
""")
conn.commit()
conn.close()
print("weight_registry table ready")
